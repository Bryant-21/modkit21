"""CLI tests for `modkit esp header` — show and edit header fields/flags."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.main import cli
from creation_lib.esp.plugin import Plugin


def _make_plugin(tmp_path: Path) -> Path:
    path = tmp_path / "B21_Header.esp"
    p = Plugin.new("B21_Header.esp", game="fo4", masters=["Fallout4.esm"])
    p.save(path)
    p.close()
    return path


def _run(*args: str):
    return CliRunner().invoke(cli, ["--game", "fo4", "esp", "header", *args])


def test_header_show(tmp_path: Path) -> None:
    result = _run(str(_make_plugin(tmp_path)))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["masters"] == 1
    assert payload["flags"]["esl"] is False
    assert "next_object_id" in payload


def test_header_set_fields(tmp_path: Path) -> None:
    path = _make_plugin(tmp_path)
    result = _run(str(path), "--author", "B21", "--description", "hello", "--next-object-id", "0x900")
    assert result.exit_code == 0, result.output
    reloaded = Plugin.load(path, game="fo4")
    try:
        assert reloaded.header.author == "B21"
        assert reloaded.header.description == "hello"
        assert (int(reloaded.header.next_object_id) & 0x00FFFFFF) == 0x900
    finally:
        reloaded.close()


def test_header_toggle_esl(tmp_path: Path) -> None:
    from creation_lib.esp.editor import header_flags

    path = _make_plugin(tmp_path)
    result = _run(str(path), "--esl")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["flags"]["esl"] is True
    reloaded = Plugin.load(path, game="fo4")
    try:
        assert header_flags.is_light(reloaded._rust_handle) is True
    finally:
        reloaded.close()

    off = _run(str(path), "--no-esl")
    assert off.exit_code == 0, off.output
    assert json.loads(off.output)["flags"]["esl"] is False


def test_header_bad_next_object_id(tmp_path: Path) -> None:
    result = _run(str(_make_plugin(tmp_path)), "--next-object-id", "zzz")
    assert result.exit_code != 0
    assert "next-object-id" in result.output
