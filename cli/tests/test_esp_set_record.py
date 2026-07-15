"""CLI tests for `modkit esp set-record` — focused on disk persistence.

Regression coverage for an intermittent bug where `set-record` reported success
(`"created": true`) yet the plugin on disk stayed at the empty header-only size
because the native save truncated the target in place and a failed/interrupted
write left it destroyed. The save is now atomic (temp file + rename), so a
successful command must always leave the record readable back from disk.
"""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.main import cli
from creation_lib.esp.plugin import Plugin


def _new_empty(tmp_path: Path) -> Path:
    out = tmp_path / "B21_SetRec.esp"
    result = CliRunner().invoke(cli, ["--game", "fo4", "esp", "new", str(out)])
    assert result.exit_code == 0, result.output
    return out


def _global_record_json(tmp_path: Path) -> Path:
    rec = {"signature": "GLOB", "form_id": "000800", "eid": "B21_PersistGlobal", "fields": []}
    src = tmp_path / "rec.json"
    src.write_text(json.dumps(rec), encoding="utf-8")
    return src


def test_set_record_persists_to_disk(tmp_path: Path) -> None:
    plugin_path = _new_empty(tmp_path)
    empty_size = plugin_path.stat().st_size
    rec = _global_record_json(tmp_path)

    result = CliRunner().invoke(
        cli, ["--game", "fo4", "esp", "set-record", str(plugin_path), str(rec), "--type", "GLOB"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["created"] is True

    # The success payload must be backed by bytes on disk: the file grew, and a
    # fresh reload (which re-reads from disk) sees the record.
    assert plugin_path.stat().st_size > empty_size, "file stayed at empty size after success"
    reloaded = Plugin.load(plugin_path)
    try:
        assert reloaded.record_count == 1
        assert "b21_persistglobal" in {k.lower() for k in reloaded.eid_index()}
    finally:
        reloaded.close()


def test_set_record_dry_run_writes_nothing(tmp_path: Path) -> None:
    plugin_path = _new_empty(tmp_path)
    before = plugin_path.read_bytes()
    rec = _global_record_json(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["--game", "fo4", "esp", "set-record", str(plugin_path), str(rec), "--type", "GLOB", "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert plugin_path.read_bytes() == before
