import json
import os
import struct

from click.testing import CliRunner

from cli.main import cli
from cli.tests.test_inspection_queries import script, string
from creation_lib.esp import Group, Plugin, PluginHeader, Record, Subrecord
from creation_lib.inspection.papyrus import PapyrusSources, audit_binding


def source(root, name, text):
    path = root.joinpath(*name.split(":")).with_suffix(".psc")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def fixture(path, src):
    source(src, "Quest", "Scriptname Quest\nBool Function SetStage(int stage) Native\n")
    source(src, "Scene", "Scriptname Scene\n")
    source(src, "ObjectReference", "Scriptname ObjectReference\n")
    source(src, "Game", "Scriptname Game\n")
    source(src, "B21:Base", """Scriptname B21:Base extends Quest
Int Property NextStage Auto
Function First()
  ; SetStage(999) is a comment.
  string example = "SetStage(999)"
  SetStage(NextStage)
EndFunction
""")
    source(src, "B21:QF", """Scriptname B21:QF extends B21:Base
Function Second()
EndFunction
""")
    source(src, "B21:Activator", """Scriptname B21:Activator extends ObjectReference
Quest Property Target Auto
Int Property Destination Auto
Auto State Ready
Event OnActivate(ObjectReference actor)
  Target.SetStage(Destination)
  Game.GetFormFromFile(0x805, "B21_Audit.esp")
EndEvent
EndState
""")
    prop = string("NextStage") + bytes([3, 1]) + struct.pack("<i", 30)
    tail = bytes([3]) + struct.pack("<H", 2) + script("B21:QF", prop, 1)
    for index, name in enumerate(("First", "Second")):
        tail += struct.pack("<Hhib", 20, 0, index, 0) + string("B21:QF") + string(name)
    tail += struct.pack("<H", 0)
    quest = Record("QUST", 0x800, subrecords=[Subrecord("EDID", b"B21_Quest\0"),
        Subrecord("VMAD", struct.pack("<HHH", 6, 2, 0) + tail),
        Subrecord("INDX", struct.pack("<HBB", 20, 0, 0)), Subrecord("QSDT", b"\0"), Subrecord("NAM2", b"First item\0"),
        Subrecord("QSDT", b"\0"), Subrecord("NAM2", b"Conditional item\0"),
        Subrecord("INDX", struct.pack("<HBB", 30, 0, 0)), Subrecord("QSDT", b"\0")])
    props = string("Target") + bytes([1, 1]) + struct.pack("<HhI", 0, -1, 0x800)
    props += string("Destination") + bytes([3, 1]) + struct.pack("<i", 20)
    activator = Record("ACTI", 0x801, subrecords=[Subrecord("EDID", b"UnrelatedPrefix\0"),
        Subrecord("VMAD", struct.pack("<HHH", 6, 2, 1) + script("B21:Activator", props, 2))])
    scene = Record("SCEN", 0x802, subrecords=[Subrecord("PNAM", struct.pack("<I", 0x800)),
        Subrecord("SCQS", struct.pack("<hh", 30, -1))])
    topic = Record("DIAL", 0x803, subrecords=[Subrecord("QNAM", struct.pack("<I", 0x800)), Subrecord("TIFC", struct.pack("<I", 1))])
    info = Record("INFO", 0x804, subrecords=[Subrecord("NAM1", b"Unnamed dialogue\0")])
    literal = Record("ACTI", 0x805, subrecords=[Subrecord("EDID", b"LiteralOnly\0")])
    with Plugin(plugin_name=path.name, file_path=path, game="fo4", header=PluginHeader(masters=[]), root_items=[
        Group(b"QUST", 0, children=[quest]), Group(b"ACTI", 0, children=[activator, literal]),
        Group(b"SCEN", 0, children=[scene]), Group(b"DIAL", 0, children=[topic,
            Group(struct.pack("<I", 0x803), 7, children=[info])])]) as plugin:
        plugin.save(path)


def run(path, src, *options, global_options=()):
    return CliRunner().invoke(cli, [*global_options, "esp", "quest-papyrus", str(path), "B21_Quest", "--source-root", str(src), *options])


