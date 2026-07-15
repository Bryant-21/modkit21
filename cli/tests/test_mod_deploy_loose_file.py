from click.testing import CliRunner

from cli.main import cli


def test_deploy_loose_file_help_loads_command():
    result = CliRunner().invoke(cli, ["mod", "deploy-loose-file", "--help"])

    assert result.exit_code == 0
    assert "Deploy one mod asset as a tracked loose file" in result.output
