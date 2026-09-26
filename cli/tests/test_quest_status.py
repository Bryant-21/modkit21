import json
import struct

from click.testing import CliRunner

from cli.main import cli
from cli.tests.test_inspection_queries import script
from cli.tests.test_quest_papyrus import fixture, source
from creation_lib.esp import Group, Plugin, PluginHeader, Record, Subrecord


def run(path, src, *args):
    result = CliRunner().invoke(cli, ["esp", "quest-status", str(path), *args, "--source-root", str(src)])
    assert result.exit_code == 0, result.output or repr(result.exception)
    return json.loads(result.output)["data"]


def test_reports_empty_and_inherited_stage_fragments(tmp_path):
    path, src = tmp_path / "B21_Audit.esp", tmp_path / "src"
    fixture(path, src)
    report, missing = run(path, src, "B21_Quest", "000999")
    assert report["found"] and report["editor_id"] == "B21_Quest"
    assert report["summary"]["stages"] == 2
    status = {f["fragment"]: f["status"] for f in report["fragments"]}
    assert status == {"First": "implemented", "Second": "empty"}
    assert report["summary"]["open_quest_fragments"] == 1
    assert not report["start"]["event_scoped"]
    assert missing == {"query": "000999", "found": False, "issues": ["not_found"]}


def test_pending_patch_members_are_not_counted_as_open(tmp_path):
    path, src, patches = tmp_path / "B21_Audit.esp", tmp_path / "src", tmp_path / "patches"
    fixture(path, src)
    source(patches, "B21:QF", "Function Second()\n    SetStage(30)\nEndFunction\n")
    report, = run(path, src, "B21_Quest", "--pending-root", str(patches))
    assert report["summary"]["open_quest_fragments"] == 0
    assert report["summary"]["pending_quest_fragments"] == 1


def test_scene_owned_through_raw_pnam_is_linked(tmp_path):
    path, src = tmp_path / "B21_Linked.esp", tmp_path / "src"
    source(src, "B21:SceneScript", "Scriptname B21:SceneScript\n")
    quest = Record("QUST", 0x800, subrecords=[Subrecord("EDID", b"B21_Quest\0")])
    scene = Record("SCEN", 0x801, subrecords=[Subrecord("EDID", b"B21_Scene\0"),
        Subrecord("VMAD", struct.pack("<HHH", 6, 2, 1) + script("B21:SceneScript")),
        Subrecord("PNAM", struct.pack("<I", 0x800))])
    with Plugin(plugin_name=path.name, file_path=path, game="fo4", header=PluginHeader(masters=[]), root_items=[
            Group(b"QUST", 0, children=[quest]), Group(b"SCEN", 0, children=[scene])]) as plugin:
        plugin.save(path)
    report, = run(path, src, "--all-quests")
    assert [(entry["editor_id"], entry["via"], entry["scripts"]) for entry in report["linked"]] == [
        ("B21_Scene", "owner", ["B21:SceneScript"])]
