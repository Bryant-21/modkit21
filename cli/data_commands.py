"""modkit data — creation-data CLI commands."""

import json
import sys

import click

import creation_lib.creation_data as cd
from cli._output import output


def _ctx_args(ctx):
    """Extract game, fmt, db_dir from click context."""
    return ctx.obj["game"], ctx.obj["fmt"], ctx.obj["db_dir"]


# Common option decorators
def filter_options(f):
    """Add common filter options for search/list commands."""
    f = click.option("-t", "--type", "record_type", default="", help="Filter by record type (e.g. Weapons)")(f)
    f = click.option("-s", "--source", default="", help="Filter by source (e.g. Fallout4.esm)")(f)
    f = click.option("--category", default="", help="Filter by category")(f)
    f = click.option("--extends", default="", help="Filter by parent script type")(f)
    f = click.option("--mod", "mod_name", default="", help="Filter by external mod name")(f)
    f = click.option("-e", "--external", is_flag=True, help="Include external mod data")(f)
    return f


def result_options(f):
    """Add max-results option."""
    f = click.option("-n", "--max-results", default=10, type=int, help="Max results (default 10)")(f)
    return f


@click.group()
@click.option("--game", default=None, help="Game profile (overrides global --game).")
@click.option("--format", "fmt", type=click.Choice(["json", "pretty", "compact", "table"]), default=None, help="Output format (overrides global --format).")
@click.pass_context
def data(ctx, game, fmt):
    """Search and query Bethesda game data — records, scripts, wiki, behaviors, NIFs."""
    if game is not None:
        ctx.obj["game"] = game
    if fmt is not None:
        ctx.obj["fmt"] = fmt


@data.command()
@click.argument("domain")
@click.argument("query", default="")
@filter_options
@click.option("--full-text", is_flag=True, help="Full-text search for NIFs domain")
@click.option("--cross-game", is_flag=True, help="Search across all games (behaviors/nifs)")
@result_options
@click.pass_context
def search(ctx, domain, query, record_type, source, category, extends, mod_name, external, full_text, cross_game, max_results):
    """Full-text search across game data.

    DOMAIN: records, scripts, wiki, behaviors, nifs, ext_records, ext_scripts

    Examples:

      modkit data search records "combat shotgun"

      modkit data search scripts "OnDeath" --extends Quest

      modkit data search nifs "laser" --full-text
    """
    game, fmt, db_dir = _ctx_args(ctx)
    # Map external flag to include_external for records/scripts, or mod_name for ext_ domains
    result = cd.search(
        domain=domain, query=query, record_type=record_type, source=source,
        category=category, extends=extends, mod_name=mod_name, full_text=full_text,
        cross_game=cross_game, max_results=max_results, game=game, db_dir=db_dir,
    )
    output(result, fmt)


@data.command()
@click.argument("domain")
@click.argument("query")
@filter_options
@click.option("--cross-game", is_flag=True, help="Search across all games (behaviors/nifs)")
@result_options
@click.pass_context
def semantic(ctx, domain, query, record_type, source, category, extends, mod_name, external, cross_game, max_results):
    """AI semantic search (natural language queries).

    Examples:

      modkit data semantic records "place where you craft chems"

      modkit data semantic scripts "script that handles death"
    """
    game, fmt, db_dir = _ctx_args(ctx)
    try:
        result = cd.semantic_search(
            domain=domain, query=query, record_type=record_type, source=source,
            category=category, extends=extends, mod_name=mod_name, cross_game=cross_game,
            max_results=max_results, game=game, db_dir=db_dir, model_ready=True,
        )
    except ImportError:
        print("Error: semantic search requires sentence-transformers. Install with: uv pip install sentence-transformers", file=sys.stderr)
        sys.exit(1)
    output(result, fmt)


@data.command()
@click.argument("domain")
@click.argument("id")
@click.pass_context
def get(ctx, domain, id):
    """Get full content by ID.

    DOMAIN: records, scripts, wiki, behaviors, nifs, ext_records, ext_scripts

    Examples:

      modkit data get records "004822:Fallout4.esm"

      modkit data get scripts Actor
    """
    game, fmt, db_dir = _ctx_args(ctx)
    result = cd.get_content(domain=domain, id=id, game=game, db_dir=db_dir)
    output(result, fmt)


@data.command("list")
@click.argument("domain")
@filter_options
@result_options
@click.pass_context
def list_cmd(ctx, domain, record_type, source, category, extends, mod_name, external, max_results):
    """List or count items in a domain.

    DOMAIN: records, record_types, scripts, extends_types, script_types,
    wiki_categories, wiki_record_types, behaviors, nifs, nif_categories, ext_mods

    Examples:

      modkit data list record_types

      modkit data list scripts --extends Quest -n 50
    """
    game, fmt, db_dir = _ctx_args(ctx)
    result = cd.list_items(
        domain=domain, record_type=record_type, source=source, category=category,
        extends=extends, mod_name=mod_name, max_results=max_results, game=game, db_dir=db_dir,
    )
    output(result, fmt)


