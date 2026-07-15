"""CLI tests for `modkit esp compact-esl`.

Renumbers owned records into the ESL window and remaps internal references in
lockstep (schema-aware, so it works on disk-loaded plugins). A FLST.LNAM ref to
an out-of-window MISC proves the reference follows its target.
"""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.main import cli
from creation_lib.esp.editor import header_flags
from creation_lib.esp.plugin import Plugin
import creation_lib.esp.native_runtime as nr


def _make_plugin(tmp_path: Path, *, extra: int = 0) -> Path:
    """MISC at high id 0xC123, FLST(LNAM->MISC) at 0x801 (already in window)."""
    path = tmp_path / "B21_Compact.esp"
    p = Plugin.new("B21_Compact.esp", game="fo4", masters=["Fallout4.esm"])
    misc = p.new_record("MISC", form_id=0xFF00C123)
    misc.add_subrecord("EDID", b"B21_Target\x00")
    p.add_record(misc)
    flst = p.new_record("FLST", form_id=0xFF000801)
    flst.add_subrecord("EDID", b"B21_List\x00")
    flst.add_subrecord("LNAM", (0xFF00C123).to_bytes(4, "little"), semantic_type="formid")
    p.add_record(flst)
    for i in range(extra):
        rec = p.new_record("MISC", form_id=0xFF002000 + i)
        rec.add_subrecord("EDID", f"B21_Filler{i}\x00".encode())
        p.add_record(rec)
    p.save(path)
    p.close()
    return path


def _run(*args: str):
    return CliRunner().invoke(cli, ["--game", "fo4", "esp", "compact-esl", *args])


def _object_ids(plugin: Plugin) -> set[int]:
    return {fid & 0x00FFFFFF for fid in nr.plugin_handle_record_form_ids(plugin._rust_handle)}


def test_compact_packs_into_window_and_sets_flag(tmp_path: Path) -> None:
    path = _make_plugin(tmp_path)
    result = _run(str(path))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["remapped"] == 1  # only the out-of-window MISC moves
    assert payload["esl_flag"] is True

    r = Plugin.load(path, game="fo4")
    try:
        ids = _object_ids(r)
        assert all(0x800 <= oid < 0x1000 for oid in ids), ids
        assert 0x801 in ids  # FLST kept its in-window id (churn-minimized)
        assert header_flags.is_light(r._rust_handle) is True
        assert (int(r.header.next_object_id) & 0x00FFFFFF) == max(ids) + 1
    finally:
        r.close()


def test_compact_remaps_internal_reference(tmp_path: Path) -> None:
    path = _make_plugin(tmp_path)
    assert _run(str(path)).exit_code == 0

    r = Plugin.load(path, game="fo4")
    try:
        flst_fid = next(
            fid for fid in nr.plugin_handle_record_form_ids(r._rust_handle)
            if (r.get_record_by_form_id(fid) or None) and r.get_record_by_form_id(fid).signature == "FLST"
        )
        obj = json.loads(nr.plugin_handle_call(r._rust_handle, "export_record_text", flst_fid, "json"))
        lnam = next(f for f in obj["fields"] if f["signature"] == "LNAM")
        target = int(lnam["value"]["reference"]["object_id"], 16)
        assert 0x800 <= target < 0x1000  # ref followed MISC into the window
        assert r.get_record_by_form_id((len(r.header.masters) << 24) | target) is not None
    finally:
        r.close()


def test_compact_no_set_esl(tmp_path: Path) -> None:
    path = _make_plugin(tmp_path)
    result = _run(str(path), "--no-set-esl")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["esl_flag"] is False
    r = Plugin.load(path, game="fo4")
    try:
        assert header_flags.is_light(r._rust_handle) is False
    finally:
        r.close()


def test_compact_dry_run_does_not_write(tmp_path: Path) -> None:
    path = _make_plugin(tmp_path)
    before = path.read_bytes()
    result = _run(str(path), "--dry-run")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["output"] is None
    assert path.read_bytes() == before


def test_compact_refuses_when_over_capacity(tmp_path: Path) -> None:
    # floor 0xFFF leaves a 1-slot window; the plugin owns 2+ records.
    path = _make_plugin(tmp_path)
    result = _run(str(path), "--floor", "0xFFF")
    assert result.exit_code != 0
    assert "too many records" in result.output
