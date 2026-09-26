from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager

import click

from cli._output import output
from cli._query import select_rows
from cli.esp_commands import esp, _load_plugin


def _open(path, game):
    return _load_plugin(Path(path), game=game, strings_dir=None, language=None, backend="native", lazy_index=True)


def _ids(plugin, record_ids):
    from creation_lib.inspection.records import record_catalog
    if not record_ids:
        return []
    catalog = record_catalog(plugin)
    result = []
    for value in record_ids:
        text = value.strip()
        try:
            number = int(text, 16)
        except ValueError:
            matches = [r for r in catalog if r["editor_id"].casefold() == text.casefold() or r["form_key"].casefold() == text.casefold()]
        else:
            if len(text.removeprefix("0x")) > 6:
                matches = [r for r in catalog if r["form_id"] == number]
            else:
                matches = [r for r in catalog if r["form_id"] & 0xFFFFFF == number]
                owned = [r for r in matches if r["form_key"].split(":", 1)[0].casefold() == plugin.plugin_name.casefold()]
                matches = owned or matches
        if len(matches) != 1:
            raise click.ClickException(f"Record not found or ambiguous: {value}")
        result.append(matches[0]["form_id"])
    return result


def _types(signatures):
    from creation_lib.esp.record_types import record_type_signature
    return [record_type_signature(s) for s in signatures]


