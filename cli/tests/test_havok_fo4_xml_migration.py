from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.main import cli


REPO_ROOT = Path(__file__).resolve().parents[2]
FO4_EXTRACTED = REPO_ROOT / "extracted" / "fo4"

FO4_HAVOK_MIGRATION_FIXTURES = [
    (
        "animation",
        FO4_EXTRACTED / "Meshes" / "Actors" / "Alien" / "Animations" / "FireSingle.hkx",
    ),
    (
        "animation",
        FO4_EXTRACTED / "Meshes" / "Actors" / "Alien" / "Animations" / "Combat_Idle.hkx",
    ),
    (
        "animation",
        FO4_EXTRACTED / "Meshes" / "Actors" / "Alien" / "Animations" / "RunForward.hkx",
    ),
    (
        "behavior",
        FO4_EXTRACTED / "Meshes" / "Actors" / "Bloatfly" / "Behaviors" / "Locomotion.hkx",
    ),
    (
        "behavior",
        FO4_EXTRACTED / "Meshes" / "Actors" / "Bloatfly" / "Behaviors" / "BloatflyRootBehavior.hkx",
    ),
    (
        "behavior",
        FO4_EXTRACTED / "Meshes" / "Actors" / "Alien" / "Behaviors" / "AlienRootBehavior.hkx",
    ),
]


def _native_havok_or_skip():
    pytest.importorskip("creation_lib._native.havok_native")


def _stable_xml(xml: str) -> str:
    return xml.replace("\r\n", "\n").strip()


@pytest.mark.parametrize(
    ("asset_kind", "hkx_path"),
    FO4_HAVOK_MIGRATION_FIXTURES,
    ids=lambda value: value.name if isinstance(value, Path) else value,
)
def test_extracted_fo4_havok_hkx_xml_hkx_xml_is_stable(asset_kind: str, hkx_path: Path):
    if not hkx_path.exists():
        pytest.skip(f"missing extracted FO4 {asset_kind} fixture: {hkx_path}")
    _native_havok_or_skip()

    xml_once = hkx_path.with_suffix(".xml")
    migrated_hkx = hkx_path.with_name(f"{hkx_path.stem}.migrated.hkx")
    xml_twice = hkx_path.with_name(f"{hkx_path.stem}.migrated.xml")

    with CliRunner().isolated_filesystem() as isolated:
        work_dir = Path(isolated)
        first_xml_path = work_dir / xml_once.name
        migrated_hkx_path = work_dir / migrated_hkx.name
        second_xml_path = work_dir / xml_twice.name

        runner = CliRunner()
        unpack_once = runner.invoke(
            cli,
            ["build", "unpack-hkx", str(hkx_path), str(first_xml_path)],
        )
        assert unpack_once.exit_code == 0, unpack_once.output

        pack = runner.invoke(
            cli,
            ["build", "pack-hkx", str(first_xml_path), str(migrated_hkx_path)],
        )
        assert pack.exit_code == 0, pack.output

        unpack_twice = runner.invoke(
            cli,
            ["build", "unpack-hkx", str(migrated_hkx_path), str(second_xml_path)],
        )
        assert unpack_twice.exit_code == 0, unpack_twice.output

        assert _stable_xml(second_xml_path.read_text(encoding="utf-8")) == _stable_xml(
            first_xml_path.read_text(encoding="utf-8")
        )
