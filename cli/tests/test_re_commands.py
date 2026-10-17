import subprocess
import sys

from click.testing import CliRunner

from cli.main import cli


def test_re_forwards_args_and_format_to_redb(monkeypatch):
    calls = []

    def fake_run(cmd, cwd=None):
        calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 3)

    monkeypatch.setattr("cli.re_commands.subprocess.run", fake_run)

    result = CliRunner().invoke(cli, ["--format", "compact", "re", "func", "TESObjectLAND", "--binary", "k"])

    assert result.exit_code == 3
    cmd, cwd = calls[0]
    assert cmd == [sys.executable, "-m", "tools.re.redb", "--format", "compact", "func", "TESObjectLAND", "--binary", "k"]
    assert (cwd / "cli" / "main.py").is_file()


def test_re_passes_help_through(monkeypatch):
    calls = []
    monkeypatch.setattr("cli.re_commands.subprocess.run",
                        lambda cmd, cwd=None: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))

    assert CliRunner().invoke(cli, ["re", "--help"]).exit_code == 0
    assert calls[0][-1] == "--help"
