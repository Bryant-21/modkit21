"""modkit swf -- SWF inspection, extraction, and packing commands.

Command surface:
    modkit swf inspect <swf>            # dump SWF structure
    modkit swf extract <swf> -o <dir>   # export shapes as SVGs
    modkit swf pack <swfproj> -o <swf>  # assemble SWF from project
    modkit swf index                    # build shape library from extracted SWFs
    modkit swf symbols list <swf>       # byte-exact SymbolClass export list (native)
    modkit swf symbols inject ...       # splice named symbols src -> dst (native)
    modkit swf abc dump <swf>           # ABC constant-pool string table (class names)
    modkit swf abc markers <swf>        # which canonical marker classes the SWF has
    modkit swf markers build ...        # inject FO76 region marker icons into FO4 SWFs
    modkit swf markers table            # dump the canonical FO76->FO4 marker table

`inspect`/`extract`/`pack` use the pure-Python (byte-lossy) codec for Pip-Boy icon
authoring; `symbols`/`abc`/`markers` use the native byte-exact reader and must be
used for inspecting/editing real menu SWFs.
"""
from __future__ import annotations

import json
from pathlib import Path

import click

from cli._output import JSON_FORMATS, output


@click.group()
def swf():
    """SWF inspection and shape library commands."""


@swf.command()
@click.argument("swf_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def inspect(ctx: click.Context, swf_path: Path):
    """Print summary of SWF structure.

    Shows: version, canvas size, FPS, frame count, shape count,
    sprite count, background color, tag breakdown.
    """
    from creation_lib.swf.parser import parse_swf_file
    from creation_lib.swf.tags import RawTag

    try:
        doc = parse_swf_file(swf_path)
    except Exception as exc:
        click.echo(f"error: failed to parse {swf_path}: {exc}", err=True)
        ctx.exit(2)
        return

    fmt = ctx.obj.get("fmt", "json") if ctx.obj else "json"
    h = doc.header

    # Count tags by type
    tag_counts: dict[str, int] = {}
    for tag in doc.tags:
        name = type(tag).__name__
        tag_counts[name] = tag_counts.get(name, 0) + 1

    summary = {
        "file": str(swf_path),
        "version": h.version,
        "compression": h.compression,
        "canvas": f"{h.frame_size.width_px}x{h.frame_size.height_px}",
        "fps": h.fps,
        "frame_count": h.frame_count,
        "background": doc.background_color.to_hex(),
        "shape_count": len(doc.shapes),
        "sprite_count": len(doc.sprites),
        "total_tags": len(doc.tags),
        "raw_tags": len(doc.raw_tags),
        "tag_breakdown": tag_counts,
    }

    if fmt in JSON_FORMATS:
        output(summary, fmt)
    else:
        click.echo(f"SWF: {swf_path.name}")
        click.echo(f"  Version: {h.version} ({h.compression})")
        click.echo(f"  Canvas:  {h.frame_size.width_px}x{h.frame_size.height_px}")
        click.echo(f"  FPS:     {h.fps}")
        click.echo(f"  Frames:  {h.frame_count}")
        click.echo(f"  BG:      {doc.background_color.to_hex()}")
        click.echo(f"  Shapes:  {len(doc.shapes)}")
        click.echo(f"  Sprites: {len(doc.sprites)}")
        click.echo(f"  Tags:    {len(doc.tags)} ({len(doc.raw_tags)} unparsed)")
        for name, count in sorted(tag_counts.items()):
            click.echo(f"    {name}: {count}")


@swf.command()
@click.argument("swf_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=None,
              help="Output directory for SVGs (default: <swf_name>_shapes/)")
@click.pass_context
def extract(ctx: click.Context, swf_path: Path, output: Path | None):
    """Export all shapes from a SWF as individual SVG files."""
    from creation_lib.swf.parser import parse_swf_file
    from creation_lib.swf.svg_io import shape_to_svg

    try:
        doc = parse_swf_file(swf_path)
    except Exception as exc:
        click.echo(f"error: failed to parse {swf_path}: {exc}", err=True)
        ctx.exit(2)
        return

    out_dir = output or (swf_path.parent / f"{swf_path.stem}_shapes")
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for shape_id, shape in doc.shapes.items():
        svg = shape_to_svg(shape)
        svg_path = out_dir / f"shape_{shape_id}.svg"
        svg_path.write_text(svg, encoding="utf-8")
        count += 1

    click.echo(f"Extracted {count} shapes to {out_dir}")


@swf.command()
@click.argument("project_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), required=True,
              help="Output SWF path")
@click.pass_context
def pack(ctx: click.Context, project_path: Path, output: Path):
    """Assemble a SWF from a .swfproj project file."""
    from creation_lib.swf.writer import write_swf_file
    from creation_lib.swf.parser import SwfDocument, SwfHeader
    from creation_lib.swf.types import RECT, RGBA
    from creation_lib.swf.tags import (
        FileAttributesTag, SetBackgroundColorTag, ShowFrameTag, EndTag,
    )
    from creation_lib.swf.timeline import Timeline

    try:
        proj = json.loads(project_path.read_text(encoding="utf-8"))
    except Exception as exc:
        click.echo(f"error: failed to read project: {exc}", err=True)
        ctx.exit(2)
        return

    canvas = proj.get("canvas", [550, 400])
    fps = proj.get("fps", 30)
    bg = proj.get("background", "#333333")

    doc = SwfDocument(
        header=SwfHeader(
            compression="CWS",
            version=17,
            file_length=0,
            frame_size=RECT(xmin=0, xmax=canvas[0] * 20, ymin=0, ymax=canvas[1] * 20),
            fps=fps,
            frame_count=1,
        ),
        background_color=RGBA.from_hex(bg),
        main_timeline=Timeline(),
    )
    doc.tags = [
        FileAttributesTag(),
        SetBackgroundColorTag(color=doc.background_color),
        ShowFrameTag(),
        EndTag(),
    ]
    doc.header.frame_count = 1

    write_swf_file(doc, output)
    click.echo(f"Packed SWF: {output}")


@swf.command("index")
@click.pass_context
def index_cmd(ctx: click.Context):
    """Build shape library from extracted FO4 SWF files.

    Equivalent to: modkit index build --domain swf
    """
    from app.paths import get_app_root, get_db_dir
    from cli.index_commands import _resolve_game_paths
    from creation_lib.db.index_builder import build_domain_index
    game = ctx.obj.get("game", "fo4") if ctx.obj else "fo4"
    extracted_dir, game_dir = _resolve_game_paths(game)
    try:
        build_domain_index(
            game,
            "swf",
            extracted_dir=extracted_dir,
            game_dir=game_dir,
            project_root=get_app_root(),
            db_dir=get_db_dir(),
            on_progress=click.echo,
        )
    except Exception as exc:
        click.echo(f"error: {exc}", err=True)
        ctx.exit(2)


@swf.group()
def symbols():
    """Byte-exact SymbolClass inspection / injection (native splicer)."""


@symbols.command("list")
@click.argument("swf_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def symbols_list(ctx: click.Context, swf_path: Path):
    """List every SymbolClass export (character_id, name) in file order.

    Unlike `swf inspect`, this reads via the native byte-exact splitter — the
    same view FO4 uses to bind REFR.TNAM marker types to icons.
    """
    from creation_lib.swf import native_runtime

    try:
        syms = native_runtime.list_symbols(swf_path.read_bytes())
    except Exception as exc:
        click.echo(f"error: {exc}", err=True)
        ctx.exit(2)
        return

    fmt = ctx.obj.get("fmt", "json") if ctx.obj else "json"
    if fmt in JSON_FORMATS:
        output([{"character_id": cid, "name": name} for cid, name in syms], fmt)
    else:
        for cid, name in syms:
            click.echo(f"  {cid:>5}  {name}")
        click.echo(f"{len(syms)} symbols")


@symbols.command("inject")
@click.option("--src", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Donor SWF (e.g. FO76 mapmarkerlibrary.swf)")
@click.option("--dst", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Destination SWF to inject into")
@click.option("-n", "--name", "names", multiple=True, required=True,
              help="SymbolClass export name to inject (repeatable)")
@click.option("-o", "--output", required=True, type=click.Path(path_type=Path),
              help="Output SWF path")
@click.pass_context
def symbols_inject(ctx: click.Context, src: Path, dst: Path, names: tuple[str, ...], output: Path):
    """Splice named symbols (with their full character closures) from src into dst."""
    from creation_lib.swf import native_runtime

    try:
        out = native_runtime.inject_symbols(src.read_bytes(), dst.read_bytes(), list(names))
    except Exception as exc:
        click.echo(f"error: {exc}", err=True)
        ctx.exit(2)
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(out)
    click.echo(f"Injected {len(names)} symbol(s) into {output.name} ({len(out)} bytes)")


@swf.group()
def abc():
    """ActionScript Byte Code inspection (read-only constant-pool view)."""


@abc.command("dump")
@click.argument("swf_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--strings/--no-strings", default=False, help="Print the full string table")
@click.pass_context
def abc_dump(ctx: click.Context, swf_path: Path, strings: bool):
    """Dump each DoABC tag's constant-pool string table (where class names live)."""
    from creation_lib.swf import native_runtime

    try:
        pools = native_runtime.abc_string_pools(swf_path.read_bytes())
    except Exception as exc:
        click.echo(f"error: {exc}", err=True)
        ctx.exit(2)
        return

    report = []
    for code, minor, major, ic, uc, dc, strs in pools:
        entry = {
            "tag_code": code,
            "version": f"{major}.{minor}",
            "int_count": ic,
            "uint_count": uc,
            "double_count": dc,
            "string_count": len(strs),
        }
        if strings:
            entry["strings"] = strs
        report.append(entry)
    fmt = ctx.obj.get("fmt", "json") if ctx.obj else "json"
    output(report, fmt if fmt in JSON_FORMATS else "json")


@abc.command("markers")
@click.argument("swf_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def abc_markers(ctx: click.Context, swf_path: Path):
    """Report which canonical FO76 marker export names already exist as AS3 classes
    in the SWF's ABC (i.e. already have a backing class)."""
    from creation_lib.swf.markers import abc_class_name_presence, marker_icon_table

    try:
        table = marker_icon_table()
        presence = abc_class_name_presence(swf_path.read_bytes(), table)
    except Exception as exc:
        click.echo(f"error: {exc}", err=True)
        ctx.exit(2)
        return

    present = sorted(n for n, ok in presence.items() if ok)
    absent = sorted(n for n, ok in presence.items() if not ok)
    fmt = ctx.obj.get("fmt", "json") if ctx.obj else "json"
    if fmt in JSON_FORMATS:
        output({"total": len(presence), "present": present, "absent": absent}, fmt)
    else:
        click.echo(f"present ({len(present)}): {', '.join(present) or '-'}")
        click.echo(f"absent  ({len(absent)}): {', '.join(absent) or '-'}")


@swf.group()
def markers():
    """FO76 -> FO4 map-marker icon injection (UI-integration phase)."""


@markers.command("table")
@click.pass_context
def markers_table(ctx: click.Context):
    """Dump the canonical FO76->FO4 marker icon table (fo76_type, fo4_byte, symbol)."""
    from creation_lib.swf.markers import marker_icon_table

    try:
        table = marker_icon_table()
    except Exception as exc:
        click.echo(f"error: {exc}", err=True)
        ctx.exit(2)
        return

    fmt = ctx.obj.get("fmt", "json") if ctx.obj else "json"
    if fmt in JSON_FORMATS:
        output(
            [
                {
                    "fo76_type": m.fo76_type,
                    "fo4_byte": m.fo4_byte,
                    "symbol": m.symbol,
                    "source_symbol": m.source_symbol,
                }
                for m in table
            ],
            fmt,
        )
    else:
        for m in table:
            renamed = "" if m.symbol == m.source_symbol else f"  (from {m.source_symbol})"
            click.echo(f"  {m.fo76_type:>3} -> {m.fo4_byte:>3}  {m.symbol}{renamed}")
        click.echo(f"{len(table)} icons")


@markers.command("build")
@click.option("--fo76-lib", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="FO76 mapmarkerlibrary.swf (symbol donor)")
@click.option("--fo4-swf", "fo4_swfs", multiple=True, required=True,
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="FO4 menu SWF to inject into (repeatable)")
@click.option("-o", "--output", "out_dir", required=True, type=click.Path(path_type=Path),
              help="Output directory for injected SWFs + marker_injection.json")
@click.pass_context
def markers_build(ctx: click.Context, fo76_lib: Path, fo4_swfs: tuple[Path, ...], out_dir: Path):
    """Inject all 42 FO76 region marker icons into each FO4 menu SWF (deterministic)."""
    from creation_lib.swf.markers import build_marker_swfs

    try:
        summary = build_marker_swfs(fo76_lib, list(fo4_swfs), out_dir)
    except Exception as exc:
        click.echo(f"error: {exc}", err=True)
        ctx.exit(2)
        return

    fmt = ctx.obj.get("fmt", "json") if ctx.obj else "json"
    output(summary, fmt if fmt in JSON_FORMATS else "json")