@data.command()
@click.argument("form_key")
@click.option("--content", "include_content", is_flag=True, help="Include full YAML content")
@click.pass_context
def record(ctx, form_key, include_content):
    """Get a game record by FormKey.

    Examples:

      modkit data record "004822:Fallout4.esm"

      modkit data record "004822:Fallout4.esm" --content
    """
    game, fmt, db_dir = _ctx_args(ctx)
    result = cd.get_record(form_key=form_key, include_content=include_content, game=game, db_dir=db_dir)
    output(result, fmt)


@data.command()
@click.argument("form_key")
@click.option("-t", "--type", "record_type", default="", help="Filter by record type")
@result_options
@click.pass_context
def refs(ctx, form_key, record_type, max_results):
    """Find all records referencing a FormKey.

    Examples:

      modkit data refs "067384:Fallout4.esm"

      modkit data refs "067384:Fallout4.esm" --type Weapons
    """
    game, fmt, db_dir = _ctx_args(ctx)
    result = cd.get_references(form_key=form_key, record_type=record_type, max_results=max_results, game=game, db_dir=db_dir)
    output(result, fmt)


@data.command()
@click.argument("editor_id")
@click.pass_context
def lookup(ctx, editor_id):
    """Look up records by EditorID (case-insensitive).

    Examples:

      modkit data lookup WorkbenchChemistry
    """
    game, fmt, db_dir = _ctx_args(ctx)
    result = cd.lookup_editor_id(editor_id=editor_id, game=game, db_dir=db_dir)
    output(result, fmt)


@data.command()
@click.argument("keyword")
@click.option("-t", "--type", "record_type", default="", help="Filter by record type")
@result_options
@click.pass_context
def keyword(ctx, keyword, record_type, max_results):
    """Find records with a specific keyword.

    Examples:

      modkit data keyword HasReceiver

      modkit data keyword HasReceiver --type Weapons
    """
    game, fmt, db_dir = _ctx_args(ctx)
    result = cd.search_by_keyword(keyword=keyword, record_type=record_type, max_results=max_results, game=game, db_dir=db_dir)
    output(result, fmt)


@data.command()
@click.argument("form_key")
@click.pass_context
def keywords(ctx, form_key):
    """Get all keywords for a record, resolved to EditorIDs.

    Examples:

      modkit data keywords "004822:Fallout4.esm"
    """
    game, fmt, db_dir = _ctx_args(ctx)
    result = cd.resolve_keywords(form_key=form_key, game=game, db_dir=db_dir)
    output(result, fmt)


@data.command("count-refs")
@click.argument("form_key")
@click.pass_context
def count_refs(ctx, form_key):
    """Count references to a FormKey (fast).

    Examples:

      modkit data count-refs "067384:Fallout4.esm"
    """
    game, fmt, db_dir = _ctx_args(ctx)
    result = cd.count_references(form_key=form_key, game=game, db_dir=db_dir)
    output(result, fmt)


@data.command()
@click.argument("name")
@click.option("--script-type", default="", help="Filter by parent script (e.g. Actor)")
@click.pass_context
def function(ctx, name, script_type):
    """Look up a Papyrus function by name.

    Examples:

      modkit data function AddItem

      modkit data function AddItem --script-type Actor
    """
    game, fmt, db_dir = _ctx_args(ctx)
    result = cd.get_function(function_name=name, script_type=script_type, game=game, db_dir=db_dir)
    output(result, fmt)


@data.command()
@click.argument("script_type")
@click.pass_context
def functions(ctx, script_type):
    """List all functions for a Papyrus script type.

    Examples:

      modkit data functions Actor
    """
    game, fmt, db_dir = _ctx_args(ctx)
    result = cd.list_functions(script_type=script_type, game=game, db_dir=db_dir)
    output(result, fmt)


@data.command()
@click.argument("script_type")
@click.pass_context
def api(ctx, script_type):
    """Get full API page for a Papyrus script type.

    Examples:

      modkit data api Actor
    """
    game, fmt, db_dir = _ctx_args(ctx)
    result = cd.get_script_api(script_type=script_type, game=game, db_dir=db_dir)
    output(result, fmt)


@data.command()
@click.argument("script_type")
@click.pass_context
def hierarchy(ctx, script_type):
    """Walk the extends chain for a script type.

    Examples:

      modkit data hierarchy Actor
    """
    game, fmt, db_dir = _ctx_args(ctx)
    result = cd.get_script_hierarchy(script_type=script_type, game=game, db_dir=db_dir)
    output(result, fmt)