def test_binary_closure_inherited_callback_stage_items_and_native_producers(tmp_path):
    path, src = tmp_path / "B21_Audit.esp", tmp_path / "src"
    fixture(path, src)
    before = path.read_bytes()
    result = run(path, src)
    assert result.exit_code == 0, result.output or repr(result.exception)
    report = json.loads(result.output)["data"][0]
    assert {r["form_key"] for r in report["records"]} == {f"B21_Audit.esp:{n:06X}" for n in range(0x800, 0x806)}
    assert {s["script"] for s in report["scripts"]} >= {"B21:QF", "B21:Base", "Quest", "Game"}
    assert report["completeness"]["records"]
    assert report["completeness"]["sources"]
    assert not report["completeness"]["callbacks"]
    stage = report["quests"][0]["stages"][0]
    assert stage["stage"] == 20
    first, second = stage["items"]
    assert first["callbacks"][0]["name"] == "First"
    assert first["callbacks"][0]["bodies"][0]["inherited"]
    assert second["callbacks"][0]["status"] == "empty"
    assert {p["stage"] for p in report["stage_producers"]} == {20, 30}
    assert any(p["kind"] == "record" and p["stage"] == 30 for p in report["stage_producers"])
    prop = next(b for b in report["bindings"] if b["script"] == "B21:QF")["property_coverage"][0]
    assert prop["declared_by"] == "B21:Base"
    assert prop["status"] == "used"
    assert path.read_bytes() == before


def test_complete_then_limits_fail_even_when_rows_are_hidden(tmp_path):
    path, src = tmp_path / "B21_Audit.esp", tmp_path / "src"
    fixture(path, src)
    source(src, "B21:QF", "Scriptname B21:QF extends B21:Base\nFunction Second()\nSetStage(30)\nEndFunction\n")
    result = run(path, src, "--fail-on-incomplete", "--max-records", "0", "--max-scripts", "0")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["meta"]["complete"]
    result = run(path, src, "--max-records", "1", "--fail-on-incomplete", global_options=("--limit", "0"))
    assert result.exit_code == 1
    assert not json.loads(result.output)["meta"]["complete"]
    assert json.loads(result.output)["data"] == []


def test_source_precedence_hash_comparison_and_pex_timestamp_is_not_proof(tmp_path):
    path, src, merged = tmp_path / "B21_Audit.esp", tmp_path / "src", tmp_path / "merged"
    fixture(path, src)
    psc = source(merged, "B21:QF", "Scriptname B21:QF extends B21:Base\nFunction Second()\nSetStage(30)\nEndFunction\n")
    output = tmp_path / "data/Scripts/B21/QF.pex"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"a fixture, not evidence of a source match")
    os.utime(output, ns=(1, 1))
    result = run(path, src, "--source-root", str(merged), "--generated-source-root", str(src))
    assert result.exit_code == 0, result.output
    qf = next(s for s in json.loads(result.output)["data"][0]["scripts"] if s["script"] == "B21:QF")
    assert qf["path"] == str(psc)
    assert qf["generated_source"]["status"] == "different"
    assert qf["output"]["status"] == "older_than_source"
    os.utime(output, ns=(psc.stat().st_mtime_ns + 10**9,) * 2)
    result = run(path, src, "--source-root", str(merged))
    qf = next(s for s in json.loads(result.output)["data"][0]["scripts"] if s["script"] == "B21:QF")
    assert qf["output"]["status"] == "unverified"


def test_missing_invalid_parent_cycles_and_dynamic_stage_values(tmp_path):
    source(tmp_path, "B21_Child", """Scriptname B21_Child extends Missing
Quest Property Target Auto
Event OnInit()
  Target.SetStage(GetStageValue())
EndEvent
""")
    sources = PapyrusSources([tmp_path])
    binding = {"script": "B21_Child", "scope": "record", "properties": [{"propertyName": "Target", "Value": 123}]}
    row = audit_binding(binding, sources, record_key="B21_Test.esp:000800", owner=None, signature="ACTI")
    assert row["inheritance_issue"] == "incomplete_inheritance"
    assert row["stage_producers"][0]["status"] == "unresolved"
    source(tmp_path, "Missing", "Scriptname Missing extends B21_Child\n")
    assert PapyrusSources([tmp_path]).lineage("B21_Child")[1] == "inheritance_cycle"
    source(tmp_path, "Broken", "Function MethodOnlyPatch()\nEndFunction\n")
    assert PapyrusSources([tmp_path]).get("Broken")["status"] == "invalid"


def test_property_shadowing_and_named_states(tmp_path):
    source(tmp_path, "B21_Test", """Scriptname B21_Test
Int Property Count Auto
Function Default()
  Int Count = 10
  Debug.Trace(Count)
EndFunction
State Ready
Event OnBeginState(string previous)
  Debug.Trace(Self.Count)
EndEvent
EndState
""")
    row = audit_binding({"script": "B21_Test", "scope": "record", "properties": [{"propertyName": "Count", "Value": 20}]},
                        PapyrusSources([tmp_path]), record_key="B21.esp:000800", owner=None, signature="ACTI")
    uses = row["property_coverage"][0]["uses"]
    assert [u["member"] for u in uses] == ["OnBeginState"]
    assert row["callbacks"][0]["state"] == "Ready"


