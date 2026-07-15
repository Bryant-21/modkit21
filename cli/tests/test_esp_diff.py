"""CLI tests for `modkit esp diff` — record-level two-plugin diff."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.main import cli
from creation_lib.esp.plugin import Plugin


def _plugin(path: Path, records: list[tuple[int, str, str, bytes | None]]) -> None:
    """records: (object_id, signature, edid, full-name-bytes-or-None)."""
    p = Plugin.new(path.name, game="fo4", masters=["Fallout4.esm"])
    for obj, sig, edid, full in records:
        rec = p.new_record(sig, form_id=(0xFF000000 | obj))
        rec.add_subrecord("EDID", edid.encode() + b"\x00")
        if full is not None:
            rec.add_subrecord("FULL", full)
        p.add_record(rec)
    p.save(path)
    p.close()


def _run(*args: str):
    return CliRunner().invoke(cli, ["--game", "fo4", "esp", "diff", *args])


def test_diff_added_removed_changed(tmp_path: Path) -> None:
    a = tmp_path / "B21_A.esp"
    b = tmp_path / "B21_B.esp"
    _plugin(a, [
        (0x800, "WEAP", "B21_Same", None),
        (0x801, "WEAP", "B21_Changed", b"Old\x00"),
        (0x802, "WEAP", "B21_Removed", None),
    ])
    _plugin(b, [
        (0x800, "WEAP", "B21_Same", None),
        (0x801, "WEAP", "B21_Changed", b"New\x00"),
        (0x803, "WEAP", "B21_Added", None),
    ])
    result = _run(str(a), str(b))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["counts"] == {"added": 1, "removed": 1, "changed": 1}
    assert [r["object_id"] for r in payload["added"]] == ["000803"]
    assert [r["object_id"] for r in payload["removed"]] == ["000802"]
    assert [r["object_id"] for r in payload["changed"]] == ["000801"]


def test_diff_identical_plugins(tmp_path: Path) -> None:
    a = tmp_path / "B21_A.esp"
    b = tmp_path / "B21_B.esp"
    recs = [(0x800, "WEAP", "B21_One", None), (0x801, "ARMO", "B21_Two", None)]
    _plugin(a, recs)
    _plugin(b, recs)
    result = _run(str(a), str(b))
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["counts"] == {"added": 0, "removed": 0, "changed": 0}


def test_diff_detail_lists_changed_subrecords(tmp_path: Path) -> None:
    a = tmp_path / "B21_A.esp"
    b = tmp_path / "B21_B.esp"
    _plugin(a, [(0x801, "WEAP", "B21_Changed", b"Old\x00")])
    _plugin(b, [(0x801, "WEAP", "B21_Changed", b"New\x00")])
    result = _run(str(a), str(b), "--detail")
    assert result.exit_code == 0, result.output
    changed = json.loads(result.output)["changed"]
    assert len(changed) == 1
    assert "FULL" in changed[0]["detail"]["subrecords_changed"]


def test_diff_type_filter(tmp_path: Path) -> None:
    a = tmp_path / "B21_A.esp"
    b = tmp_path / "B21_B.esp"
    _plugin(a, [(0x800, "WEAP", "B21_W", None)])
    _plugin(b, [(0x800, "WEAP", "B21_W", None), (0x801, "ARMO", "B21_A", None)])
    result = _run(str(a), str(b), "--type", "WEAP")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["counts"]["added"] == 0  # ARMO excluded
