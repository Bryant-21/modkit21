"""modkit previs — native previsbine (precombine + previs) checks over a load order."""

from pathlib import Path

import click

from cli._output import output


@click.group()
@click.pass_context
def previs(ctx):
    """Precombine and previs repair tools."""


def _source_options(command):
    options = [
        click.option("--mo2-profile", type=click.Path(exists=True, file_okay=False, path_type=Path),
                     help="MO2 profile folder (<instance>/profiles/<name>)."),
        click.option("--modbox-profile", "modbox_profile", default=None,
                     help="ModBox21 mod-manager profile name or id ('' = first profile)."),
        click.option("--library", type=click.Path(exists=True, file_okay=False, path_type=Path),
                     help="ModBox21 mod-manager library (default: the toolkit's library)."),
        click.option("--against", "against", multiple=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
                     help="With --plugin: check it against this plugin it doesn't master (e.g. PPF.esm), loaded before it. "
                          "Repeatable. A patch then masters these and the plugin."),
        click.option("--plugin", type=click.Path(exists=True, dir_okay=False, path_type=Path),
                     help="One plugin, checked with its masters."),
        click.option("--game-dir", type=click.Path(exists=True, file_okay=False, path_type=Path),
                     help="Fallout 4 install folder (default: FO4_DIR)."),
        click.option("--include-base-conflicts", is_flag=True,
                     help="Also report inconsistencies between Bethesda plugins alone (PRP-style full scan)."),
        click.option("--restore-disabled", is_flag=True,
                     help="Treat previs/precombines a mod deliberately disabled as broken."),
        click.option("--unprecombined", type=int, default=None,
                     help="Rebuild precombined cells with at least N mod references left out of the precombines."),
        click.option("--workers", type=int, default=None),
    ]
    for option in reversed(options):
        command = option(command)
    return command


def _load_order(mo2_profile, modbox_profile, library, plugin, game_dir, against=()):
    from creation_lib import previs as previs_lib

    chosen = [s for s in (mo2_profile, modbox_profile, plugin) if s is not None]
    if len(chosen) != 1:
        raise click.UsageError("give exactly one of --mo2-profile, --modbox-profile, --plugin")
    if against and plugin is None:
        raise click.UsageError("--against works with --plugin")
    if modbox_profile is not None:
        library = library or _default_library()
        return previs_lib.from_modbox_profile(library, _modbox_profile_id(library, modbox_profile))
    if game_dir is None:
        from cli.ck_commands import _resolve_game_dir

        game_dir = _resolve_game_dir("fo4")
    if mo2_profile is not None:
        return previs_lib.from_mo2_profile(mo2_profile, game_dir)
    return previs_lib.from_plugin(plugin, game_dir, against=list(against))


@previs.command("check")
@_source_options
@click.pass_context
def check(ctx, mo2_profile, modbox_profile, library, against, plugin, game_dir, include_base_conflicts, restore_disabled,
          unprecombined, workers):
    """Find cells whose precombines or previs the load order broke, outdated or disabled.

    Pick exactly one source: --mo2-profile, --modbox-profile or --plugin. Read-only.
    """
    from creation_lib import previs as previs_lib

    spec = _load_order(mo2_profile, modbox_profile, library, plugin, game_dir, against)
    report = previs_lib.check_load_order(
        spec,
        ignore_base_only=not include_base_conflicts,
        restore_disabled=restore_disabled,
        unprecombined_threshold=unprecombined,
        workers=workers,
    )
    report["summary"]["load_order"] = spec.label
    output(report, ctx.obj["fmt"], collection="cells")


@previs.command("build")
@_source_options
@click.option("--output", "output_dir", required=True, type=click.Path(file_okay=False, path_type=Path),
              help="Folder for the patch plugin, its BA2, CSG and CDX (install it as a mod, loaded last).")
@click.option("--name", "patch_name", default=None, help="Patch file name; its extension follows --plugin-type.")
@click.option("--work-dir", type=click.Path(file_okay=False, path_type=Path), default=None,
              help="Scratch folder for the seed and loose output (default: <output>-work; wiped first).")
@click.option("--scope", type=click.Choice(["broken", "plugin", "all"]), default="broken", show_default=True,
              help="broken: cells the load order broke. plugin (needs --plugin): every cell that plugin defines, "
                   "overrides or places references in. all: every cell of the load order, e.g. to build PPF.esm "
                   "over Fallout4.esm, the DLC and the unofficial patch.")
