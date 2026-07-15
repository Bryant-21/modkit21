"""CLI tests for `modkit esp copy` — copy a record between plugins."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.main import cli
from creation_lib.esp.plugin import Plugin


def _make_plugins(tmp_path: Path) -> tuple[Path, Path]:
    """Source with a referenceable WEAP (EditorID B21_CopyMe) + empty target."""
    src_path = tmp_path / "B21_Src.esp"
    src = Plugin.new("B21_Src.esp", game="fo4", masters=["Fallout4.esm"])
    src.add_record(src.new_record("WEAP"))  # filler so B21_CopyMe isn't object id 0x800
    rec = src.new_record("WEAP")
    rec.add_subrecord("EDID", b"B21_CopyMe\x00")
    src.add_record(rec)
    src.save(src_path)
    src.close()

    tgt_path = tmp_path / "B21_Tgt.esp"
    tgt = Plugin.new("B21_Tgt.esp", game="fo4", masters=["Fallout4.esm"])
    tgt.save(tgt_path)
    tgt.close()
    return src_path, tgt_path


def _copy(src: Path, tgt: Path, *extra: str):
    result = CliRunner().invoke(
        cli, ["--game", "fo4", "esp", "copy", str(src), str(tgt), "B21_CopyMe", *extra]
    )
    return result


def test_copy_new_allocates_fresh_form_id(tmp_path: Path) -> None:
    src, tgt = _make_plugins(tmp_path)
    result = _copy(src, tgt)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "new"
    assert payload["record"]["new_form_id"] != payload["record"]["source_form_id"]


def test_copy_override_keeps_form_id_and_adds_master(tmp_path: Path) -> None:
    src, tgt = _make_plugins(tmp_path)
    result = _copy(src, tgt, "--mode", "override")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mode"] == "override"
    assert payload["record"]["new_form_id"] == payload["record"]["source_form_id"]

    reloaded = Plugin.load(tgt)
    try:
        assert "b21_src.esp" in [m.lower() for m in reloaded.header.masters]
    finally:
        reloaded.close()


def test_copy_dry_run_writes_nothing(tmp_path: Path) -> None:
    src, tgt = _make_plugins(tmp_path)
    before = tgt.read_bytes()
    result = _copy(src, tgt, "--dry-run")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["output"] is None
    assert "new_form_id" not in payload["record"]
    assert tgt.read_bytes() == before


def test_copy_unknown_record_errors(tmp_path: Path) -> None:
    src, tgt = _make_plugins(tmp_path)
    result = CliRunner().invoke(
        cli, ["--game", "fo4", "esp", "copy", str(src), str(tgt), "B21_DoesNotExist"]
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
