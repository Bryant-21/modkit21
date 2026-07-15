"""modkit nif — NIF mesh manipulation CLI commands."""

import json
import os
import sys

import click

from cli._output import output
from cli._session import (
    open_session, load_session, save_session, close_session, cleanup_stale,
)

# Lazy imports to avoid slow startup
_nif_loaded = False


def _ensure_nif():
    global _nif_loaded
    if not _nif_loaded:
        _nif_loaded = True


def _error(msg: str) -> dict:
    return {"error": msg}


def _load_nif_or_error(session_id: str):
    """Load NIF from session, return (nif, original_path) or print error and exit."""
    try:
        return load_session(session_id)
    except FileNotFoundError:
        print(f"Error: No session '{session_id}'", file=sys.stderr)
        sys.exit(1)


@click.group()
@click.option("--format", "fmt", type=click.Choice(["json", "pretty", "compact", "table"]), default=None, help="Output format (overrides global --format).")
@click.pass_context
def nif(ctx, fmt):
    """Inspect and edit NIF mesh files."""
    _ensure_nif()
    cleanup_stale()
    if fmt is not None:
        ctx.obj["fmt"] = fmt


@nif.command("open")
@click.argument("path")
@click.pass_context
def open_cmd(ctx, path):
    """Open a NIF file for editing. Returns session_id.

    Examples:

      modkit nif open meshes/weapon.nif
    """
    from creation_lib.nif.nif_file import NifFile

    fmt = ctx.obj["fmt"]
    path = os.path.normpath(os.path.abspath(path))
    if not os.path.isfile(path):
        output(_error(f"File not found: {path}"), fmt)
        return

    try:
        nif_file = NifFile.load(path)
        sid = open_session(nif_file, path)
        h = nif_file.header
        root = nif_file.blocks[0] if nif_file.blocks else None
        type_counts: dict[str, int] = {}
        for b in nif_file.blocks:
            type_counts[b.type_name] = type_counts.get(b.type_name, 0) + 1
        output({
            "session_id": sid,
            "version": f"{h.version[0]}.{h.version[1]}.{h.version[2]}.{h.version[3]}",
            "bs_version": h.bs_version,
            "block_count": len(nif_file.blocks),
            "root": {
                "id": root.block_id if root else -1,
                "type": root.type_name if root else "",
                "name": root.get_field("Name") or "" if root else "",
            },
            "block_types": type_counts,
        }, fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command("new")
@click.option("--game", default="FO4", help="Target game for NIF header (default FO4)")
@click.argument("path")
@click.pass_context
def new_cmd(ctx, game, path):
    """Create a new empty NIF file. Returns session_id.

    Examples:

      modkit nif new meshes/my_weapon.nif
    """
    from creation_lib.nif.nif_file import NifFile

    fmt = ctx.obj["fmt"]
    try:
        nif_file = NifFile.new(game)
        sid = open_session(nif_file, os.path.normpath(os.path.abspath(path)))
        output({
            "session_id": sid,
            "game": game,
            "root_block_id": 0,
            "path": path,
        }, fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command("save")
@click.argument("session_id")
@click.option("--path", default="", help="Save to this path instead of original")
@click.pass_context
def save_cmd(ctx, session_id, path):
    """Save a NIF session to disk.

    Examples:

      modkit nif save abc123

      modkit nif save abc123 --path output/weapon.nif
    """
    fmt = ctx.obj["fmt"]
    nif_file, original_path = _load_nif_or_error(session_id)
    try:
        save_path = path or original_path
        if not save_path:
            output(_error("No path specified and no original path in session"), fmt)
            return
        save_path = os.path.normpath(os.path.abspath(save_path))
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        nif_file.save(save_path)
        output({"saved": save_path}, fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command("close")
@click.argument("session_id")
@click.pass_context
def close_cmd(ctx, session_id):
    """Close a NIF session and free resources.

    Examples:

      modkit nif close abc123
    """
    fmt = ctx.obj["fmt"]
    if close_session(session_id):
        output({"closed": session_id}, fmt)
    else:
        output(_error(f"No session '{session_id}'"), fmt)


@nif.command()
@click.option("--path", default="", help="NIF file path (stateless, no session needed)")
@click.option("--session", "session_id", default="", help="Session ID (for open sessions)")
@click.option("--block", "block_id", default=-1, type=int, help="Block ID (-1 for hierarchy tree)")
@click.option("--format", "fmt", type=click.Choice(["json", "pretty", "compact", "table"]), default=None, help="Output format (overrides global --format).")
@click.pass_context
def inspect(ctx, path, session_id, block_id, fmt):
    """Inspect a NIF file or specific block.

    Use --path for read-only inspection (no session needed).
    Use --session for inspecting during an edit session.

    Examples:

      modkit nif inspect --path meshes/weapon.nif

      modkit nif inspect --path meshes/weapon.nif --block 0

      modkit nif inspect --session abc123 --block 5
    """
    from creation_lib.nif.nif_file import NifFile
    from creation_lib.nif.types import to_json

    effective_fmt = fmt if fmt is not None else ctx.obj["fmt"]
    try:
        if path:
            p = os.path.normpath(os.path.abspath(path))
            if not os.path.isfile(p):
                output(_error(f"File not found: {p}"), effective_fmt)
                return
            nif_file = NifFile.load(p)
        elif session_id:
            nif_file, _ = _load_nif_or_error(session_id)
        else:
            output(_error("Provide either --path (stateless) or --session (open session)"), effective_fmt)
            return

        result = _inspect_nif(nif_file, block_id)
        output(result, effective_fmt)
    except Exception as e:
        output(_error(str(e)), effective_fmt)


def _inspect_nif(nif_file, block_id: int) -> dict:
    """Core inspect logic."""
    from creation_lib.nif.types import to_json

    if block_id == -1:
        return nif_file.get_hierarchy()

    block = nif_file.get_block(block_id)
    if block is None:
        return _error(f"Block {block_id} not found (0-{len(nif_file.blocks)-1})")

    from creation_lib.nif.schema import build_field_def_map
    schema = nif_file.schema
    field_defs = build_field_def_map(schema, block.type_name)

    display_fields = {}
    for name, val in block.fields:
        display_name = name.split(":")[0] if ":" in name else name
        fdef = field_defs.get(name)
        if fdef and fdef.type in schema.enums and isinstance(val, int):
            enum_def = schema.enums[fdef.type]
            enum_name = next((o.name for o in enum_def.options if o.value == val), str(val))
            display_fields[display_name] = enum_name
        elif fdef and fdef.type in schema.bitflags and isinstance(val, int):
            bf_def = schema.bitflags[fdef.type]
            flags = [o.name for o in bf_def.options if val & (1 << o.value)]
            display_fields[display_name] = flags
        else:
            display_fields[display_name] = to_json(val)

    return {"block_id": block_id, "type": block.type_name, "fields": display_fields}


@nif.command()
@click.argument("session_id")
@click.argument("block_id", type=int)
@click.argument("fields_json")
@click.pass_context
def modify(ctx, session_id, block_id, fields_json):
    """Update fields on an existing block.

    FIELDS_JSON: JSON dict of field_name -> new_value.

    Examples:

      modkit nif modify abc123 0 '{"Name": "MyWeapon"}'
    """
    fmt = ctx.obj["fmt"]
    nif_file, _ = _load_nif_or_error(session_id)
    try:
        fields = json.loads(fields_json)
        block = nif_file.get_block(block_id)
        if block is None:
            output(_error(f"Block {block_id} not found"), fmt)
            return
        for name, val in fields.items():
            block.set_field(name, val)
        save_session(session_id, nif_file)
        output({"block_id": block_id, "updated_fields": list(fields.keys())}, fmt)
    except json.JSONDecodeError as e:
        output(_error(f"Invalid JSON: {e}"), fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command()
@click.argument("source_session")
@click.argument("block_ids")
@click.argument("target_session")
@click.option("--attach-to", default=-1, type=int, help="Attach copied blocks as children of this block")
@click.pass_context
def copy(ctx, source_session, block_ids, target_session, attach_to):
    """Copy blocks (with dependency trees) between NIFs.

    BLOCK_IDS: comma-separated block IDs (e.g. "3,5,7").

    Handles Ref/Ptr remapping automatically. Copies BSTriShapes with their
    materials, textures, skin data, and animation controllers.

    Examples:

      modkit nif copy src123 "3,5" tgt456

      modkit nif copy src123 "3" tgt456 --attach-to 0
    """
    from creation_lib.nif.operations.copy import copy_blocks as ops_copy_blocks

    fmt = ctx.obj["fmt"]
    src_nif, _ = _load_nif_or_error(source_session)
    tgt_nif, _ = _load_nif_or_error(target_session)
    try:
        ids = [int(x.strip()) for x in block_ids.split(",")]
        id_map = ops_copy_blocks(
            src_nif, ids, tgt_nif,
            attach_to=attach_to if attach_to >= 0 else None,
        )
        save_session(target_session, tgt_nif)
        output({"id_map": {str(k): v for k, v in id_map.items()}}, fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command()
@click.argument("session_id")
@click.argument("type_name")
@click.option("--fields-json", default="{}", help="Initial field values as JSON")
@click.option("--attach-to", default=-1, type=int, help="Add as child of this block")
@click.pass_context
def add(ctx, session_id, type_name, fields_json, attach_to):
    """Create a new block.

    Examples:

      modkit nif add abc123 NiNode

      modkit nif add abc123 BSTriShape --attach-to 0
    """
    fmt = ctx.obj["fmt"]
    nif_file, _ = _load_nif_or_error(session_id)
    try:
        fields = json.loads(fields_json) if fields_json != "{}" else None
        block = nif_file.add_block(type_name, fields)
        if attach_to >= 0:
            parent = nif_file.get_block(attach_to)
            if parent:
                children = parent.get_field("Children")
                if isinstance(children, list):
                    children.append(block.block_id)
                    parent.set_field("Children", children)
                num = parent.get_field("Num Children")
                if isinstance(num, int):
                    parent.set_field("Num Children", num + 1)
        save_session(session_id, nif_file)
        output({"block_id": block.block_id, "type": type_name, "fields": block.to_json()}, fmt)
    except json.JSONDecodeError as e:
        output(_error(f"Invalid JSON: {e}"), fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command()
@click.argument("session_id")
@click.argument("block_ids")
@click.pass_context
def remove(ctx, session_id, block_ids):
    """Remove blocks from a NIF. Updates all Ref/Ptr indices.

    BLOCK_IDS: comma-separated block IDs (e.g. "3,5,7").

    Examples:

      modkit nif remove abc123 "3,5"
    """
    fmt = ctx.obj["fmt"]
    nif_file, _ = _load_nif_or_error(session_id)
    try:
        ids = [int(x.strip()) for x in block_ids.split(",")]
        before = len(nif_file.blocks)
        nif_file.remove_blocks(ids)
        after = len(nif_file.blocks)
        save_session(session_id, nif_file)
        output({"removed": before - after}, fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command()
@click.argument("session_id")
@click.option("--node", "node_block_id", default=0, type=int, help="Node block ID (default 0)")
@click.option(
    "--shape-type", default="convex_hull",
    type=click.Choice([
        "convex_hull", "convex_fit", "box", "sphere", "capsule", "cylinder",
        "list", "auto", "mesh", "compressed_mesh", "auto_compressed_mesh",
    ]),
    help="Collision shape type",
)
@click.option("--source-blocks", default="", help="Comma-separated source block IDs (auto-detect if empty)")
@click.option("--layer", default="STATIC", help="Collision layer")
@click.option("--mass", default=0.0, type=float)
@click.option("--friction", default=0.5, type=float)
@click.option("--restitution", default=0.4, type=float)
@click.option("--radius", default=0.05, type=float)
@click.option("--replace/--no-replace", default=True, help="Replace existing collision")
@click.pass_context
def collision(ctx, session_id, node_block_id, shape_type, source_blocks, layer,
              mass, friction, restitution, radius, replace):
    """Generate collision hierarchy on a node.

    Shape types:
      convex_hull, convex_fit, box, sphere, capsule, cylinder — single convex shape
      list, auto — compound (one hull per mesh component)
      mesh, compressed_mesh — full triangle mesh (FO4: hknpCompressedMeshShape)
      auto_compressed_mesh — simplified triangle mesh capped for compressed mesh

    Examples:

      modkit nif collision abc123

      modkit nif collision abc123 --shape-type box --layer STATIC

      modkit nif collision abc123 --shape-type auto_compressed_mesh --layer CLUTTER

      modkit nif collision abc123 --shape-type compressed_mesh --layer CLUTTER
    """
    from creation_lib.nif.operations.collision import generate_collision as gen_coll
    from creation_lib.core.game_profiles import detect_game

    fmt = ctx.obj["fmt"]
    nif_file, _ = _load_nif_or_error(session_id)
    try:
        source_block_ids = None
        if source_blocks:
            source_block_ids = [int(x.strip()) for x in source_blocks.split(",")]

        profile = getattr(nif_file, 'detected_game', None)
        if profile is None and hasattr(nif_file, 'header'):
            profile = detect_game(nif_file.header.bs_version)

        result = gen_coll(
            nif_file, node_block_id, shape_type=shape_type,
            source_block_ids=source_block_ids, layer=layer,
            mass=mass, friction=friction, restitution=restitution,
            radius=radius, replace=replace, profile=profile,
        )
        save_session(session_id, nif_file)
        output({
            "success": result.success,
            "description": result.description,
            "modified_block_ids": result.modified_block_ids,
            "warnings": result.warnings,
        }, fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command("rm-collision")
@click.argument("session_id")
@click.option("--node", "node_block_id", default=0, type=int, help="Node block ID (default 0)")
@click.pass_context
def rm_collision(ctx, session_id, node_block_id):
    """Remove collision subtree from a node.

    Examples:

      modkit nif rm-collision abc123
    """
    from creation_lib.nif.operations.collision import remove_collision as rem_coll

    fmt = ctx.obj["fmt"]
    nif_file, _ = _load_nif_or_error(session_id)
    try:
        result = rem_coll(nif_file, node_block_id)
        save_session(session_id, nif_file)
        output({
            "success": result.success,
            "description": result.description,
            "warnings": result.warnings,
        }, fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command("strip-all-collision")
@click.argument("path")
@click.option("--output", "output_path", default="", help="Output path. Defaults to overwriting PATH.")
@click.pass_context
def strip_all_collision(ctx, path, output_path):
    """Remove every collision subtree from a NIF file."""
    from creation_lib.nif.nif_file import NifFile

    fmt = ctx.obj["fmt"]
    src = os.path.normpath(os.path.abspath(path))
    dst = os.path.normpath(os.path.abspath(output_path or path))
    if not os.path.isfile(src):
        output(_error(f"File not found: {src}"), fmt)
        return

    try:
        nif_file = NifFile.load(src)
        before = len(nif_file.blocks)
        removed = _strip_all_collision_subtrees(nif_file)
        bsx_cleared = _clear_havok_bsx_flag_if_no_collision(nif_file)
        nif_file.save(dst)
        output({
            "path": src,
            "output": dst,
            "removed_collision_roots": removed,
            "cleared_bsx_flags": bsx_cleared,
            "blocks_before": before,
            "blocks_after": len(nif_file.blocks),
        }, fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command("strip-all-collision-batch")
@click.argument("manifest_path")
@click.option("--jobs", default=0, type=int, show_default=True, help="Parallel NIF jobs. 0 = auto.")
@click.option("--backup-root", default="", help="Optional root for backups of existing output files.")
@click.option("--manifest-out", default="", help="Optional JSON path for the per-file result manifest.")
@click.pass_context
def strip_all_collision_batch(ctx, manifest_path, jobs, backup_root, manifest_out):
    """Remove all collision from many NIFs listed in a JSON manifest.

    The manifest must be a JSON array, or an object with an ``items`` array.
    Each item needs ``source`` and ``output``/``target``. ``model`` is optional
    and is used for backup paths and reporting.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from pathlib import Path
    import shutil

    from creation_lib.nif.nif_file import NifFile

    fmt = ctx.obj["fmt"]
    manifest_file = os.path.normpath(os.path.abspath(manifest_path))
    if not os.path.isfile(manifest_file):
        output(_error(f"Manifest not found: {manifest_file}"), fmt)
        return

    try:
        payload = json.loads(Path(manifest_file).read_text(encoding="utf-8"))
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            output(_error("Manifest must be a JSON array or an object with an items array"), fmt)
            return
    except Exception as e:
        output(_error(f"Could not read manifest: {e}"), fmt)
        return

    job_count = jobs if jobs and jobs > 0 else min(8, max(1, (os.cpu_count() or 1) - 1))
    backup_base = Path(backup_root) if backup_root else None

    def process_one(item):
        model = str(item.get("model") or "")
        source = item.get("source")
        output_path = item.get("output") or item.get("target")
        if not source or not output_path:
            return {"model": model, "source": source or "", "output": output_path or "", "success": False, "error": "missing source/output"}
        src = Path(source)
        dst = Path(output_path)
        if not src.is_file():
            return {"model": model, "source": str(src), "output": str(dst), "success": False, "error": "source missing"}
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            backup = ""
            if backup_base is not None and dst.exists():
                rel = Path(model.replace("\\", os.sep).replace("/", os.sep)) if model else Path(dst.name)
                backup_path = backup_base / rel
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                if not backup_path.exists():
                    shutil.copy2(dst, backup_path)
                backup = str(backup_path)

            nif_file = NifFile.load(str(src))
            blocks_before = len(nif_file.blocks)
            removed = _strip_all_collision_subtrees(nif_file)
            bsx_cleared = _clear_havok_bsx_flag_if_no_collision(nif_file)
            has_collision = _has_havok_collision_blocks(nif_file)
            nif_file.save(str(dst))
            return {
                "model": model,
                "source": str(src),
                "output": str(dst),
                "backup": backup,
                "success": not has_collision,
                "removed_collision_roots": removed,
                "cleared_bsx_flags": bsx_cleared,
                "blocks_before": blocks_before,
                "blocks_after": len(nif_file.blocks),
                "error": "collision remains after strip" if has_collision else "",
            }
        except Exception as exc:
            return {"model": model, "source": str(src), "output": str(dst), "success": False, "error": str(exc)}

    results = []
    completed = 0
    with ThreadPoolExecutor(max_workers=job_count) as executor:
        futures = [executor.submit(process_one, item) for item in items]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            completed += 1
            if completed == len(futures) or completed % 25 == 0:
                click.echo(
                    f"strip-all-collision-batch: completed {completed}/{len(futures)} errors={sum(1 for row in results if not row.get('success'))}",
                    err=True,
                )

    results.sort(key=lambda row: str(row.get("model") or row.get("output") or ""))
    if manifest_out:
        out_path = Path(manifest_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    summary = {
        "count": len(results),
        "success": sum(1 for row in results if row.get("success")),
        "errors": [row for row in results if not row.get("success")],
        "manifest_out": manifest_out,
        "jobs": job_count,
    }
    output(summary, fmt)


def _find_model_path(obj):
    """Recursively locate the first .nif model path in an authoring-record dict."""
    if isinstance(obj, str):
        return obj if obj.lower().endswith(".nif") else None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "model" in str(k).lower():
                hit = _find_model_path(v)
                if hit:
                    return hit
        for v in obj.values():
            hit = _find_model_path(v)
            if hit:
                return hit
    if isinstance(obj, list):
        for v in obj:
            hit = _find_model_path(v)
            if hit:
                return hit
    return None


def _normalize_model_filter(model: str) -> str:
    text = str(model or "").replace("\\", "/").strip().lstrip("/")
    if text.lower().startswith("meshes/"):
        text = text[7:]
    return text.lower()


def _strip_all_collision_subtrees(nif_file) -> int:
    """Remove every collision subtree in the NIF. Re-scans after each removal
    because remove_collision shifts block indices. Returns the count removed."""
    from creation_lib.nif.operations.collision import remove_collision, _find_collision_object

    removed = 0
    for _ in range(64):
        target = None
        for bid in range(len(nif_file.blocks)):
            if _find_collision_object(nif_file, bid) is not None:
                target = bid
                break
        if target is None:
            break
        result = remove_collision(nif_file, target)
        if not getattr(result, "success", False):
            break
        removed += 1
    return removed


def _has_havok_collision_blocks(nif_file) -> bool:
    return any(getattr(block, "type_name", "").startswith("bhk") for block in nif_file.blocks)


def _clear_havok_bsx_flag_if_no_collision(nif_file) -> int:
    if _has_havok_collision_blocks(nif_file):
        return 0
    cleared = 0
    for block in nif_file.blocks:
        if getattr(block, "type_name", "") != "BSXFlags":
            continue
        value = block.get_field("Integer Data")
        if not isinstance(value, int) or (value & 0x02) == 0:
            continue
        block.set_field("Integer Data", value & ~0x02)
        cleared += 1
    return cleared


@nif.command("port-cell-nifs")
@click.argument("plugin_path")
@click.argument("cell_id")
@click.option("--base-type", "base_types", multiple=True, required=True, help="Base record signature(s) whose placed NIFs to port, e.g. MISC. Repeatable.")
@click.option("--source-dir", required=True, help="Source-game extracted root (contains Meshes/). Source NIF = <source-dir>/Meshes/<model>.")
@click.option("--output-dir", required=True, help="Target Data root. Writes <output-dir>/Meshes/<model> as a loose override.")
@click.option("--source-game", default="fo76", show_default=True)
@click.option("--target-game", default="fo4", show_default=True)
@click.option("--strip-collision", is_flag=True, default=False, help="Remove ALL collision from each converted NIF (debug: isolate whether converted collision freezes/crashes a cell).")
@click.option("--include-external", is_flag=True, default=False, help="Also port bases that live in a master (default: only this plugin's own bases).")
@click.option("--model", "model_filters", multiple=True, help="Only convert matching model path(s). Repeatable; accepts paths with or without Meshes/.")
@click.option("--jobs", default=0, type=int, show_default=True, help="Parallel NIF conversion jobs. 0 = auto.")
@click.pass_context
def port_cell_nifs(ctx, plugin_path, cell_id, base_types, source_dir, output_dir, source_game, target_game, strip_collision, include_external, model_filters, jobs):
    """Convert a cell's placed base NIFs from source->target game and deploy them loose.

    Enumerates CELL_ID's placed children whose NAME base resolves to one of --base-type,
    reads each unique base's model path, converts the source NIF to the target game, and
    writes it under <output-dir>/Meshes/<model> as a loose override. With --strip-collision
    every converted NIF has all collision removed -- a fast way to isolate whether the
    converted collision is what freezes/crashes a cell.

    Example:

      modkit --game fo4 nif port-cell-nifs mods/SeventySix/SeventySix.esm 62781C
        --base-type MISC --source-dir extracted/fo76
        --output-dir "N:/Steam Games/steamapps/common/Fallout 4/Data" --strip-collision
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from pathlib import Path

    from cli.esp_commands import _load_plugin, _resolve_cell_object_id
    from creation_lib.esp import native_runtime as esp_nr
    from creation_lib.nif import native_runtime as nif_nr

    fmt = ctx.obj["fmt"]
    wanted = {t.strip().upper() for t in base_types}
    wanted_models = {_normalize_model_filter(model) for model in model_filters}
    job_count = jobs if jobs and jobs > 0 else min(8, max(1, (os.cpu_count() or 1) - 1))
    src_root = Path(source_dir)
    out_root = Path(output_dir)

    models: dict[str, str] = {}
    base_form_keys: list[str] = []
    seen_base_form_keys: set[str] = set()
    with _load_plugin(Path(plugin_path), game=ctx.obj.get("game"), strings_dir=None, language=None, backend="auto") as plugin:
        handle = getattr(plugin, "_rust_handle", None)
        if handle is None:
            raise click.ClickException("port-cell-nifs requires the native ESP backend.")
        own = plugin.plugin_name.lower()
        coid = _resolve_cell_object_id(handle, plugin, cell_id)
        for child in esp_nr.plugin_handle_collect_cell_children(handle, coid):
            refs = esp_nr.plugin_handle_get_referenced_form_keys_by_subrecord(handle, child.get("form_key", ""), "NAME")
            bfk = refs[0] if refs else None
            if not bfk:
                continue
            if (not include_external) and bfk.split(":", 1)[0].lower() != own:
                continue
            if bfk in seen_base_form_keys:
                continue
            seen_base_form_keys.add(bfk)
            base_form_keys.append(bfk)

        click.echo(
            f"port-cell-nifs: found {len(base_form_keys)} unique placed base FormKeys; collecting NIF assets...",
            err=True,
        )
        assets = esp_nr.plugin_handle_collect_assets(
            [handle],
            [],
            asset_kinds=["nif"],
            signatures=sorted(wanted),
            form_keys=base_form_keys,
        )
        for asset in assets:
            model = asset.get("source_path", "")
            if model:
                models.setdefault(model, asset.get("source_form_key", ""))

    if wanted_models:
        models = {
            model: oid
            for model, oid in models.items()
            if _normalize_model_filter(model) in wanted_models
        }
    matched_models = {_normalize_model_filter(model) for model in models}
    missing_model_filters = sorted(wanted_models - matched_models)

    click.echo(
        f"port-cell-nifs: converting {len(models)} unique NIF(s) with {job_count} job(s)"
        + (" and stripping collision" if strip_collision else ""),
        err=True,
    )

    def convert_one(item):
        model, oid = item
        rel = model.replace("/", os.sep).replace("\\", os.sep).lstrip(os.sep)
        if rel.lower().startswith("meshes" + os.sep):
            rel = rel[len("meshes") + 1:]
        src = src_root / "Meshes" / rel
        dst = out_root / "Meshes" / rel
        if not src.is_file():
            return {"model": model, "owner": oid, "converted": False, "stripped": 0, "error": f"source NIF missing: {src}"}
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            report = nif_nr.convert_nif_file_raw(
                str(src), str(dst), source_game, target_game, None,
                {
                    "source_path": model,
                    "addon_index_map": {},
                    "asset_prefix": "",
                },
            )
            if not report.get("supported"):
                return {"model": model, "owner": oid, "converted": False, "stripped": 0, "error": "; ".join(report.get("errors", []) or ["unsupported"])}
            n_removed = 0
            if strip_collision:
                from creation_lib.nif.nif_file import NifFile

                nif_file = NifFile.load(str(dst))
                n_removed = _strip_all_collision_subtrees(nif_file)
                nif_file.save(str(dst))
            return {"model": model, "owner": oid, "converted": True, "stripped": n_removed, "error": ""}
        except Exception as exc:
            return {"model": model, "owner": oid, "converted": False, "stripped": 0, "error": str(exc)}

    converted = 0
    stripped = 0
    errors: list[dict] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=job_count) as executor:
        futures = [executor.submit(convert_one, item) for item in models.items()]
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            if result["converted"]:
                converted += 1
            if result["stripped"]:
                stripped += 1
            if result["error"]:
                errors.append({"model": result["model"], "owner": result["owner"], "error": result["error"]})
            if completed == len(futures) or completed % 10 == 0:
                click.echo(
                    f"port-cell-nifs: completed {completed}/{len(futures)} converted={converted} errors={len(errors)}",
                    err=True,
                )

    result = {
        "cell": cell_id,
        "base_types": sorted(wanted),
        "model_filters": sorted(wanted_models),
        "missing_model_filters": missing_model_filters,
        "jobs": job_count,
        "unique_models": len(models),
        "converted": converted,
        "strip_collision": strip_collision,
        "stripped_collision": stripped,
        "error_count": len(errors),
        "errors": errors[:25],
    }
    output(result, fmt)
    if missing_model_filters or errors:
        problems = []
        if missing_model_filters:
            problems.append(f"{len(missing_model_filters)} model filter(s) did not match placed NIFs")
        if errors:
            problems.append(f"{len(errors)} NIF conversion(s) failed")
        raise click.ClickException("; ".join(problems))


@nif.command("auto-skin")
@click.argument("session_id")
@click.option("--shape", "shape_id", default=0, type=int, help="BSTriShape block ID")
@click.option("--reference", "reference_path", default="", help="Path to reference body NIF")
@click.option("--method", default="hybrid", type=click.Choice(["barycentric", "proximity", "hybrid"]))
@click.option("--game", default="fo4", help="Target game for reference body")
@click.option("--gender", default="female", type=click.Choice(["male", "female"]))
@click.pass_context
def auto_skin(ctx, session_id, shape_id, reference_path, method, game, gender):
    """Auto-skin a mesh using reference body weights.

    Examples:

      modkit nif auto-skin abc123

      modkit nif auto-skin abc123 --shape 3 --method barycentric --gender male
    """
    from cli._nif_skinning import auto_skin as do_auto_skin

    fmt = ctx.obj["fmt"]
    nif_file, original_path = _load_nif_or_error(session_id)
    try:
        result = do_auto_skin(
            nif_file, shape_id=shape_id,
            reference_path=reference_path, method=method,
            game=game, gender=gender,
        )
        save_session(session_id, nif_file)
        output(result, fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command()
@click.argument("source_session")
@click.argument("source_shape_id", type=int)
@click.argument("target_session")
@click.argument("target_shape_id", type=int)
@click.option("--method", default="hybrid", type=click.Choice(["barycentric", "proximity", "hybrid"]))
@click.option("--radius", "search_radius", default=10.0, type=float, help="Search radius for proximity method")
@click.pass_context
def transfer(ctx, source_session, source_shape_id, target_session, target_shape_id, method, search_radius):
    """Transfer bone weights between shapes.

    Examples:

      modkit nif transfer src123 3 tgt456 5

      modkit nif transfer src123 3 tgt456 5 --method proximity --radius 5.0
    """
    from cli._nif_skinning import transfer_weights as do_transfer

    fmt = ctx.obj["fmt"]
    src_nif, src_path = _load_nif_or_error(source_session)
    tgt_nif, tgt_path = _load_nif_or_error(target_session)
    try:
        result = do_transfer(
            src_nif, source_shape_id,
            tgt_nif, target_shape_id,
            method=method, search_radius=search_radius,
        )
        save_session(target_session, tgt_nif)
        output(result, fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command()
@click.argument("session_id")
@click.option("--shape", "shape_id", default=0, type=int, help="BSTriShape block ID")
@click.option("--reference", "reference_path", default="", help="Reference NIF for from_reference method")
@click.option("--method", default="from_bones", type=click.Choice(["from_bones", "from_reference"]))
@click.pass_context
def partitions(ctx, session_id, shape_id, reference_path, method):
    """Generate dismemberment partition assignments.

    Examples:

      modkit nif partitions abc123

      modkit nif partitions abc123 --shape 3 --method from_reference --reference body.nif
    """
    from cli._nif_skinning import generate_partitions as do_partitions

    fmt = ctx.obj["fmt"]
    nif_file, original_path = _load_nif_or_error(session_id)
    try:
        result = do_partitions(
            nif_file, shape_id=shape_id,
            reference_path=reference_path, method=method,
        )
        output(result, fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command()
@click.argument("session_id")
@click.option("--shape", "shape_id", default=None, type=int, help="Validate weights on one BSTriShape block ID")
@click.pass_context
def validate(ctx, session_id, shape_id):
    """Validate NIF structure, references, materials, and optional shape weights.

    Examples:

      modkit nif validate abc123

      modkit nif validate abc123 --shape 3
    """
    from cli._nif_skinning import validate_weights
    from creation_lib.nif.validation import validate_nif

    fmt = ctx.obj["fmt"]
    nif_file, original_path = _load_nif_or_error(session_id)
    try:
        if shape_id is None:
            result = validate_nif(nif_file)
        else:
            result = validate_weights(nif_file, shape_id=shape_id)
        output(result, fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command()
@click.argument("session_id")
@click.option("--shape", "shape_id", default=0, type=int, help="BSTriShape block ID")
@click.option("--max-bones", default=4, type=int, help="Max bone influences per vertex")
@click.pass_context
def normalize(ctx, session_id, shape_id, max_bones):
    """Normalize bone weights (enforce max bones, sum to 1.0).

    Examples:

      modkit nif normalize abc123

      modkit nif normalize abc123 --shape 3 --max-bones 4
    """
    from cli._nif_skinning import normalize_weights as do_normalize

    fmt = ctx.obj["fmt"]
    nif_file, original_path = _load_nif_or_error(session_id)
    try:
        result = do_normalize(nif_file, shape_id=shape_id, max_bones=max_bones)
        save_session(session_id, nif_file)
        output(result, fmt)
    except Exception as e:
        output(_error(str(e)), fmt)


@nif.command()
@click.argument("commands_json")
@click.pass_context
def batch(ctx, commands_json):
    """Execute multiple NIF commands in one call.

    Commands run sequentially — later commands see earlier changes.

    Examples:

      modkit nif batch '[{"tool":"inspect","args":{"path":"weapon.nif","block_id":0}}]'
    """
    fmt = ctx.obj["fmt"]
    try:
        commands = json.loads(commands_json)
    except json.JSONDecodeError as e:
        output(_error(f"Invalid JSON: {e}"), fmt)
        return

    from creation_lib.nif.nif_file import NifFile
    from creation_lib.nif.types import to_json
    from creation_lib.nif.operations.copy import copy_blocks as ops_copy_blocks
    from creation_lib.nif.operations.collision import (
        generate_collision as gen_coll,
        remove_collision as rem_coll,
    )
    from creation_lib.core.game_profiles import detect_game
    from cli._nif_skinning import (
        auto_skin as do_auto_skin,
        transfer_weights as do_transfer,
        generate_partitions as do_partitions,
        validate_weights as do_validate,
        normalize_weights as do_normalize,
    )

    # Batch dispatch — operates on in-memory NifFile objects via sessions
    sessions: dict[str, dict] = {}

    def _get_or_load(sid: str) -> NifFile:
        if sid not in sessions:
            nif_file, path = load_session(sid)
            sessions[sid] = {"nif": nif_file, "path": path}
        return sessions[sid]["nif"]

    def _batch_inspect(args):
        if args.get("path"):
            p = os.path.normpath(os.path.abspath(args["path"]))
            nif_file = NifFile.load(p)
        elif args.get("session_id"):
            nif_file = _get_or_load(args["session_id"])
        else:
            return _error("Provide path or session_id")
        return _inspect_nif(nif_file, args.get("block_id", -1))

    def _batch_modify(args):
        nif_file = _get_or_load(args["session_id"])
        block = nif_file.get_block(args["block_id"])
        if block is None:
            return _error(f"Block {args['block_id']} not found")
        for name, val in args.get("fields", {}).items():
            block.set_field(name, val)
        return {"block_id": args["block_id"], "updated_fields": list(args.get("fields", {}).keys())}

    def _batch_copy_blocks(args):
        src = _get_or_load(args["source_session"])
        tgt = _get_or_load(args["target_session"])
        attach = args.get("attach_to", -1)
        id_map = ops_copy_blocks(
            src, args["block_ids"], tgt,
            attach_to=attach if attach >= 0 else None,
        )
        return {"id_map": {str(k): v for k, v in id_map.items()}}

    def _batch_add_block(args):
        nif_file = _get_or_load(args["session_id"])
        block = nif_file.add_block(args["type_name"], args.get("fields"))
        attach = args.get("attach_to", -1)
        if attach >= 0:
            parent = nif_file.get_block(attach)
            if parent:
                children = parent.get_field("Children")
                if isinstance(children, list):
                    children.append(block.block_id)
                    parent.set_field("Children", children)
                num = parent.get_field("Num Children")
                if isinstance(num, int):
                    parent.set_field("Num Children", num + 1)
        return {"block_id": block.block_id, "type": args["type_name"], "fields": block.to_json()}

    def _batch_remove_blocks(args):
        nif_file = _get_or_load(args["session_id"])
        before = len(nif_file.blocks)
        nif_file.remove_blocks(args["block_ids"])
        return {"removed": before - len(nif_file.blocks)}

    def _batch_generate_collision(args):
        nif_file = _get_or_load(args["session_id"])
        profile = getattr(nif_file, 'detected_game', None)
        if profile is None and hasattr(nif_file, 'header'):
            profile = detect_game(nif_file.header.bs_version)
        result = gen_coll(
            nif_file, args.get("node_block_id", 0),
            shape_type=args.get("shape_type", "convex_hull"),
            source_block_ids=args.get("source_block_ids"),
            layer=args.get("layer", "STATIC"),
            mass=args.get("mass", 0.0),
            friction=args.get("friction", 0.5),
            restitution=args.get("restitution", 0.4),
            radius=args.get("radius", 0.05),
            replace=args.get("replace", True),
            profile=profile,
        )
        return {"success": result.success, "description": result.description,
                "modified_block_ids": result.modified_block_ids, "warnings": result.warnings}

    def _batch_remove_collision(args):
        nif_file = _get_or_load(args["session_id"])
        result = rem_coll(nif_file, args.get("node_block_id", 0))
        return {"success": result.success, "description": result.description, "warnings": result.warnings}

    def _batch_auto_skin(args):
        nif_file = _get_or_load(args["session_id"])
        return do_auto_skin(nif_file, **{k: v for k, v in args.items() if k != "session_id"})

    def _batch_transfer_weights(args):
        src = _get_or_load(args["source_session"])
        tgt = _get_or_load(args["target_session"])
        return do_transfer(src, args["source_shape_id"], tgt, args["target_shape_id"],
                           method=args.get("method", "hybrid"), search_radius=args.get("search_radius", 10.0))

    def _batch_generate_partitions(args):
        nif_file = _get_or_load(args["session_id"])
        return do_partitions(nif_file, **{k: v for k, v in args.items() if k != "session_id"})

    def _batch_validate_weights(args):
        nif_file = _get_or_load(args["session_id"])
        return do_validate(nif_file, **{k: v for k, v in args.items() if k != "session_id"})

    def _batch_normalize_weights(args):
        nif_file = _get_or_load(args["session_id"])
        return do_normalize(nif_file, **{k: v for k, v in args.items() if k != "session_id"})

    dispatch = {
        "inspect": _batch_inspect,
        "modify": _batch_modify,
        "copy_blocks": _batch_copy_blocks,
        "add_block": _batch_add_block,
        "remove_blocks": _batch_remove_blocks,
        "generate_collision": _batch_generate_collision,
        "remove_collision": _batch_remove_collision,
        "auto_skin": _batch_auto_skin,
        "transfer_weights": _batch_transfer_weights,
        "generate_partitions": _batch_generate_partitions,
        "validate_weights": _batch_validate_weights,
        "normalize_weights": _batch_normalize_weights,
    }

    results = []
    for cmd in commands:
        tool_name = cmd.get("tool", "")
        args = cmd.get("args", {})
        fn = dispatch.get(tool_name)
        if fn is None:
            results.append({"tool": tool_name, "args": args,
                            "result": {"error": f"Unknown tool '{tool_name}'. Valid: {', '.join(sorted(dispatch))}"}})
            continue
        try:
            result = fn(args)
        except Exception as e:
            result = {"error": str(e)}
        results.append({"tool": tool_name, "args": args, "result": result})

    # Save any modified sessions back
    for sid in sessions:
        save_session(sid, sessions[sid]["nif"])

    output(results, fmt)
