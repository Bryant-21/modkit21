from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.main import cli
from creation_lib.esp import topology_audit


def _plugin_report(path: Path, game: str, *, form_id: str) -> dict:
    cell = {
        "form_id": form_id,
        "x": 0,
        "y": 0,
        "child_groups": 1,
        "persistent_groups": 1,
        "temporary_groups": 1,
        "visible_distant_groups": 0,
        "persistent_records": 1,
        "temporary_records": 2,
        "visible_distant_records": 0,
        "land_records": 1,
        "land_in_temporary_group": 1,
        "misplaced_land_records": 0,
        "navm_records": 1,
        "navm_in_temporary_group": 1,
        "misplaced_navm_records": 0,
    }
    summary = {
        "worldspaces": 1,
        "exterior_cells": 1,
        "unique_cell_coordinates": 1,
        "persistent_groups": 1,
        "temporary_groups": 1,
        "land_records": 1,
        "navm_records": 1,
        "valid_land_records": 1,
        "valid_navm_records": 1,
        "missing_land_cells": 0,
        "duplicate_cell_coordinates": 0,
        "duplicate_land_cells": 0,
        "flat_exterior_cells": 0,
        "flat_land_records": 0,
        "flat_navm_records": 0,
        "orphan_land_records": 0,
        "orphan_navm_records": 0,
        "misplaced_land_records": 0,
        "misplaced_navm_records": 0,
    }
    world_anomalies = {
        "duplicate_cell_coordinates": [],
        "cells_missing_coordinates": [],
        "cells_missing_child_groups": [],
        "cells_missing_land": [],
        "cells_with_duplicate_land": [],
        "orphan_cell_groups": [],
        "orphan_land_records": [],
        "orphan_navm_records": [],
        "misplaced_land_records": [],
        "misplaced_navm_records": [],
    }
    return {
        "plugin": path.name,
        "path": str(path),
        "game": game,
        "header_size": 24,
        "worldspaces": [
            {
                "editor_id": "WastelandNV",
                "form_id": form_id,
                "cells": [cell],
                "summary": {
                    "exterior_cells": 1,
                    "unique_cell_coordinates": 1,
                    "non_exterior_cells": 1,
                    "cell_child_groups": 1,
                    "persistent_groups": 1,
                    "temporary_groups": 1,
                    "visible_distant_groups": 0,
                    "persistent_records": 1,
                    "temporary_records": 2,
                    "visible_distant_records": 0,
                    "land_records": 1,
                    "navm_records": 1,
                    "valid_land_records": 1,
                    "valid_navm_records": 1,
                },
                "anomalies": world_anomalies,
            }
        ],
        "summary": summary,
        "anomalies": {
            "flat_exterior_cells": [],
            "flat_land_records": [],
            "flat_navm_records": [],
            "duplicate_record_form_ids": [],
        },
    }


def _install_fake_audit(
    monkeypatch, source: Path, output: Path, calls: list[dict]
) -> None:
    source_report = _plugin_report(source, "fnv", form_id="00000800")
    output_report = _plugin_report(output, "fo4", form_id="01001000")

    def fake_audit(source_path, output_path, *, source_game, target_game):
        calls.append(
            {
                "source_path": Path(source_path),
                "output_path": Path(output_path),
                "source_game": source_game,
                "target_game": target_game,
            }
        )
        return {
            "schema_version": 1,
            "source": source_report,
            "output": output_report,
            "equality": topology_audit.compare_topology_reports(
                source_report, output_report
            ),
        }

    monkeypatch.setattr(topology_audit, "audit_topology_pair", fake_audit)


def test_audit_topology_command_forwards_games_and_emits_json(
    tmp_path, monkeypatch
) -> None:
    source = tmp_path / "FalloutNV.esm"
    output = tmp_path / "Converted.esm"
    source.write_bytes(b"source")
    output.write_bytes(b"output")
    calls: list[dict] = []
    _install_fake_audit(monkeypatch, source, output, calls)

    result = CliRunner().invoke(
        cli,
        [
            "esp",
            "audit-topology",
            str(source),
            str(output),
            "--source-game",
            "fnv",
            "--target-game",
            "fo4",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["equality"]["equal"] is True
    assert calls == [
        {
            "source_path": source,
            "output_path": output,
            "source_game": "fnv",
            "target_game": "fo4",
        }
    ]


def test_audit_topology_command_supports_markdown_and_global_compact(
    tmp_path, monkeypatch
) -> None:
    source = tmp_path / "FalloutNV.esm"
    output = tmp_path / "Converted.esm"
    source.write_bytes(b"source")
    output.write_bytes(b"output")
    calls: list[dict] = []
    _install_fake_audit(monkeypatch, source, output, calls)
    runner = CliRunner()

    markdown = runner.invoke(
        cli,
        [
            "esp",
            "audit-topology",
            str(source),
            str(output),
            "--source-game",
            "fnv",
            "--target-game",
            "fo4",
            "--format",
            "markdown",
        ],
    )
    compact = runner.invoke(
        cli,
        [
            "--format",
            "compact",
            "esp",
            "audit-topology",
            str(source),
            str(output),
            "--source-game",
            "fnv",
            "--target-game",
            "fo4",
        ],
    )

    assert markdown.exit_code == 0, markdown.output
    assert markdown.output.startswith("# ESP topology audit\n")
    assert "**Result:** MATCH" in markdown.output
    assert compact.exit_code == 0, compact.output
    assert json.loads(compact.output)["equality"]["equal"] is True
    assert '\n  "source"' not in compact.output
