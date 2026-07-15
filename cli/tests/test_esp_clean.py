"""CLI tests for `modkit esp clean` — ITM removal + UDR.

ITM needs the master on disk (the override is compared against it), so the
fixture writes a sibling B21_Master.esm. The deleted REFR exercises UDR, which
is flag-based and needs no master.
"""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.main import cli
from creation_lib.esp.editor import header_flags
from creation_lib.esp.plugin import Plugin
import creation_lib.esp.native_runtime as nr


def _make_master(tmp_path: Path) -> None:
    path = tmp_path / "B21_Master.esm"
    m = Plugin.new("B21_Master.esm", game="fo4", masters=[])
    rec = m.new_record("MISC", form_id=0x00000800)
    rec.add_subrecord("EDID", b"B21_Item\x00")
    m.add_record(rec)
    header_flags.set_master(m._rust_handle, True)
    m.save(path)
    m.close()


def _make_plugin(tmp_path: Path, *, master: str = "B21_Master.esm", itm: bool = True) -> Path:
    path = tmp_path / "B21_Clean.esp"
    p = Plugin.new("B21_Clean.esp", game="fo4", masters=[master])
    if itm:
        # Byte-identical override of the master record (idx 0) → ITM.
        ov = p.new_record("MISC", form_id=0x00000800)
        ov.add_subrecord("EDID", b"B21_Item\x00")
        p.add_record(ov)
    deleted = p.new_record("REFR", form_id=0xFF000810)
    deleted.flags = 0x20  # RECORD_FLAG_DELETED
    deleted.add_subrecord("NAME", (0x00000800).to_bytes(4, "little"), semantic_type="formid")
    p.add_record(deleted)
    p.save(path)
    p.close()
    return path


def _run(*args: str):
    return CliRunner().invoke(cli, ["--game", "fo4", "esp", "clean", *args])


def _record_count(path: Path) -> int:
    r = Plugin.load(path, game="fo4")
    try:
        return len(nr.plugin_handle_record_form_ids(r._rust_handle))
    finally:
        r.close()


def test_clean_removes_itm_and_udr(tmp_path: Path) -> None:
    _make_master(tmp_path)
    path = _make_plugin(tmp_path)
    result = _run(str(path))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["itm_removed"] == ["00000800"]
    assert payload["udr_fixed"] == ["01000810"]
    assert payload["itm_skipped"] is False
    assert _record_count(path) == 1  # override removed, REFR undeleted (kept)


def test_clean_no_itm_keeps_override(tmp_path: Path) -> None:
    _make_master(tmp_path)
    path = _make_plugin(tmp_path)
    result = _run(str(path), "--no-itm")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["itm_removed"] == []
    assert payload["udr_fixed"] == ["01000810"]
    assert _record_count(path) == 2  # override kept


def test_clean_dry_run_does_not_write(tmp_path: Path) -> None:
    _make_master(tmp_path)
    path = _make_plugin(tmp_path)
    before = path.read_bytes()
    result = _run(str(path), "--dry-run")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["output"] is None
    assert payload["itm_removed"] == ["00000800"]
    assert path.read_bytes() == before


def test_clean_missing_master_skips_itm(tmp_path: Path) -> None:
    path = _make_plugin(tmp_path, master="B21_NoSuchMaster.esm", itm=False)
    result = _run(str(path))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["itm_skipped"] is True
    assert "B21_NoSuchMaster.esm" in payload["missing_masters"]
    assert payload["udr_fixed"] == ["01000810"]  # UDR still runs
