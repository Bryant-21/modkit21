"""CLI tests for `modkit esp masters` — list / add / remove / reorder.

DLCRobot is referenced by an override record (record-level — reliably detected on a
disk-loaded plugin). Subrecord-level ref nulling is unit-tested against the native
helper in test_null_refs_to_master.py, where semantic types are present.
"""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.main import cli
from creation_lib.esp.plugin import Plugin


def _make_plugin(tmp_path: Path) -> Path:
    """Masters [Fallout4, DLCRobot, DLCCoast]; DLCRobot used by an override record."""
    path = tmp_path / "B21_Masters.esp"
    p = Plugin.new("B21_Masters.esp", game="fo4", masters=["Fallout4.esm", "DLCRobot.esm", "DLCCoast.esm"])
    local = p.new_record("WEAP")
    local.add_subrecord("EDID", b"B21_Local\x00")
    p.add_record(local)
    override = p.new_record("WEAP", form_id=0x01000DEF)  # override of DLCRobot:000DEF
    override.add_subrecord("EDID", b"B21_Override\x00")
    p.add_record(override)
    p.save(path)
    p.close()
    return path


def _run(*args: str):
    return CliRunner().invoke(cli, ["--game", "fo4", "esp", "masters", *args])


def _eid_set(plugin: Plugin) -> set[str]:
    return {k.lower() for k in plugin.eid_index()}


def test_masters_list(tmp_path: Path) -> None:
    result = _run("list", str(_make_plugin(tmp_path)))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    by_name = {m["name"].lower(): m for m in payload["masters"]}
    assert payload["count"] == 3
    assert by_name["dlcrobot.esm"]["used"] is True
    assert by_name["dlccoast.esm"]["used"] is False


def test_masters_add_idempotent(tmp_path: Path) -> None:
    path = _make_plugin(tmp_path)
    first = _run("add", str(path), "DLCworkshop01.esm")
    assert first.exit_code == 0, first.output
    assert [a["name"] for a in json.loads(first.output)["added"]] == ["DLCworkshop01.esm"]
    second = _run("add", str(path), "DLCworkshop01.esm")
    assert second.exit_code == 0, second.output
    assert json.loads(second.output)["added"] == []
    reloaded = Plugin.load(path, game="fo4")
    try:
        assert [m.lower() for m in reloaded.header.masters].count("dlcworkshop01.esm") == 1
    finally:
        reloaded.close()


def test_masters_remove_unused_succeeds(tmp_path: Path) -> None:
    path = _make_plugin(tmp_path)
    result = _run("remove", str(path), "DLCCoast.esm")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["forced"] is False
    reloaded = Plugin.load(path, game="fo4")
    try:
        assert "dlccoast.esm" not in [m.lower() for m in reloaded.header.masters]
    finally:
        reloaded.close()


def test_masters_remove_refuses_when_referenced(tmp_path: Path) -> None:
    path = _make_plugin(tmp_path)
    result = _run("remove", str(path), "DLCRobot.esm")
    assert result.exit_code != 0
    assert "--force" in result.output
    reloaded = Plugin.load(path, game="fo4")
    try:
        assert "dlcrobot.esm" in [m.lower() for m in reloaded.header.masters]
    finally:
        reloaded.close()


def test_masters_remove_force_drops_overrides(tmp_path: Path) -> None:
    path = _make_plugin(tmp_path)
    result = _run("remove", str(path), "DLCRobot.esm", "--force")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["forced"] is True
    assert payload["overrides_dropped"] == 1
    reloaded = Plugin.load(path, game="fo4")
    try:
        assert "dlcrobot.esm" not in [m.lower() for m in reloaded.header.masters]
        assert "b21_override" not in _eid_set(reloaded)  # override of DLCRobot was dropped
    finally:
        reloaded.close()


def test_masters_reorder(tmp_path: Path) -> None:
    path = _make_plugin(tmp_path)
    result = _run("reorder", str(path), "DLCCoast.esm", "DLCRobot.esm", "Fallout4.esm")
    assert result.exit_code == 0, result.output
    reloaded = Plugin.load(path, game="fo4")
    try:
        assert [m.lower() for m in reloaded.header.masters] == ["dlccoast.esm", "dlcrobot.esm", "fallout4.esm"]
    finally:
        reloaded.close()


def test_masters_reorder_rejects_non_permutation(tmp_path: Path) -> None:
    path = _make_plugin(tmp_path)
    result = _run("reorder", str(path), "DLCRobot.esm", "Fallout4.esm")
    assert result.exit_code != 0
    assert "permutation" in result.output
