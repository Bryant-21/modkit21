from click.testing import CliRunner

from cli.main import cli


def test_index_build_accepts_game_after_build(monkeypatch):
    calls = []

    def fake_build_domain_index(game, domain, **kwargs):
        calls.append((game, domain, kwargs.get("embeddings"), kwargs))

    monkeypatch.setattr("creation_lib.db.index_builder.build_domain_index", fake_build_domain_index)

    result = CliRunner().invoke(
        cli, ["index", "build", "--domain", "nifs", "--game", "fo76"]
    )

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    game, domain, embeddings, kwargs = calls[0]
    assert (game, domain, embeddings) == ("fo76", "nifs", False)
    assert "project_root" in kwargs
    assert "db_dir" in kwargs
