from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from click.testing import CliRunner

from cli.main import cli


@dataclass
class FakeReport:
    ok: bool
    errors: list[str]
    warnings: list[dict]
    timings_ms: dict
    counts: dict
    data: dict


@dataclass
class FakeCellBounds:
    min_x: int
    min_y: int
    max_x: int
    max_y: int


@dataclass
class FakeOfflineRenderJob:
    output_path: str
    width: int
    height: int


class FakeScene:
    def __init__(self, calls: list[tuple]):
        self.calls = calls

    def stats(self) -> FakeReport:
        self.calls.append(("stats",))
        return FakeReport(True, [], [], {}, {"cells": 1}, {"worldspace": "TinyWorld"})

    def close(self) -> None:
        self.calls.append(("scene.close",))


class FakeSession:
    def __init__(self, calls: list[tuple]):
        self.calls = calls

    def __enter__(self):
        self.calls.append(("session.enter",))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.calls.append(("session.exit",))

    def list_worldspaces(self) -> FakeReport:
        self.calls.append(("list_worldspaces",))
        return FakeReport(True, [], [], {}, {"worldspaces": 0}, {"worldspaces": []})

    def load_worldspace(self, worldspace: str, bounds: FakeCellBounds) -> FakeScene:
        self.calls.append(("load_worldspace", worldspace, bounds))
        return FakeScene(self.calls)


class FakeWorldSceneBuilder:
    def __init__(
        self,
        *,
        game: str,
        plugin_paths: list[str],
        data_paths: list[str],
        archive_paths: list[str],
    ):
        self.calls = FakeWorldSceneBuilder.calls
        self.calls.append(("builder", game, plugin_paths, data_paths, archive_paths))

    def open(self) -> FakeSession:
        self.calls.append(("open",))
        return FakeSession(self.calls)


FakeWorldSceneBuilder.calls = []


def fake_api() -> SimpleNamespace:
    return SimpleNamespace(
        CellBounds=FakeCellBounds,
        OfflineRenderJob=FakeOfflineRenderJob,
        WorldSceneBuilder=FakeWorldSceneBuilder,
    )


def test_world_list_worldspaces_empty_stack(monkeypatch) -> None:
    FakeWorldSceneBuilder.calls = []
    monkeypatch.setattr("cli.world_commands._load_world_renderer_api", fake_api)

    result = CliRunner().invoke(cli, ["--format", "json", "world", "list-worldspaces"])

    assert result.exit_code == 0
    assert '"worldspaces":[]' in result.output
    assert ("builder", "fo4", [], [], []) in FakeWorldSceneBuilder.calls
    assert ("list_worldspaces",) in FakeWorldSceneBuilder.calls


def test_world_inspect_loads_requested_worldspace_and_bounds(monkeypatch) -> None:
    FakeWorldSceneBuilder.calls = []
    monkeypatch.setattr("cli.world_commands._load_world_renderer_api", fake_api)

    result = CliRunner().invoke(
        cli,
        [
            "--game",
            "skyrimse",
            "world",
            "inspect",
            "--plugin",
            "Skyrim.esm",
            "--data-path",
            "Data",
            "--archive",
            "Archive.bsa",
            "--worldspace",
            "Tamriel",
            "--min-x",
            "-2",
            "--min-y",
            "-3",
            "--max-x",
            "4",
            "--max-y",
            "5",
        ],
    )

    assert result.exit_code == 0
    assert (
        "builder",
        "skyrimse",
        ["Skyrim.esm"],
        ["Data"],
        ["Archive.bsa"],
    ) in FakeWorldSceneBuilder.calls
    assert (
        "load_worldspace",
        "Tamriel",
        FakeCellBounds(-2, -3, 4, 5),
    ) in FakeWorldSceneBuilder.calls
    assert ("stats",) in FakeWorldSceneBuilder.calls
    assert ("scene.close",) in FakeWorldSceneBuilder.calls


def test_world_render_validates_dimensions(tmp_path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "world",
            "render",
            str(tmp_path / "out.png"),
            "--worldspace",
            "TinyWorld",
            "--width",
            "0",
            "--height",
            "64",
        ],
    )

    assert result.exit_code != 0
    assert "width and height must be positive" in result.output


def test_world_render_calls_offscreen_renderer(monkeypatch, tmp_path) -> None:
    FakeWorldSceneBuilder.calls = []
    render_calls = []
    monkeypatch.setattr("cli.world_commands._load_world_renderer_api", fake_api)

    def fake_render(scene: FakeScene, job: FakeOfflineRenderJob) -> FakeReport:
        render_calls.append((scene, job))
        return FakeReport(True, [], [], {}, {}, {"output_path": job.output_path})

    monkeypatch.setattr("cli.world_commands._load_offscreen_renderer", lambda: fake_render)

    result = CliRunner().invoke(
        cli,
        [
            "world",
            "render",
            str(tmp_path / "out.png"),
            "--worldspace",
            "TinyWorld",
            "--width",
            "64",
            "--height",
            "32",
        ],
    )

    assert result.exit_code == 0
    assert render_calls
    assert render_calls[0][1] == FakeOfflineRenderJob(
        output_path=str(tmp_path / "out.png"),
        width=64,
        height=32,
    )
    assert ("scene.close",) in FakeWorldSceneBuilder.calls


def test_world_render_writes_report_file(monkeypatch, tmp_path) -> None:
    FakeWorldSceneBuilder.calls = []
    monkeypatch.setattr("cli.world_commands._load_world_renderer_api", fake_api)
    monkeypatch.setattr(
        "cli.world_commands._load_offscreen_renderer",
        lambda: lambda _scene, job: FakeReport(
            True, [], [], {}, {}, {"output_path": job.output_path}
        ),
    )
    report_path = tmp_path / "report.json"

    result = CliRunner().invoke(
        cli,
        [
            "world",
            "render",
            str(tmp_path / "out.png"),
            "--worldspace",
            "TinyWorld",
            "--report",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert '"ok": true' in report_path.read_text(encoding="utf-8")
