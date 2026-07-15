from __future__ import annotations

from cli._output import output


def test_output_json_default_is_minified(capsys) -> None:
    output({"a": 1, "b": [2]})

    assert capsys.readouterr().out == '{"a":1,"b":[2]}\n'


def test_output_compact_alias_is_minified(capsys) -> None:
    output({"a": 1, "b": [2]}, "compact")

    assert capsys.readouterr().out == '{"a":1,"b":[2]}\n'


def test_output_pretty_is_indented(capsys) -> None:
    output({"a": 1, "b": [2]}, "pretty")

    assert capsys.readouterr().out == '{\n  "a": 1,\n  "b": [\n    2\n  ]\n}\n'


def test_output_table_is_unchanged(capsys) -> None:
    output([{"name": "Alpha"}], "table")

    stdout = capsys.readouterr().out
    assert "name" in stdout
    assert "Alpha" in stdout
