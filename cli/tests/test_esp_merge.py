"""CLI tests for `modkit esp merge` — bulk record copy between plugins."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.main import cli
from creation_lib.esp.plugin import Plugin
import creation_lib.esp.native_runtime as nr


def _make_source(tmp_path: Path) -> Path:
    path = tmp_path / "B21_Source.esp"
    p = Plugin.new("B21_Source.esp", game="fo4", masters=["Fallout4.esm"])
    for name, sig in [("B21_Sword", "WEAP"), ("B21_Shield", "ARMO"), ("B21_Potion", "ALCH")]:
        rec = p.new_record(sig)
        rec.add_subrecord("EDID", name.encode() + b"\x00")
        p.add_record(rec)
    p.save(path)
    p.close()
    return path


def _make_target(tmp_path: Path) -> Path:
    path = tmp_path / "B21_Target.esp"
    p = Plugin.new("B21_Target.esp", game="fo4", masters=["Fallout4.esm"])
    keep = p.new_record("MISC")
    keep.add_subrecord("EDID", b"B21_Existing\x00")
    p.add_record(keep)
    p.save(path)
    p.close()
    return path


def _run(*args: str):
    return CliRunner().invoke(cli, ["--game", "fo4", "esp", "merge", *args])


def _record_count(path: Path) -> int:
    r = Plugin.load(path, game="fo4")
    try:
        return len(nr.plugin_handle_record_form_ids(r._rust_handle))
    finally:
        r.close()


def test_merge_new_appends_all(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    dst = _make_target(tmp_path)
    result = _run(str(src), str(dst), "--mode", "new")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["merged"] == 3
    assert payload["mode"] == "new"
    assert _record_count(dst) == 4  # 1 existing + 3 merged


def test_merge_override_adds_source_master(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    dst = _make_target(tmp_path)
    result = _run(str(src), str(dst), "--mode", "override")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["merged"] == 3
    r = Plugin.load(dst, game="fo4")
    try:
        assert "b21_source.esp" in [m.lower() for m in r.header.masters]
    finally:
        r.close()


def test_merge_match_subset(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    dst = _make_target(tmp_path)
    result = _run(str(src), str(dst), "--match", "B21_S*")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["merged"] == 2  # Sword + Shield, not Potion
    assert {e["editor_id"] for e in payload["records"]} == {"B21_Sword", "B21_Shield"}


def test_merge_type_filter(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    dst = _make_target(tmp_path)
    result = _run(str(src), str(dst), "--type", "WEAP")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["merged"] == 1


def test_merge_dry_run_does_not_write(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    dst = _make_target(tmp_path)
    before = dst.read_bytes()
    result = _run(str(src), str(dst), "--dry-run")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["merged"] == 3
    assert dst.read_bytes() == before
