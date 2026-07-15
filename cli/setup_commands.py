"""CLI setup command."""

from __future__ import annotations

import click


@click.command("setup")
@click.option("--force", is_flag=True, help="Run setup even if it was completed before.")
def setup(force: bool) -> None:
    """Open the first-run setup window and write toolkit_settings.json + .env."""
    try:
        from cli.setup_gui import run_setup_gui
    except Exception as exc:
        raise click.ClickException(f"Setup GUI is unavailable: {exc}") from exc

    try:
        completed = run_setup_gui(force=force)
    except Exception as exc:
        raise click.ClickException(f"Setup GUI failed: {exc}") from exc
    if completed:
        click.echo("Setup complete.")
    else:
        click.echo("Setup cancelled.")
