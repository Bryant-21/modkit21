from __future__ import annotations

from click.testing import CliRunner

from cli.main import cli


def test_modkit_does_not_expose_schema_group() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "schema" not in result.output.split()


def test_modkit_schema_group_is_unknown_command() -> None:
    result = CliRunner().invoke(cli, ["schema", "--help"])
    assert result.exit_code != 0
    assert "No such command 'schema'" in result.output
