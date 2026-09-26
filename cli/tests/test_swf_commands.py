from __future__ import annotations

from click.testing import CliRunner

from cli.main import cli


def test_swf_symbols_list_json_is_minified(monkeypatch, tmp_path) -> None:
    from creation_lib.swf import native_runtime

    swf_path = tmp_path / "menu.swf"
    swf_path.write_bytes(b"fake-swf")
    monkeypatch.setattr(native_runtime, "list_symbols", lambda _data: [(7, "MarkerIcon")])

    result = CliRunner().invoke(cli, ["swf", "symbols", "list", str(swf_path)])

    assert result.exit_code == 0, result.output
    assert result.output == '[{"character_id":7,"name":"MarkerIcon"}]\n'


def test_swf_symbols_list_pretty_is_indented(monkeypatch, tmp_path) -> None:
    from creation_lib.swf import native_runtime

    swf_path = tmp_path / "menu.swf"
    swf_path.write_bytes(b"fake-swf")
    monkeypatch.setattr(native_runtime, "list_symbols", lambda _data: [(7, "MarkerIcon")])

    result = CliRunner().invoke(
        cli,
        ["--format", "pretty", "swf", "symbols", "list", str(swf_path)],
    )

    assert result.exit_code == 0, result.output
    assert result.output == (
        '[\n'
        '  {\n'
        '    "character_id": 7,\n'
        '    "name": "MarkerIcon"\n'
        '  }\n'
        ']\n'
    )


def test_swf_abc_outline_passes_class_and_emits_json(monkeypatch, tmp_path) -> None:
    from creation_lib.swf import native_runtime

    swf_path = tmp_path / "menu.swf"
    swf_path.write_bytes(b"fake-swf")
    calls = []

    def fake(data, class_name):
        calls.append((data, class_name))
        return {"name": class_name, "super": "flash.display.MovieClip"}

    monkeypatch.setattr(native_runtime, "abc_class_outline", fake)

    result = CliRunner().invoke(cli, ["swf", "abc", "outline", str(swf_path), "ItemCard"])

    assert result.exit_code == 0, result.output
    assert calls == [(b"fake-swf", "ItemCard")]
    assert result.output == '{"name":"ItemCard","super":"flash.display.MovieClip"}\n'


def test_swf_abc_disasm_forwards_method_filter(monkeypatch, tmp_path) -> None:
    from creation_lib.swf import native_runtime

    swf_path = tmp_path / "menu.swf"
    swf_path.write_bytes(b"fake-swf")
    calls = []

    def fake(data, class_name, method=None):
        calls.append((class_name, method))
        return [{"method": "populate", "code": ["    0  GetLocal { index: 0 }"]}]

    monkeypatch.setattr(native_runtime, "abc_disassemble", fake)

    result = CliRunner().invoke(
        cli, ["swf", "abc", "disasm", str(swf_path), "ItemCard", "--method", "populate"]
    )

    assert result.exit_code == 0, result.output
    assert calls == [("ItemCard", "populate")]
    assert '"method":"populate"' in result.output


def test_swf_abc_deps_forwards_transitive_flag(monkeypatch, tmp_path) -> None:
    from creation_lib.swf import native_runtime

    swf_path = tmp_path / "menu.swf"
    swf_path.write_bytes(b"fake-swf")
    calls = []

    def fake(data, class_name, transitive=False):
        calls.append((class_name, transitive))
        return {"root": class_name, "classes": [], "external": ["Shared.AS3.BSUIComponent"]}

    monkeypatch.setattr(native_runtime, "abc_class_references", fake)

    result = CliRunner().invoke(cli, ["swf", "abc", "deps", str(swf_path), "ItemCard", "--transitive"])

    assert result.exit_code == 0, result.output
    assert calls == [("ItemCard", True)]
    assert "Shared.AS3.BSUIComponent" in result.output


def test_swf_abc_outline_reports_native_errors(monkeypatch, tmp_path) -> None:
    from creation_lib.swf import native_runtime

    swf_path = tmp_path / "menu.swf"
    swf_path.write_bytes(b"fake-swf")

    def fake(data, class_name):
        raise ValueError(f"Class '{class_name}' is not defined in this movie")

    monkeypatch.setattr(native_runtime, "abc_class_outline", fake)

    result = CliRunner().invoke(cli, ["swf", "abc", "outline", str(swf_path), "Nope"])

    assert result.exit_code == 2
    assert "is not defined" in result.stderr
