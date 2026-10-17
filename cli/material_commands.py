"""modkit material — FO4 material upgrades (thin wrapper over material_upgrade_native)."""

from pathlib import Path

import click

from cli._output import output

_CLASS_CHOICES = ("metal", "painted", "wood", "fabric", "stone", "organic", "other", "skin", "grass")


@click.group()
@click.pass_context
def material(ctx):
    """Material tools."""


@material.command("upgrade-v22")
@click.argument("sources", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", "output_dir", type=click.Path(file_okay=False, path_type=Path),
              help="Output mod folder (required unless --dry-run).")
@click.option("--dry-run", is_flag=True, help="Plan only: report per-material decisions, write nothing.")
@click.option("--class", "classes", multiple=True, type=click.Choice(_CLASS_CHOICES),
              help="Material classes to upgrade (repeatable). Default: all except skin and grass.")
@click.option("--metal", "metal_mode", type=click.Choice(("off", "envmap", "mask", "user-mask")), default="off",
              show_default=True, help="off: all dielectric; envmap: metal-cube materials become metal; "
              "mask: per-texel mask from _s.R (low precision); user-mask: <dir>/<diffuse stem>_metal.dds.")
@click.option("--metal-mask-dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--smoothness-gain", type=float, default=1.0, show_default=True)
@click.option("--knee", type=float, default=None, help="Compress smoothness above this value (e.g. 0.5).")
@click.option("--materials/--no-materials", "include_materials", default=True, show_default=True)
@click.option("--nifs/--no-nifs", "include_nifs", default=False, show_default=True,
              help="Also fill slots 8/9 of NIF texture sets that name no .bgsm.")
@click.option("--terrain", "include_terrain", is_flag=True,
              help="Stage the raw terrain layer bank (*_source_{d,n,l,r}.dds) from LTEX/TXST in --plugin and write "
                   "terrain/fo4cs/<worldspace>.btd4 for FO4CS native terrain.")
@click.option("--plugin", "plugins", multiple=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Plugin(s) for --terrain, in load order.")
@click.option("--terrain-size", type=int, default=1024, show_default=True)
@click.option("--worldspace", "worldspaces", multiple=True,
              help="Worldspace editor id(s) to write terrain sidecars for (default: every worldspace with LAND).")
@click.option("--terrain-sidecars/--no-terrain-sidecars", default=True, show_default=True,
              help="With --terrain, write the per-worldspace BTD4 sidecars.")
@click.option("--exclude-file", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Text file of data paths not to upgrade (one per line), e.g. a native replace set.")
@click.option("--prefix", "prefixes", multiple=True, help="Only scan paths under this prefix (materials/weapons/).")
@click.option("--workers", type=int, default=4, show_default=True)
@click.option("--units/--no-units", "with_units", default=False, help="Include every per-unit decision in the output.")
@click.pass_context
def upgrade_v22(ctx, sources, output_dir, dry_run, classes, metal_mode, metal_mask_dir, smoothness_gain, knee,
                include_materials, include_nifs, include_terrain, plugins, terrain_size, worldspaces,
                terrain_sidecars, exclude_file, prefixes, workers, with_units):
    """Upgrade FO4 materials and texture sets to BGSM v22+ (PBR) into a separate output mod.

    SOURCES are Data folders, mod folders or .ba2 files; later ones override earlier ones.
    `_d`/`_n` are never re-encoded; writes `_r` (shared 4x4 BC4 by default), `_l` (BC1, no alpha)
    and v22 BGSMs, plus materialupgrade/upgrade_report.json.
    """
    from creation_lib.material_tools import upgrade_v22 as up

    if not dry_run and output_dir is None:
        raise click.UsageError("--output is required unless --dry-run")
    exclude = []
    if exclude_file:
        exclude = [line.strip() for line in exclude_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    opts = up.UpgradeOptions(
        sources=[str(p.resolve()) for p in sources],
        output=str(output_dir.resolve()) if output_dir else "",
        classes=list(classes) or list(up.DEFAULT_CLASSES),
        metal_mode=metal_mode,
        metal_mask_dir=str(metal_mask_dir.resolve()) if metal_mask_dir else None,
        smoothness_gain=smoothness_gain,
        knee=knee,
        include_materials=include_materials,
        include_nifs=include_nifs,
        include_terrain=include_terrain,
        plugins=[str(p.resolve()) for p in plugins],
        terrain_layer_size=terrain_size,
        terrain_sidecars=terrain_sidecars,
        terrain_worldspaces=list(worldspaces),
        exclude_paths=exclude,
        include_prefixes=list(prefixes),
        workers=workers,
    )
    fmt = ctx.obj["fmt"]

    def progress(done, total, message):
        if fmt not in ("json", "jsonl"):
            click.echo(f"\r{message}: {done}/{total}", nl=False, err=True)
        return True

    report = up.plan(opts) if dry_run else up.run(opts, progress)
    if not dry_run and fmt not in ("json", "jsonl"):
        click.echo("", err=True)
    if not with_units:
        report.pop("units", None)
        report.pop("texture_outputs", None)
        if "result" in report:
            report["result"]["written"] = len(report["result"]["written"])
    output(report, fmt)
