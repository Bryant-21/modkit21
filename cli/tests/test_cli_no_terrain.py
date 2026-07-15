from __future__ import annotations

from click.testing import CliRunner

from cli.main import cli


def test_terrain_is_not_a_public_cli_command():
    result = CliRunner().invoke(cli, ["terrain"])

    assert result.exit_code != 0
    assert "No such command 'terrain'" in result.output
