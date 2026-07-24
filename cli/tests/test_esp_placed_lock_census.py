from __future__ import annotations

from cli.esp_commands import _xloc_level


def test_xloc_level_reads_first_byte() -> None:
    assert _xloc_level([("NAME", b"\x01\x02", None), ("XLOC", b"\x4b" + b"\0" * 15, None)]) == 75


def test_xloc_level_handles_absent_or_empty_payload() -> None:
    assert _xloc_level([("NAME", b"\0" * 4, None)]) is None
    assert _xloc_level([("XLOC", b"", None)]) is None