@esp.command("race-subgraphs")
@click.argument("plugin_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("record_id", required=False)
@click.pass_context
def race_subgraphs(ctx, plugin_path, record_id):
    """Group RACE behavior paths, keywords and flags with the native AnimTextData parser."""
    from creation_lib.inspection.animation import race_subgraphs
    form_id = None
    if record_id:
        with _open(plugin_path, ctx.obj["game"]) as plugin:
            form_id = _ids(plugin, [record_id])[0]
    output(race_subgraphs(plugin_path, ctx.obj["game"], form_id), ctx.obj["fmt"], collection="races")


@esp.command("query")
@click.argument("plugin_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--record", "record_ids", multiple=True, help="EditorID or local hex FormID; repeatable.")
@click.option("--type", "signatures", multiple=True)
@click.option("--match", default="*", help="EditorID glob.")
@click.pass_context
def query(ctx, plugin_path, record_ids, signatures, match):
    """Query decoded record fields without a full plugin export.

    Global --fields/--where/--limit/--offset/--count-only/--group-by precede esp.
    Example: modkit --fields eid,fields --limit 5 esp query B21_Example.esp --type ACTI
    """
    from creation_lib.inspection.records import record_rows
    with _open(plugin_path, ctx.obj["game"]) as plugin:
        rows = record_rows(plugin, signatures=_types(signatures), pattern=match, record_ids=_ids(plugin, record_ids))
        report = select_rows(rows, ctx.obj["report_options"])
        report["meta"].update(plugin=str(Path(plugin_path).resolve()), game=plugin.game)
        output(report, ctx.obj["fmt"], queried=True)


@esp.command("vmad")
@click.argument("plugin_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("record_id", required=False)
@click.option("--type", "signatures", multiple=True)
@click.option("--script", default=None, help="Exact, case-insensitive attached script name.")
@click.option("--script-glob", default=None, help="Case-insensitive script glob.")
@click.option("--property", "property_name", default=None, help="Require an exact property name.")
@click.option("--fail-on-incomplete", is_flag=True, help="Exit 1 if any candidate VMAD could not be fully decoded.")
@click.pass_context
def vmad(ctx, plugin_path, record_id, signatures, script, script_glob, property_name, fail_on_incomplete):
    """Find decoded script bindings, typed properties, aliases and fragments.

    Example: modkit --fields editor_id,script,scope,properties esp vmad B21_Example.esp --script B21_Activator
    """
    from creation_lib.inspection.records import vmad_rows
    with _open(plugin_path, ctx.obj["game"]) as plugin:
        diagnostics = {}
        rows = vmad_rows(plugin, diagnostics, signatures=_types(signatures),
                         record_ids=_ids(plugin, [record_id]) if record_id else (),
                         script=script, script_glob=script_glob, property_name=property_name)
        report = select_rows(rows, ctx.obj["report_options"])
        report["meta"].update(plugin=str(Path(plugin_path).resolve()), game=plugin.game, **diagnostics)
        output(report, ctx.obj["fmt"], queried=True)
        if fail_on_incomplete and not diagnostics["complete"]:
            ctx.exit(1)


def semantic_diff(ctx, a_path, b_path, record_type, record_ids, fields, exclude, normalize):
    from creation_lib.esp import native_runtime
    from creation_lib.inspection.records import named_fields, normalize_references, field_differences, record_catalog

    def identity(plugin, row):
        owner, oid = row["form_key"].rsplit(":", 1)
        return ("$self" if owner.casefold() == plugin.plugin_name.casefold() else owner.casefold(), int(oid, 16))

    def decoded(plugin, row):
        if row is None:
            return {}
        inspected = native_runtime.plugin_handle_inspect_record(plugin._rust_handle, row["form_id"])
        return {**named_fields(inspected["record"]), "signature": inspected["signature"]}

    with _open(a_path, ctx.obj["game"]) as left, _open(b_path, ctx.obj["game"]) as right:
        types = _types([record_type]) if record_type else None
        a_index = {identity(left, row): row for row in record_catalog(left, types or ())}
        b_index = {identity(right, row): row for row in record_catalog(right, types or ())}
        selected = set(a_index) | set(b_index)
        if record_ids:
            selected = set()
            for value in record_ids:
                found = False
                for plugin, index in ((left, a_index), (right, b_index)):
                    try:
                        fid = _ids(plugin, [value])[0]
                    except click.ClickException:
                        continue
                    for key, row in index.items():
                        if row["form_id"] == fid:
                            selected.add(key)
                            found = True
                if not found:
                    raise click.ClickException(f"Record not found in either plugin: {value}")
        changes, counts = [], {"added": 0, "removed": 0, "changed": 0}
        for key in sorted(selected):
            a_row, b_row = a_index.get(key), b_index.get(key)
            before, after = decoded(left, a_row), decoded(right, b_row)
            if normalize:
                before, after = normalize_references(before, left.plugin_name), normalize_references(after, right.plugin_name)
            differences = field_differences(before, after, fields=fields, exclude=exclude)
            if not differences:
                continue
            status = "added" if a_row is None else "removed" if b_row is None else "changed"
            counts[status] += 1
            row = b_row or a_row
            changes.append({"object_id": f"{key[1]:06X}", "form_key": row["form_key"], "signature": row["signature"],
                            "editor_id": row["editor_id"], "status": status, "changes": differences})
        report = {"plugin_a": str(a_path.resolve()), "plugin_b": str(b_path.resolve()),
                  "semantic": True, "normalized_references": normalize, "counts": counts, "changes": changes}
        output(report, ctx.obj["fmt"], collection="changes")


def resolution_options(function):
    function = click.option("--asset-root", "asset_roots", multiple=True, type=click.Path(exists=True, file_okay=False, path_type=Path), help="Data or asset-category root. Later roots take precedence.")(function)
    function = click.option("--archive", "archive_paths", multiple=True, type=click.Path(exists=True, dir_okay=False, path_type=Path), help="BA2/BSA to search. Later archives take precedence.")(function)
    function = click.option("--master-search-path", "master_paths", multiple=True, type=click.Path(exists=True, file_okay=False, path_type=Path))(function)
    function = click.option("--load-order", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None, help="Ordered plugin paths/names, one per line. Read-only; * prefixes allowed.")(function)
    return function


@contextmanager
def _graph(ctx, plugin_path, master_paths, load_order, *, lazy_index=True):
    from creation_lib.inspection.graph import PluginGraph
    roots = [Path(plugin_path).resolve().parent, *master_paths]
    if load_order:
        roots.append(load_order.resolve().parent)
    with PluginGraph(ctx.obj["game"], roots, lazy_index=lazy_index) as graph:
        if load_order:
            for line in load_order.read_text(encoding="utf-8-sig").splitlines():
                name = line.strip().lstrip("*")
                if not name or name.startswith("#"):
                    continue
                path = graph.find(name)
                if path is None:
                    raise click.ClickException(f"Load-order plugin not found: {name}")
                graph.load(path)
        plugin = graph.load(plugin_path)
        yield graph, plugin


def _resolver(plugin_path, asset_roots, archive_paths):
    from creation_lib.inspection.assets import AssetResolver
    roots = list(asset_roots)
    if not roots:
        root = Path(plugin_path).resolve().parent
        roots = [root]
        if (root / "data").is_dir():
            roots.append(root / "data")
    return AssetResolver(roots, archive_paths)


@esp.command("quest-papyrus")
@click.argument("plugin_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("quest_ids", nargs=-1, required=True)
@click.option("--source-root", "source_roots", multiple=True, required=True,
              type=click.Path(exists=True, file_okay=False, path_type=Path),
              help="Root of complete, merged PSC files, including imports. Later roots win; namespaces are directories.")
@click.option("--generated-source-root", "generated_roots", multiple=True,
              type=click.Path(exists=True, file_okay=False, path_type=Path),
              help="Optional generated PSC roots to compare with merged source by SHA-256. Later roots win.")
@resolution_options
@click.option("--max-records", default=10000, type=click.IntRange(min=0), show_default=True, help="Per-quest record limit; 0 means unlimited.")
@click.option("--max-scripts", default=10000, type=click.IntRange(min=0), show_default=True, help="Per-quest script limit; 0 means unlimited.")
@click.option("--fail-on-incomplete", is_flag=True, help="Exit 1 for incomplete static coverage (independent of output pagination).")
@click.pass_context
def quest_papyrus(ctx, plugin_path, quest_ids, source_roots, generated_roots, asset_roots,
                  archive_paths, master_paths, load_order, max_records, max_scripts, fail_on_incomplete):
    """Audit quest Papyrus dependency closure, VMAD/PSC coverage and source/output freshness.

    Follows record references, reverse quest references, nested dialogue INFOs,
    script parents/imports/types and literal Game.GetFormFromFile dependencies.
    Reports every stage item, callback body, property use and SetStage producer.
    Global --items scripts|bindings|stages|stage_producers|records|edges|issues
    selects a flat inventory across quests; --fields/--where then apply to it.
    Dynamic dependencies and traversal limits are explicit; this is a static
    inventory, not proof of runtime reachability or matching compiled bytecode.
    Supply already-merged sources; method-only patch files are not full scripts.
    """
    from creation_lib.inspection.papyrus import PapyrusSources
    from creation_lib.inspection.quest_papyrus import QuestPapyrusAudit
    from creation_lib.inspection.records import form_key

    with _graph(ctx, plugin_path, master_paths, load_order, lazy_index=False) as (graph, plugin):
        ids = _ids(plugin, quest_ids)
        keys = list(dict.fromkeys(form_key(plugin, fid) for fid in ids))
        if any(graph.resolve(key)[-1][1]["signature"] != "QUST" for key in keys):
            raise click.ClickException("All requested records must be quests (QUST)")
        sources = PapyrusSources(source_roots, generated_roots)
        resolver = _resolver(plugin_path, asset_roots, archive_paths)
        auditor = QuestPapyrusAudit(graph, sources, resolver, max_records=max_records, max_scripts=max_scripts)
        try:
            rows = [auditor.audit(key) for key in keys]
        except (ValueError, RuntimeError, OSError) as error:
            raise click.ClickException(str(error)) from error
        destination = ctx.obj["report_options"].get("output")
        if destination:
            target = Path(destination).resolve()
            inputs = {Path(p.file_path).resolve() for p in graph.plugins}
            inputs.update(p for entries in sources.files.values() for _, p in entries)
            inputs.update(p for entries in sources.generated.values() for _, p in entries)
            for row in rows:
                for source in row["scripts"]:
                    inputs.update(Path(loc["path"]).resolve() for loc in source["output"]["resolution"].get("locations", []))
            if target in inputs:
                raise click.BadParameter("Report output must differ from inspected plugin, source and script output files", param_hint="--output")
        options = ctx.obj["report_options"]
        items = options.get("items")
        selected = rows
        if items == "stages":
            selected = [{"root_quest": row["quest"], "quest": quest["quest"], **stage}
                        for row in rows for quest in row["quests"] for stage in quest["stages"]]
        elif items in {"scripts", "bindings", "stage_producers", "records", "edges", "issues"}:
            selected = [{"root_quest": row["quest"], **entry} for row in rows for entry in row[items]]
        elif items:
            raise click.BadParameter("Choose scripts, bindings, stages, stage_producers, records, edges or issues", param_hint="--items")
        report = select_rows(selected, options)
        if items:
            report["meta"]["items"] = items
        report["meta"].update(schema_version=1, plugin=str(plugin_path.resolve()), game=plugin.game,
                              complete=all(row["complete"] for row in rows),
                              scope="Static record references, reverse QUST references, DIAL children, PSC dependencies and literal form lookups",
                              runtime_reachability="not_proven", bytecode_matches_source="unverified",
                              source_roots=[str(p) for p in sources.roots],
                              generated_source_roots=[str(p) for p in sources.generated_roots],
                              load_order=[str(p.file_path) for p in graph.plugins], resolution=resolver.describe())
        output(report, ctx.obj["fmt"], queried=True)
        if fail_on_incomplete and not report["meta"]["complete"]:
            ctx.exit(1)


@esp.command("quest-status")
@click.argument("plugin_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("quest_ids", nargs=-1)
@click.option("--ids-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Quest EditorIDs or local hex FormIDs, one per line (# comments allowed).")
@click.option("--all-quests", is_flag=True, help="Audit every QUST in the plugin.")
@click.option("--source-root", "source_roots", multiple=True, required=True,
              type=click.Path(exists=True, file_okay=False, path_type=Path),
              help="Root of the plugin's merged/generated PSC files. Later roots win.")
@click.option("--base-root", "base_roots", multiple=True,
              type=click.Path(exists=True, file_okay=False, path_type=Path),
              help="Game base-script PSC root. Scripts resolved here count as vanilla, not hollow.")
@click.option("--pending-root", "pending_roots", multiple=True,
              type=click.Path(exists=True, file_okay=False, path_type=Path),
              help="Method-only patch fragments; empty members they define are reported as pending, not open.")
@click.pass_context
def quest_status(ctx, plugin_path, quest_ids, ids_file, all_quests, source_roots, base_roots, pending_roots):
    """Batch quest triage: start wiring plus empty/missing Papyrus bodies.

    For each quest: event scoping and Story Manager nodes, quest/alias scripts
    with empty members, stage fragments that are empty or missing, and empty
    fragments on TERM/SCEN/INFO/PACK/PERK records owned by or bound to it.
    Static only; faster than quest-papyrus because it skips the full closure.
    Example: modkit --fields editor_id,summary esp quest-status X.esm EN01_MQ_Bunker --source-root Scripts/Source/User
    """
    from creation_lib.inspection.quest_status import QuestStatusAudit
    queries = list(quest_ids)
    if ids_file:
        queries += [line.split("#", 1)[0].strip() for line in ids_file.read_text(encoding="utf-8-sig").splitlines()]
        queries = [q for q in queries if q]
    if not queries and not all_quests:
        raise click.UsageError("Pass quest IDs, --ids-file or --all-quests")
    with _open(plugin_path, ctx.obj["game"]) as plugin:
        auditor = QuestStatusAudit(plugin, source_roots, base_roots=base_roots, pending_roots=pending_roots)
        if all_quests:
            queries += [row["form_key"].split(":", 1)[1] for row in auditor.catalog.values()
                        if row["signature"] == "QUST" and row["form_key"].casefold().startswith(plugin.plugin_name.casefold() + ":")]
        rows = [auditor.audit(q) for q in dict.fromkeys(queries)]
        report = select_rows(rows, ctx.obj["report_options"])
        report["meta"].update(plugin=str(plugin_path.resolve()), game=plugin.game,
                              source_roots=[str(p) for p in source_roots], base_roots=[str(p) for p in base_roots],
                              pending_roots=[str(p) for p in pending_roots], runtime_reachability="not_proven")
        output(report, ctx.obj["fmt"], queried=True)


@esp.command("explain")
@click.argument("plugin_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("record_id")
@resolution_options
@click.option("--depth", type=click.IntRange(min=0), default=2, show_default=True)
@click.option("--max-records", type=click.IntRange(min=1), default=100, show_default=True)
@click.option("--max-assets", type=click.IntRange(min=1), default=500, show_default=True)
@click.pass_context
def explain(ctx, plugin_path, record_id, asset_roots, archive_paths, master_paths, load_order, depth, max_records, max_assets):
    """Follow record references, VMAD scripts, NIF materials and textures; show override winners and missing assets."""
    from creation_lib.inspection.graph import explain_record
    from creation_lib.inspection.records import form_key
    with _graph(ctx, plugin_path, master_paths, load_order) as (graph, plugin):
        fid = _ids(plugin, [record_id])[0]
        matches = [row for row in graph.index(plugin).values() if row["form_id"] == fid]
        if not matches:
            matches = [row for row in graph.index(plugin).values() if row["form_id"] & 0xFFFFFF == fid & 0xFFFFFF]
        if len(matches) != 1:
            raise click.ClickException(f"Ambiguous record: {record_id}; specify a raw FormID")
        key = form_key(plugin, matches[0]["form_id"])
        report = explain_record(graph, key, _resolver(plugin_path, asset_roots, archive_paths),
                                depth=depth, max_records=max_records, max_assets=max_assets)
        report["load_order"] = [p.plugin_name for p in graph.plugins]
        output(report, ctx.obj["fmt"])


def _placements(plugin, cell=None, worldspace=None):
    from creation_lib.esp import native_runtime
    from cli.esp_commands import _PLACED_RECORD_SIGNATURES, _resolve_cell_raw_form_id
    from creation_lib.inspection.records import record_catalog
    if cell and worldspace:
        raise click.UsageError("--cell and --worldspace are mutually exclusive")
    if cell:
        fid = _resolve_cell_raw_form_id(plugin._rust_handle, cell)
        return native_runtime.plugin_handle_collect_cell_children(plugin._rust_handle, fid)
    rows = record_catalog(plugin, _PLACED_RECORD_SIGNATURES)
    if worldspace:
        from creation_lib.inspection.records import form_key
        roots = native_runtime.plugin_handle_collect_cell_slice_roots(plugin._rust_handle,
            worldspace_editor_id=worldspace, min_x=-(2**31), min_y=-(2**31), max_x=2**31-1, max_y=2**31-1,
            include_worldspace_persistent_cell=True)
        if not roots.get("worldspace_form_keys"):
            raise click.ClickException(f"Worldspace not found: {worldspace}")
        wanted = {key.casefold() for key in roots.get("placed_form_keys", [])}
        rows = [row for row in rows if form_key(plugin, row["form_id"]).casefold() in wanted]
    return rows


@esp.command("placed-models")
@click.argument("plugin_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--cell", default=None)
@click.option("--worldspace", default=None)
@click.option("--base-type", "base_types", multiple=True)
@click.option("--fail-on-missing", is_flag=True)
@resolution_options
@click.pass_context
def placed_models(ctx, plugin_path, cell, worldspace, base_types, fail_on_missing, asset_roots, archive_paths, master_paths, load_order):
    """Audit placed base models against loose files and archives, including malformed paths and unresolved bases."""
    from creation_lib.inspection.placed import placed_rows, model_census
    with _graph(ctx, plugin_path, master_paths, load_order) as (graph, plugin):
        resolver = _resolver(plugin_path, asset_roots, archive_paths)
        report = model_census(placed_rows(graph, plugin, _placements(plugin, cell, worldspace), resolver, base_types=_types(base_types)))
        report.update(plugin=str(plugin_path.resolve()), cell=cell, worldspace=worldspace, issues=graph.issues, resolution=resolver.describe())
        failed = bool(graph.issues) or any(row["status"] != "available" for row in report["records"])
        output(report, ctx.obj["fmt"], collection="records")
        if fail_on_missing and failed:
            ctx.exit(1)


@esp.command("cell-collision")
@click.argument("plugin_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("cell")
@click.option("--base-type", "base_types", multiple=True)
@resolution_options
@click.pass_context
def cell_collision(ctx, plugin_path, cell, base_types, asset_roots, archive_paths, master_paths, load_order):
    """Inventory a cell's placed models and decoded collision bodies, layers and masses."""
    from creation_lib.inspection.placed import placed_rows
    with _graph(ctx, plugin_path, master_paths, load_order) as (graph, plugin):
        resolver = _resolver(plugin_path, asset_roots, archive_paths)
        rows = placed_rows(graph, plugin, _placements(plugin, cell=cell), resolver, base_types=_types(base_types), collision=True)
        report = select_rows(rows, ctx.obj["report_options"])
        report["meta"].update(plugin=str(plugin_path.resolve()), cell=cell, issues=graph.issues, resolution=resolver.describe())
        output(report, ctx.obj["fmt"], queried=True)


def register_asset_commands(cli):
    from cli.nif_commands import nif

    @nif.command("collision-report")
    @click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @click.pass_context
    def nif_collision_report(ctx, path):
        """Read collision blocks and embedded Havok bodies without editing the NIF."""
        from creation_lib.inspection.collision import collision_report
        output({"path": str(path.resolve()), **collision_report(path.read_bytes())}, ctx.obj["fmt"], collection="blocks")

    @cli.group("behavior")
    def behavior():
        """Inspect local HKX behavior graphs and their XML sources."""

    @behavior.command("report")
    @click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @click.pass_context
    def report(ctx, path):
        """Describe events, variables, states, transitions, clips and unresolved graph references."""
        from creation_lib.inspection.behavior import behavior_report
        output(behavior_report(path), ctx.obj["fmt"])
