from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click

from cli._output import output


@click.group()
@click.pass_context
def world(ctx: click.Context) -> None:
    """Inspect and render static worldspaces."""


def _load_world_renderer_api() -> SimpleNamespace:
    from creation_lib.world_renderer import (  # noqa: PLC0415
        CellBounds,
        OfflineRenderJob,
        WorldSceneBuilder,
    )

    return SimpleNamespace(
        CellBounds=CellBounds,
        OfflineRenderJob=OfflineRenderJob,
        WorldSceneBuilder=WorldSceneBuilder,
    )


def _load_offscreen_renderer():
    from creation_lib.renderer.world_offscreen import (  # noqa: PLC0415
        render_world_scene_offscreen,
    )

    return render_world_scene_offscreen


def _format(ctx: click.Context) -> str:
    return ctx.obj.get("fmt", "json") if ctx.obj else "json"


def _report_data(report: Any) -> Any:
    if is_dataclass(report):
        return asdict(report)
    if hasattr(report, "__dict__"):
        return report.__dict__
    return report


def _write_report_file(report_path: Path | None, report: Any) -> None:
    if report_path is None:
        return
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(_report_data(report), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _builder(
    ctx: click.Context,
    plugin_paths: Sequence[Path],
    data_paths: Sequence[Path],
    archive_paths: Sequence[Path],
):
    api = _load_world_renderer_api()
    game = ctx.obj.get("game", "fo4") if ctx.obj else "fo4"
    return api.WorldSceneBuilder(
        game=game,
        plugin_paths=[str(path) for path in plugin_paths],
        data_paths=[str(path) for path in data_paths],
        archive_paths=[str(path) for path in archive_paths],
    )


@world.command("list-worldspaces")
@click.option("--plugin", "plugin_paths", multiple=True, type=click.Path(path_type=Path))
@click.option("--data-path", "data_paths", multiple=True, type=click.Path(path_type=Path))
@click.option("--archive", "archive_paths", multiple=True, type=click.Path(path_type=Path))
@click.pass_context
def list_worldspaces(
    ctx: click.Context,
    plugin_paths: Sequence[Path],
    data_paths: Sequence[Path],
    archive_paths: Sequence[Path],
) -> None:
    with _builder(ctx, plugin_paths, data_paths, archive_paths).open() as session:
        report = session.list_worldspaces()
    output(_report_data(report), _format(ctx))


@world.command("inspect")
@click.option("--plugin", "plugin_paths", multiple=True, type=click.Path(path_type=Path))
@click.option("--data-path", "data_paths", multiple=True, type=click.Path(path_type=Path))
@click.option("--archive", "archive_paths", multiple=True, type=click.Path(path_type=Path))
@click.option("--worldspace", required=True)
@click.option("--min-x", default=-1, type=int)
@click.option("--min-y", default=-1, type=int)
@click.option("--max-x", default=1, type=int)
@click.option("--max-y", default=1, type=int)
@click.pass_context
def inspect(
    ctx: click.Context,
    plugin_paths: Sequence[Path],
    data_paths: Sequence[Path],
    archive_paths: Sequence[Path],
    worldspace: str,
    min_x: int,
    min_y: int,
    max_x: int,
    max_y: int,
) -> None:
    api = _load_world_renderer_api()
    with _builder(ctx, plugin_paths, data_paths, archive_paths).open() as session:
        scene = session.load_worldspace(
            worldspace,
            api.CellBounds(min_x, min_y, max_x, max_y),
        )
        try:
            report = scene.stats()
        finally:
            scene.close()
    output(_report_data(report), _format(ctx))


@world.command("render")
@click.argument("output_path", type=click.Path(path_type=Path))
@click.option("--plugin", "plugin_paths", multiple=True, type=click.Path(path_type=Path))
@click.option("--data-path", "data_paths", multiple=True, type=click.Path(path_type=Path))
@click.option("--archive", "archive_paths", multiple=True, type=click.Path(path_type=Path))
@click.option("--worldspace", required=True)
@click.option("--min-x", default=-1, type=int)
@click.option("--min-y", default=-1, type=int)
@click.option("--max-x", default=1, type=int)
@click.option("--max-y", default=1, type=int)
@click.option("--width", default=1920, type=int)
@click.option("--height", default=1080, type=int)
@click.option("--report", "report_path", type=click.Path(path_type=Path))
@click.pass_context
def render(
    ctx: click.Context,
    output_path: Path,
    plugin_paths: Sequence[Path],
    data_paths: Sequence[Path],
    archive_paths: Sequence[Path],
    worldspace: str,
    min_x: int,
    min_y: int,
    max_x: int,
    max_y: int,
    width: int,
    height: int,
    report_path: Path | None,
) -> None:
    if width <= 0 or height <= 0:
        raise click.ClickException("width and height must be positive")

    api = _load_world_renderer_api()
    render_world_scene_offscreen = _load_offscreen_renderer()
    with _builder(ctx, plugin_paths, data_paths, archive_paths).open() as session:
        scene = session.load_worldspace(
            worldspace,
            api.CellBounds(min_x, min_y, max_x, max_y),
        )
        try:
            report = render_world_scene_offscreen(
                scene,
                api.OfflineRenderJob(
                    output_path=str(output_path),
                    width=width,
                    height=height,
                ),
            )
        finally:
            scene.close()
    _write_report_file(report_path, report)
    output(_report_data(report), _format(ctx))
