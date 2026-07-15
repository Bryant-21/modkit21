"""CLI tests for `modkit esp new` — create a fresh empty plugin."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.main import cli


def _new(tmp_path: Path, name: str, *extra: str):
    out = tmp_path / name
    result = CliRunner().invoke(
        cli, ["--game", "fo4", "esp", "new", str(out), *extra]
    )
    return out, result


def test_new_esp_infers_extension_and_writes_file(tmp_path: Path) -> None:
    out, result = _new(tmp_path, "B21_Cli.esp")
    assert result.exit_code == 0, result.output
    assert out.is_file()
    payload = json.loads(result.output)
    assert payload["extension"] == "esp"
    assert payload["masters"] == ["Fallout4.esm"]
    assert "Master" not in payload["flags"]


def test_new_esm_sets_master_flag(tmp_path: Path) -> None:
    _out, result = _new(tmp_path, "B21_Cli.esm")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["extension"] == "esm"
    assert "Master" in payload["flags"]


def test_new_esp_with_light_override(tmp_path: Path) -> None:
    _out, result = _new(tmp_path, "B21_Light.esp", "--light")
    assert result.exit_code == 0, result.output
    assert "Light" in json.loads(result.output)["flags"]


def test_new_no_masters(tmp_path: Path) -> None:
    _out, result = _new(tmp_path, "B21_Bare.esp", "--no-masters")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["masters"] == []


def test_new_rejects_unknown_extension(tmp_path: Path) -> None:
    _out, result = _new(tmp_path, "B21_Bad.txt")
    assert result.exit_code != 0
    assert "extension" in result.output.lower()


def test_new_refuses_overwrite_without_force(tmp_path: Path) -> None:
    out, first = _new(tmp_path, "B21_Exists.esp")
    assert first.exit_code == 0
    _out, second = _new(tmp_path, "B21_Exists.esp")
    assert second.exit_code != 0
    assert "exists" in second.output.lower()


def test_new_force_overwrites(tmp_path: Path) -> None:
    _new(tmp_path, "B21_Force.esp")
    _out, result = _new(tmp_path, "B21_Force.esp", "--force")
    assert result.exit_code == 0, result.output
