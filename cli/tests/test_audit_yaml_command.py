from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli import audit_commands
from cli.main import cli

def test_audit_yaml_accepts_current_authoring_records_layout(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(audit_commands, "_PROJECT_ROOT", tmp_path)
    whitelist_dir = tmp_path / "whitelists"
    whitelist_dir.mkdir()
    monkeypatch.setattr(audit_commands, "_WHITELIST_DIR", whitelist_dir)
    (whitelist_dir / "fo4.yaml").write_text(
        "game: fo4\nrecord_types:\n  WEAP:\n  - FULL\n  - Data\n",
        encoding="utf-8",
    )

    mod_dir = tmp_path / "mods" / "B21_TestAudit"
    record_dir = mod_dir / "yaml" / "records" / "WEAP"
    record_dir.mkdir(parents=True)
    (mod_dir / ".game").write_text("fo4\n", encoding="utf-8")
    (record_dir / "TestWeapon - 000800_Test.esp.yaml").write_text(
        "\n".join(
            [
                "form_id: '000800'",
                "flags: '00000004'",
                "version_control: 0",
                "form_version: 208",
                "version2: 1",
                "eid: TestWeapon",
                "fields:",
                "- FULL: Test Weapon",
                "- Data:",
                "    Weight: 1.0",
                "    Value: 1",
                "    DamageBase: 1",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli,
        [
            "--game",
            "fo4",
            "--format",
            "json",
            "data",
            "audit-yaml",
            "B21_TestAudit",
            "--mods-dir",
            str(tmp_path / "mods"),
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["status"] == "clean"
    assert report["files_checked"] == 1
    assert report["files_with_unknowns"] == 0
    assert report["unknown_record_types"] == []
