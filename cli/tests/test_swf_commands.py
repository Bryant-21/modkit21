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
