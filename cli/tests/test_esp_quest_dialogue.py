import json
import struct

from click.testing import CliRunner

from cli.main import cli
from creation_lib.esp import Group, Plugin, PluginHeader, Record, Subrecord


def make_plugin(path, *, count=2):
    quest = Record("QUST", 0x01000800, subrecords=[Subrecord("EDID", b"B21_Selected\0")])
    other = Record("QUST", 0x01000801, subrecords=[Subrecord("EDID", b"B21_Other\0")])
    topics = []
    for topic_id, owner, infos in [(0x01000900, quest.form_id, [0x01000910, 0x01000911]),
                                    (0x01000901, other.form_id, [0x01000912])]:
        topics.append(Record("DIAL", topic_id, subrecords=[
            Subrecord("QNAM", struct.pack("<I", owner)),
            Subrecord("TIFC", struct.pack("<I", count if owner == quest.form_id else 1)),
        ]))
        topics.append(Group(struct.pack("<I", topic_id), 7, children=[
            Record("INFO", info, subrecords=[Subrecord("NAM1", b"Test response\0")]) for info in infos
        ]))
    plugin = Plugin(plugin_name=path.name, file_path=path, game="fo4",
                    header=PluginHeader(masters=["Fallout4.esm"], master_sizes=[0]),
                    root_items=[Group(b"QUST", 0, children=[quest, other]), Group(b"DIAL", 0, children=topics)])
    try:
        plugin.save(path)
    finally:
        plugin.close()


def run(path, *quests):
    return CliRunner().invoke(cli, ["--game", "fo4", "esp", "quest-dialogue", str(path), *quests])


def test_follows_topic_groups_and_excludes_other_quest(tmp_path):
    path = tmp_path / "B21_Dialogue.esp"
    make_plugin(path)
    result = run(path, "B21_Selected")
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["meta"]["complete"]
    assert report["meta"]["topics"] == 1
    assert report["data"][0]["info_form_ids"] == ["01000910", "01000911"]
    by_id = run(path, "000800")
    assert by_id.exit_code == 0, by_id.output
    assert json.loads(by_id.output) == report


def test_count_mismatch_reports_incomplete_and_multiple_quests_work(tmp_path):
    path = tmp_path / "B21_Dialogue.esp"
    make_plugin(path, count=3)
    result = run(path, "B21_Selected", "B21_Other")
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["meta"]["topics"] == 2
    assert report["meta"]["infos"] == 3
    assert not report["meta"]["complete"]
    assert report["meta"]["issues"] == [{"topic": "01000900", "expected_infos": 3, "returned_infos": 2}]


def test_missing_or_nonquest_id_fails(tmp_path):
    path = tmp_path / "B21_Dialogue.esp"
    make_plugin(path)
    for quest_id in ("B21_Missing", "000900"):
        result = run(path, quest_id)
        assert result.exit_code != 0
        assert "Quest not found or ambiguous" in result.output
