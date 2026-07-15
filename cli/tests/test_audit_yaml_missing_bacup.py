"""CLI tests for `modkit data audit-yaml` degrading cleanly without the bacup tree."""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cli.main import cli


def test_audit_yaml_reports_missing_bacup(monkeypatch, tmp_path: Path) -> None:
    import cli.audit_commands as ac

    monkeypatch.setattr(ac, "_WHITELIST_DIR", tmp_path / "nope" / "whitelists")

    mods_dir = tmp_path / "mods"
    (mods_dir / "SomeMod" / "yaml").mkdir(parents=True)

    result = CliRunner().invoke(
        cli,
        ["--game", "fo4", "data", "audit-yaml", "SomeMod", "--mods-dir", str(mods_dir)],
    )

    assert result.exit_code != 0
    assert "bacup" in result.output.lower()
    assert "Traceback" not in result.output
