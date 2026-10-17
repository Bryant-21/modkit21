from __future__ import annotations

import json

from click.testing import CliRunner

from cli.main import cli


def _fake_report(dry_run: bool) -> dict:
    report = {
        "dry_run": dry_run,
        "summary": {"units": 2, "upgrade": 1, "skipped": 1},
        "units": [{"key": "materials/a.bgsm"}],
        "texture_outputs": ["textures/a_l.dds"],
    }
    if not dry_run:
        report["result"] = {"written": ["materials/a.bgsm", "textures/a_l.dds"], "errors": [], "cancelled": False}
    return report


def test_upgrade_v22_dry_run_maps_options(monkeypatch, tmp_path) -> None:
    from creation_lib.material_tools import upgrade_v22

    seen = []
    monkeypatch.setattr(upgrade_v22, "plan", lambda options: seen.append(options) or _fake_report(True))
    exclude = tmp_path / "replace.txt"
    exclude.write_text("materials/b.bgsm\n\n", encoding="utf-8")

    result = CliRunner().invoke(cli, [
        "material", "upgrade-v22", str(tmp_path), "--dry-run", "--class", "metal", "--class", "wood",
        "--metal", "envmap", "--smoothness-gain", "1.2", "--knee", "0.5", "--nifs", "--exclude-file", str(exclude),
    ])

    assert result.exit_code == 0, result.output
    (options,) = seen
    assert options.classes == ["metal", "wood"] and options.metal_mode == "envmap"
    assert options.smoothness_gain == 1.2 and options.knee == 0.5 and options.include_nifs
    assert options.exclude_paths == ["materials/b.bgsm"]
    report = json.loads(result.output)
    assert report["summary"]["upgrade"] == 1 and "units" not in report


def test_upgrade_v22_requires_output_unless_dry_run(tmp_path) -> None:
    result = CliRunner().invoke(cli, ["material", "upgrade-v22", str(tmp_path)])
    assert result.exit_code != 0


def test_upgrade_v22_run_counts_written_files(monkeypatch, tmp_path) -> None:
    from creation_lib.material_tools import upgrade_v22

    monkeypatch.setattr(upgrade_v22, "run", lambda options, progress=None: _fake_report(False))
    result = CliRunner().invoke(cli, ["material", "upgrade-v22", str(tmp_path), "-o", str(tmp_path / "out")])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["result"]["written"] == 2


def test_upgrade_v22_terrain_maps_worldspaces(monkeypatch, tmp_path) -> None:
    from creation_lib.material_tools import upgrade_v22

    seen = []
    monkeypatch.setattr(upgrade_v22, "plan", lambda options: seen.append(options) or _fake_report(True))
    plugin = tmp_path / "Fallout4.esm"
    plugin.write_bytes(b"TES4")
    result = CliRunner().invoke(cli, [
        "material", "upgrade-v22", str(tmp_path), "--dry-run", "--terrain", "--plugin", str(plugin),
        "--worldspace", "Commonwealth", "--worldspace", "SanctuaryHillsWorld",
    ])
    assert result.exit_code == 0, result.output
    (options,) = seen
    assert options.include_terrain and options.terrain_sidecars
    assert options.terrain_worldspaces == ["Commonwealth", "SanctuaryHillsWorld"]
    assert json.loads(options.to_json())["terrain_worldspaces"] == ["Commonwealth", "SanctuaryHillsWorld"]
