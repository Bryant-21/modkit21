"""modkit — unified CLI for Bethesda modding tools."""

import multiprocessing
import os
import sys

import click

# Ensure project root is on sys.path for lib imports
_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Suppress noisy logging from libraries
import logging

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)


def _configure_stdio():
    """Use UTF-8 for Click output to avoid Windows help-text encoding crashes."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _bootstrap_environment():
    """Load workspace .env at the CLI boundary."""
    from app.paths import load_dotenv_into_environ

    load_dotenv_into_environ()


@click.group()
@click.option(
    "--game",
    default="",
    help="Game profile (fo4, fo76, skyrimse, starfield). Defaults to DEFAULT_GAME env or fo4.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "pretty", "compact", "table"]),
    default="json",
    help="Output format.",
)
@click.option(
    "--db-dir",
    default="",
    help="Path to database directory. Defaults to ./data/ relative to exe.",
)
@click.pass_context
def cli(ctx, game: str, fmt: str, db_dir: str):
    """modkit — Bethesda modding toolkit CLI.

    Search game data, manipulate NIF meshes, and more.
    """
    ctx.ensure_object(dict)

    # Resolve game
    ctx.obj["game_explicit"] = bool(game)
    if not game:
        game = os.environ.get("DEFAULT_GAME", "fo4")
    ctx.obj["game"] = game
    ctx.obj["fmt"] = fmt

    # Resolve db_dir
    if not db_dir:
        db_dir = os.environ.get("MODKIT_DB_DIR", "")
    if not db_dir:
        # Use the shared app path resolver so frozen builds can discover the
        # workspace root even when the executable lives under dist/.
        from app.paths import get_db_dir

        db_dir = str(get_db_dir())
    ctx.obj["db_dir"] = db_dir


@cli.command()
def version():
    """Print version and exit."""
    version_file = os.path.join(_PROJECT_ROOT, "VERSION")
    if not os.path.isfile(version_file) and getattr(sys, "frozen", False):
        version_file = os.path.join(sys._MEIPASS, "VERSION")
    if os.path.isfile(version_file):
        with open(version_file) as f:
            click.echo(f"modkit {f.read().strip()}")
    else:
        click.echo("modkit (dev)")


# Register command groups
from cli.data_commands import data  # noqa: E402
from cli.nif_commands import nif  # noqa: E402
from cli import audit_commands as _audit_commands  # noqa: E402, F401 — registers `data audit-yaml` as a side effect

cli.add_command(data)
cli.add_command(nif)

from cli.cloth_commands import cloth  # noqa: E402

cli.add_command(cloth)

from cli.build_commands import build  # noqa: E402
from cli.archive_commands import archive  # noqa: E402
from cli.texture_commands import texture  # noqa: E402
from cli.mod_commands import mod  # noqa: E402
from cli.esp_commands import esp  # noqa: E402
from cli.ck_commands import ck  # noqa: E402
from cli.git_commands import git  # noqa: E402
from cli.index_commands import index  # noqa: E402
from cli.swf_commands import swf  # noqa: E402
from cli.setup_commands import setup  # noqa: E402
from cli.world_commands import world  # noqa: E402

cli.add_command(build)
cli.add_command(archive)
cli.add_command(texture)
cli.add_command(mod)
cli.add_command(esp)
cli.add_command(ck)
cli.add_command(git)
cli.add_command(index)
cli.add_command(swf)
cli.add_command(setup)
cli.add_command(world)


def _normalize_exit_code(code):
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    print(code, file=sys.stderr)
    return 1


def _force_exit(code):
    """Terminate immediately, skipping interpreter finalization.

    Frozen (PyInstaller) builds can hang at exit when a non-daemon Python thread
    or a native PyO3/rayon thread never joins, leaving modkit.exe resident and
    holding memory long after the command finished and printed its output. The
    work is already done by the time we get here, so flush user-visible output
    and hand off to the OS, which reclaims everything at once.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    os._exit(code)


def main():
    multiprocessing.freeze_support()
    _configure_stdio()
    _bootstrap_environment()

    # Dev runs (uv run python / pytest) keep normal teardown; only the frozen
    # exe needs the hard exit that fixes the lingering-process bug.
    if not getattr(sys, "frozen", False):
        cli()
        return

    # An aborted/timed-out request kills the agent's shell but not modkit.exe;
    # tear ourselves down when that parent dies instead of orphaning native
    # worker threads that keep holding memory.
    from cli._watchdog import install_parent_death_watchdog

    install_parent_death_watchdog(on_exit=_force_exit)

    code = 0
    try:
        cli()
    except SystemExit as exc:
        code = _normalize_exit_code(exc.code)
    except BaseException:
        import traceback

        traceback.print_exc()
        code = 1
    finally:
        _force_exit(code)


if __name__ == "__main__":
    main()
