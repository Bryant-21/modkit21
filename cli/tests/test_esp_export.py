from __future__ import annotations

from contextlib import contextmanager

from click.testing import CliRunner

from cli.main import cli


class FakePlugin:
    plugin_name = "Fake.esp"


@contextmanager
def fake_load_plugin(*_args, **_kwargs):
    yield FakePlugin()


def test_esp_export_json_stdout_is_minified(monkeypatch, tmp_path) -> None:
    import creation_lib.esp

    plugin_path = tmp_path / "Fake.esp"
    plugin_path.write_bytes(b"fake-plugin")
    monkeypatch.setattr("cli.esp_commands._load_plugin", fake_load_plugin)
    monkeypatch.setattr(
        creation_lib.esp,
        "export_json",
        lambda _plugin, *, mode, backend: '{\n  "b": 2,\n  "a": [\n    1\n  ]\n}',
    )

    result = CliRunner().invoke(
        cli,
        ["esp", "export", str(plugin_path), "--encoding", "json"],
    )

    assert result.exit_code == 0, result.output
    assert result.output == '{"b":2,"a":[1]}\n'


def test_esp_export_json_stdout_can_be_pretty(monkeypatch, tmp_path) -> None:
    import creation_lib.esp

    plugin_path = tmp_path / "Fake.esp"
    plugin_path.write_bytes(b"fake-plugin")
    monkeypatch.setattr("cli.esp_commands._load_plugin", fake_load_plugin)
    monkeypatch.setattr(
        creation_lib.esp,
        "export_json",
        lambda _plugin, *, mode, backend: '{"b":2,"a":[1]}',
    )

    result = CliRunner().invoke(
        cli,
        ["--format", "pretty", "esp", "export", str(plugin_path), "--encoding", "json"],
    )

    assert result.exit_code == 0, result.output
    assert result.output == '{\n  "b": 2,\n  "a": [\n    1\n  ]\n}\n'


def test_esp_export_json_file_is_minified(monkeypatch, tmp_path) -> None:
    import creation_lib.esp

    plugin_path = tmp_path / "Fake.esp"
    output_path = tmp_path / "export.json"
    plugin_path.write_bytes(b"fake-plugin")
    monkeypatch.setattr("cli.esp_commands._load_plugin", fake_load_plugin)
    monkeypatch.setattr(
        creation_lib.esp,
        "export_json",
        lambda _plugin, *, mode, backend: '{\n  "b": 2,\n  "a": [\n    1\n  ]\n}',
    )

    result = CliRunner().invoke(
        cli,
        [
            "esp",
            "export",
            str(plugin_path),
            "--encoding",
            "json",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output_path.read_text(encoding="utf-8") == '{"b":2,"a":[1]}'