@click.option("--all-cells", is_flag=True, help="Same as --scope plugin: every cell the --plugin touches.")
@click.option("--output-mode", type=click.Choice(["patch", "plugin"]), default="patch", show_default=True,
              help="patch: a new patch plugin. plugin (needs --plugin): a stamped copy of the plugin itself in --output.")
@click.option("--plugin-type", type=click.Choice(["esp", "esm"]), default="esp", show_default=True,
              help="Write the patch as an ESP or an ESM. It is an ESP whenever it masters a plain ESP.")
@click.option("--no-pack", is_flag=True,
              help="Leave the meshes and tomes loose instead of packing <Name> - Main.ba2.")
@click.option("--small-model-cull", is_flag=True,
              help="Keep the CK's 4096-unit previs cull distance on models smaller than 100 units "
                   "(off by default: it hides small precombined parts of larger objects from afar).")
@click.pass_context
def build(ctx, mo2_profile, modbox_profile, library, against, plugin, game_dir, include_base_conflicts, restore_disabled,
          unprecombined, workers, output_dir, patch_name, work_dir, scope, all_cells, output_mode, plugin_type, no_pack,
          small_model_cull):
    """Check the load order, then rebuild precombines and previs for the broken cells into one patch plugin.

    With --output-mode plugin the chosen plugin gets the new previsbines itself (a copy in --output,
    named like it, with its own CSG/CDX); a plugin that already ships <Name> - Main.ba2 gets loose files.
    With --plugin Mod.esp --against PPF.esm the patch fixes what the mod breaks in PPF.esm and masters
    both (default name "Mod - PPF Patch.esp").
    Never writes to the game or any mod folder; the result is checked again with the patch loaded last.
    """
    from creation_lib import previs as previs_lib

    if all_cells:
        if scope == "all":
            raise click.UsageError("--all-cells means --scope plugin; it can't be combined with --scope all")
        scope = "plugin"
    if (scope == "plugin" or output_mode == "plugin") and plugin is None:
        raise click.UsageError("--scope plugin and --output-mode plugin work on one plugin: give --plugin")
    if output_mode == "plugin" and patch_name:
        raise click.UsageError("--name is for patches; --output-mode plugin keeps the plugin's name")
    spec = _load_order(mo2_profile, modbox_profile, library, plugin, game_dir, against)
    if against and not patch_name:
        patch_name = f"{plugin.stem} - {against[0].stem} Patch"
    patch_name = patch_name or previs_lib.DEFAULT_PATCH_NAME
    report = previs_lib.check_load_order(
        spec,
        ignore_base_only=not include_base_conflicts,
        restore_disabled=restore_disabled,
        unprecombined_threshold=unprecombined,
        rebuild_plugin=plugin.name if scope == "plugin" else None,
        rebuild_all=scope == "all",
        workers=workers,
    )
    result = previs_lib.build_patch(
        spec,
        report,
        output_dir,
        work_dir=work_dir or output_dir.with_name(output_dir.name + "-work"),
        patch_name=patch_name,
        into_plugin=plugin if output_mode == "plugin" else None,
        pack=not no_pack,
        plugin_type=plugin_type,
        required_masters=[p.name for p in against] + [plugin.name] if against else [],
        workers=workers,
        small_model_cull=small_model_cull,
        log=lambda message: click.echo(message, err=True),
    )
    summary = {
        "load_order": spec.label,
        "output_mode": output_mode,
        "patch": str(result.patch) if result.patch else None,
        "archive": str(result.archive) if result.archive else None,
        "cells_patched": len(result.patch_report["cells"]) if result.patch_report else 0,
        "cells_not_rebuilt": (result.patch_report or {}).get("unchanged", []),
        "cells_added": (result.patch_report or {}).get("added_cells", []),
        "skipped": result.skipped,
        "before": report["summary"],
        "after": result.recheck["summary"] if result.recheck else None,
    }
    output(summary, ctx.obj["fmt"])


def _default_library() -> Path:
    from creation_lib.mod_manager.locations import default_library_path

    return default_library_path()


def _modbox_profile_id(library: Path, wanted: str) -> str | None:
    from creation_lib.previs import modbox_profiles

    profiles = modbox_profiles(library)
    if not wanted:
        return None
    for profile_id, name in profiles:
        if wanted in (profile_id, name):
            return profile_id
    names = ", ".join(name for _, name in profiles)
    raise click.BadParameter(f"no profile {wanted!r} (have: {names})", param_hint="--modbox-profile")