@data.command()
@click.argument("behavior_id")
@click.pass_context
def behavior(ctx, behavior_id):
    """Get raw XML content of a behavior file.

    Examples:

      modkit data behavior "fo4/UniqueBehaviors/FlamerFX/Behavior"
    """
    game, fmt, db_dir = _ctx_args(ctx)
    result = cd.get_behavior_xml(behavior_id=behavior_id, game=game, db_dir=db_dir)
    output(result, fmt)


@data.command()
@click.argument("commands_json")
@click.pass_context
def batch(ctx, commands_json):
    """Execute multiple queries from JSON.

    Examples:

      modkit data batch '[{"tool":"search","args":{"domain":"records","query":"shotgun"}}]'
    """
    game, fmt, db_dir = _ctx_args(ctx)
    try:
        commands = json.loads(commands_json)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    result = cd.batch(commands=commands, game=game, db_dir=db_dir)
    output(result, fmt)


@data.command()
@click.argument("mod_name")
@click.option("--asset", "asset_path", default="", help="Asset path to trace (partial match OK).")
@click.option("--record", "record_fk", default="", help="FormKey of record to trace (partial match OK).")
@click.pass_context
def trace(ctx, mod_name, asset_path, record_fk):
    """Print provenance ancestry for an asset or record in a converted mod.

    Reads asset_provenance.jsonl / record_provenance.jsonl written alongside
    conversion_log.txt in the mod output folder.

    Examples:

      modkit data trace B21_Converted_meltdown_Batch --asset scorchbeast
      modkit data trace B21_Converted_meltdown_Batch --record 6F5790
    """
    import os

    from app.paths import get_app_root
    mod_dir = str(get_app_root() / "mods" / mod_name)
    if not os.path.isdir(mod_dir):
        print(f"Error: mod directory not found: {mod_dir}", file=sys.stderr)
        sys.exit(1)

    if asset_path:
        prov_file = os.path.join(mod_dir, "asset_provenance.jsonl")
        if not os.path.isfile(prov_file):
            print(f"Error: {prov_file} not found — run conversion first.", file=sys.stderr)
            sys.exit(1)
        query = asset_path.lower()
        matches = []
        with open(prov_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if query in entry.get("asset_path", "").lower():
                    matches.append(entry)
        if not matches:
            print(f"No assets matching '{asset_path}' found in provenance log.")
        else:
            print(f"Found {len(matches)} matching asset(s):\n")
            for m in matches:
                print(f"  asset_path:     {m.get('asset_path')}")
                print(f"  asset_type:     {m.get('asset_type')}")
                print(f"  added_by:       {m.get('added_by_record_eid')} ({m.get('added_by_record_fk')})")
                print(f"  field:          {m.get('added_by_field')}")
                print(f"  walk_depth:     {m.get('walk_depth')}")
                print(f"  walker_pass:    {m.get('walker_pass')}")
                print()

    elif record_fk:
        prov_file = os.path.join(mod_dir, "record_provenance.jsonl")
        if not os.path.isfile(prov_file):
            print(f"Error: {prov_file} not found — run conversion first.", file=sys.stderr)
            sys.exit(1)
        query = record_fk.lower()
        matches = []
        with open(prov_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if query in entry.get("form_key", "").lower() or query in entry.get("editor_id", "").lower():
                    matches.append(entry)
        if not matches:
            print(f"No records matching '{record_fk}' found in provenance log.")
        else:
            print(f"Found {len(matches)} matching record(s):\n")
            for m in matches:
                print(f"  form_key:       {m.get('form_key')}")
                print(f"  editor_id:      {m.get('editor_id')}")
                print(f"  record_type:    {m.get('record_type')}")
                print(f"  added_by:       {m.get('added_by_record_eid')} ({m.get('added_by_record_fk')})")
                print(f"  field:          {m.get('added_by_field')}")
                print(f"  walk_depth:     {m.get('walk_depth')}")
                print(f"  walker_pass:    {m.get('walker_pass')}")
                print()
    else:
        # No filter — show full summary from conversion_log.txt ancestor section
        prov_file = os.path.join(mod_dir, "asset_provenance.jsonl")
        if not os.path.isfile(prov_file):
            print(f"Error: {prov_file} not found — run conversion first.", file=sys.stderr)
            sys.exit(1)
        counts: dict[str, int] = {}
        with open(prov_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                eid = entry.get("added_by_record_eid") or "(unknown)"
                fk = entry.get("added_by_record_fk") or ""
                label = f"{eid} ({fk})" if fk else eid
                counts[label] = counts.get(label, 0) + 1
        print(f"Asset provenance summary for {mod_name}:\n")
        for label, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            flag = "  <-- REVIEW" if count > 10 else ""
            print(f"  {count:4d}  {label}{flag}")