def test_missing_sources_and_script_limit_cannot_pass_coverage(tmp_path):
    path, src = tmp_path / "B21_Audit.esp", tmp_path / "src"
    fixture(path, src)
    result = run(path, src, "--max-scripts", "1", "--fail-on-incomplete")
    assert result.exit_code == 1
    report = json.loads(result.output)["data"][0]
    assert report["counts"]["scripts"] == 1
    assert report["limits"]["pending_scripts"]
    assert not report["completeness"]["sources"]
    assert any(b.get("callback_status") == "incomplete_source" for b in report["bindings"])
    (src / "B21/Base.psc").unlink()
    result = run(path, src, "--fail-on-incomplete")
    assert result.exit_code == 1
    report = json.loads(result.output)["data"][0]
    assert next(s for s in report["scripts"] if s["script"] == "B21:Base")["status"] == "missing"


def test_flat_binding_query_preserves_unfiltered_completeness(tmp_path):
    path, src = tmp_path / "B21_Audit.esp", tmp_path / "src"
    fixture(path, src)
    result = run(path, src, "--fail-on-incomplete", global_options=("--items", "bindings", "--where", "callback_status=empty",
                            "--fields", "root_quest,fragment.FragmentName,callback_status"))
    assert result.exit_code == 1
    report = json.loads(result.output)
    assert report["data"] == [{"root_quest": {"form_key": "B21_Audit.esp:000800", "editor_id": "B21_Quest"},
                               "fragment.FragmentName": "Second", "callback_status": "empty"}]
    assert not report["meta"]["complete"]


def test_output_cannot_overwrite_a_source_selected_through_a_directory(tmp_path):
    path, src = tmp_path / "B21_Audit.esp", tmp_path / "src"
    fixture(path, src)
    psc = src / "B21/QF.psc"
    before = psc.read_bytes()
    result = run(path, src, global_options=("--output", str(psc)))
    assert result.exit_code == 2
    assert psc.read_bytes() == before


def test_unmatched_item_and_undecoded_stage_are_reported(tmp_path):
    path, src = tmp_path / "B21_Audit.esp", tmp_path / "src"
    fixture(path, src)
    with Plugin.load(path, game="fo4", backend="native") as plugin:
        quest = plugin.read_authoring_record(0x800)
        quest["signature"] = "QUST"
        quest["fields"].append({"INDX": {"raw_hex": "01"}})
        plugin.upsert_authoring_record(quest)
        plugin.save(path)
    result = run(path, src)
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)["data"][0]
    assert any(i["code"] == "UNDECODED_STAGE" for i in report["issues"])


def test_imported_helper_stage_producer_and_exact_script_limit(tmp_path):
    path, src = tmp_path / "B21_Audit.esp", tmp_path / "src"
    fixture(path, src)
    source(src, "B21:QF", """Scriptname B21:QF extends B21:Base
Import B21_Helper
Function Second()
  Advance()
EndFunction
""")
    source(src, "B21_Helper", """Scriptname B21_Helper
Function Advance() Global
  (Game.GetFormFromFile(0x800, "B21_Audit.esp") as Quest).SetStage(30)
EndFunction
""")
    result = run(path, src, "--max-scripts", "7", "--fail-on-incomplete")
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)["data"][0]
    assert report["counts"]["scripts"] == 7
    producer = next(p for p in report["stage_producers"] if p.get("script") == "B21_Helper")
    assert producer["target"] == "B21_Audit.esp:000800"
    assert producer["stage"] == 30
    assert producer["binding_path"] is None


def test_stage_producer_points_to_a_missing_stage(tmp_path):
    path, src = tmp_path / "B21_Audit.esp", tmp_path / "src"
    fixture(path, src)
    source(src, "B21:QF", "Scriptname B21:QF extends B21:Base\nFunction Second()\nSetStage(1234)\nEndFunction\n")
    result = run(path, src, "--fail-on-incomplete")
    assert result.exit_code == 1
    report = json.loads(result.output)["data"][0]
    producer = next(p for p in report["stage_producers"] if p["stage"] == 1234)
    assert producer["status"] == "missing_stage"
    assert producer["target_stage_declared"] is False
    assert not report["completeness"]["stage_targets"]
