"""`modkit esp get-record` must print each subrecord's value under its own signature."""
from __future__ import annotations

import json
import struct
from pathlib import Path

from click.testing import CliRunner

from cli.main import cli
from creation_lib.esp.model import Record
from creation_lib.esp.plugin import Plugin

# Twelve-byte FO76 PRPS rows (AVIF, value, CURV) copied from SeventySix.esm encFeralGhoul01.
PRPS = bytes.fromhex(
    "DA0200000000C84200000000"
    "C30200000000804000000000"
    "D402000000000000F8E97600"
    "D9DD7A000000000000000000"
)
DNAM = bytes.fromhex("2300640000000100")


def _formid(object_id: int) -> bytes:
    return struct.pack("<I", object_id)


def _object_id(value: dict) -> str:
    return value["reference"]["object_id"]


def test_fo76_npc_values_stay_under_their_own_subrecord(tmp_path: Path) -> None:
    """AJNG+AJXG fold into one authoring row group, which shifted every later
    value onto the previous subrecord's signature (PRPS bytes printed as ECOR,
    INRD as PRPS, DNAM as OBTS) and left the last subrecord (CVT2) null."""
    subrecords = [
        ("EDID", b"B21_encFeralGhoul01\x00"),
        ("AJNG", _formid(0x5C4037)),
        ("AJXG", _formid(0x5C4033)),
        ("ECOR", _formid(0x04223F)),
        ("PRPS", PRPS),
        ("INRD", _formid(0x5B7102)),
        ("DNAM", DNAM),
        ("CVT2", _formid(0x34EF65)),
    ]
    plugin = Plugin.new("B21_Fo76NpcFields.esp", game="fo76")
    try:
        record = Record("NPC_", 0x000800, form_version=209)
        for signature, data in subrecords:
            record.add_subrecord(signature, data)
        plugin.add_record(record)
        target = tmp_path / "B21_Fo76NpcFields.esp"
        plugin.save(target)
    finally:
        plugin.close()

    result = CliRunner().invoke(cli, ["--game", "fo76", "esp", "get-record", str(target), "000800"])
    assert result.exit_code == 0, result.output
    fields = json.loads(result.output)["fields"]

    assert [field["signature"] for field in fields] == [sig for sig, _ in subrecords[1:]]
    by_signature = {field["signature"]: field for field in fields}
    assert _object_id(by_signature["AJNG"]["value"]) == "5C4037"
    assert _object_id(by_signature["AJXG"]["value"]) == "5C4033"
    assert _object_id(by_signature["ECOR"]["value"]) == "04223F"
    assert by_signature["PRPS"]["raw_hex"] == PRPS.hex().upper()
    assert _object_id(by_signature["INRD"]["value"]) == "5B7102"
    assert by_signature["DNAM"]["fields"]["CalculatedHealth"] == 35
    assert by_signature["DNAM"]["fields"]["CalculatedActionPoints"] == 100
    assert _object_id(by_signature["CVT2"]["value"]) == "34EF65"
