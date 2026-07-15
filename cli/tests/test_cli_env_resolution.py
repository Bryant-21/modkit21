from pathlib import Path

from click.testing import CliRunner

from cli.main import cli


def test_resolve_game_data_dir_reads_env_from_cwd_when_project_root_lookup_fails(tmp_path, monkeypatch):
    from cli.mod_commands import _resolve_game_data_dir

    (tmp_path / ".env").write_text('FO4_DIR="C:/Games/Fallout 4"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FO4_DIR", raising=False)
    monkeypatch.setattr("app.paths.get_app_root", lambda: Path("Z:/not-a-real-root"))

    resolved = _resolve_game_data_dir("fo4")

    assert resolved == Path("C:/Games/Fallout 4") / "Data"


def test_esp_build_mod_validates_local_authoring_only(tmp_path, monkeypatch):
    mod_name = "B21_TestMod"
    mod_dir = tmp_path / "mods" / mod_name
    (mod_dir / "yaml").mkdir(parents=True)
    (mod_dir / ".game").write_text("fo4", encoding="utf-8")

    seen_yaml_dirs: list[Path] = []

    def fake_validate_authoring(yaml_dir):
        seen_yaml_dirs.append(Path(yaml_dir))
        return [], 1

    def fake_deserialize(_yaml_dir, output_path, **_kwargs):
        Path(output_path).write_bytes(b"ESP")

    monkeypatch.setattr("app.paths.get_app_root", lambda: tmp_path)
    monkeypatch.setattr("creation_lib.esp.validate.validate_authoring", fake_validate_authoring)
    monkeypatch.setattr("creation_lib.esp.authoring.deserialize", fake_deserialize)
    monkeypatch.setattr("creation_lib.esp.authoring.get_plugin_ext", lambda _mod_dir: "esp")

    result = CliRunner().invoke(cli, ["--game", "fo4", "esp", "build-mod", mod_name])

    assert result.exit_code == 0, result.output
    assert seen_yaml_dirs == [mod_dir / "yaml"]
    assert (mod_dir / f"{mod_name}.esp").read_bytes() == b"ESP"
