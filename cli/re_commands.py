"""modkit re — runs the RE symbol database (tools/re/redb) as a subprocess.

All arguments after `re` go to `python -m tools.re.redb` untouched; see tools/re/redb/__main__.py.
The frozen modkit.exe has no tools/ package, so it shells out to `uv run` in the workspace instead.
"""
from __future__ import annotations

import subprocess
import sys

import click


def _redb_command(fmt: str, args: list[str]) -> list[str]:
    if getattr(sys, "frozen", False):
        interpreter = ["uv", "run", "--no-sync", "python"]
    else:
        interpreter = [sys.executable]
    return [*interpreter, "-m", "tools.re.redb", "--format", fmt, *args]


@click.command(
    "re",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    add_help_option=False,
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def re_group(ctx, args):
    """RE symbol database: status, ingest, index, search, func, al, xrefs, vtable, export (run `re --help` for verbs)."""
    from app.paths import get_app_root

    fmt = (ctx.obj or {}).get("fmt", "json")
    sys.stdout.flush()
    result = subprocess.run(_redb_command(fmt, args), cwd=get_app_root())
    ctx.exit(result.returncode)
