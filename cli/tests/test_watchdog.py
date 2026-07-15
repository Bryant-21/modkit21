"""Tests for the parent-death watchdog (cli/_watchdog.py).

Reproduces the lingering-process bug: when modkit's launching parent (the shell
an AI agent spawns) is killed mid-command, modkit must notice and tear itself
down instead of running its native worker threads to completion in the
background, holding memory.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

import pytest

from cli import _watchdog
from cli._watchdog import _wait_for_process_exit, install_parent_death_watchdog

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _spawn_sleeper() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def test_wait_blocks_while_parent_alive_then_returns_on_death() -> None:
    proc = _spawn_sleeper()
    result: list[bool] = []
    watcher = threading.Thread(target=lambda: result.append(_wait_for_process_exit(proc.pid)))
    watcher.start()
    try:
        watcher.join(timeout=0.5)
        assert watcher.is_alive(), "watcher returned while the parent was still alive"

        proc.kill()
        proc.wait()
        watcher.join(timeout=5.0)
        assert not watcher.is_alive(), "watcher did not notice the parent dying"
        assert result == [True]
    finally:
        if proc.poll() is None:
            proc.kill()


@pytest.mark.skipif(sys.platform != "win32", reason="exercises the Windows OpenProcess branch")
def test_wait_returns_false_when_parent_cannot_be_opened(monkeypatch) -> None:
    # When the parent handle cannot be opened, the helper must report "could not
    # observe an exit" (False), NOT "the process exited" (True) -- otherwise the
    # watchdog would force-exit modkit immediately on startup.
    monkeypatch.setattr(_watchdog._kernel32, "OpenProcess", lambda *a: 0)
    assert _wait_for_process_exit(123456) is False


def test_watchdog_fires_on_exit_when_parent_dies() -> None:
    proc = _spawn_sleeper()
    fired = threading.Event()
    install_parent_death_watchdog(on_exit=lambda code: fired.set(), parent_pid=proc.pid)
    try:
        assert not fired.wait(timeout=0.5), "watchdog fired while the parent was alive"
        proc.kill()
        proc.wait()
        assert fired.wait(timeout=5.0), "watchdog did not fire after the parent died"
    finally:
        if proc.poll() is None:
            proc.kill()


@pytest.mark.skipif(sys.platform != "win32", reason="exercises the Windows OpenProcess branch")
def test_watchdog_does_not_fire_when_parent_cannot_be_opened(monkeypatch) -> None:
    monkeypatch.setattr(_watchdog._kernel32, "OpenProcess", lambda *a: 0)
    fired = threading.Event()
    install_parent_death_watchdog(on_exit=lambda code: fired.set(), parent_pid=123456)
    assert not fired.wait(timeout=0.5), "watchdog force-exited on an unwatchable parent"


def _wait_for_file(path: Path, timeout: float) -> bool:
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return path.exists()


def test_watchdog_force_exits_process_when_watched_parent_dies(tmp_path: Path) -> None:
    """End-to-end across real process boundaries: a process running the real
    watchdog must force-exit when the process it watches dies -- the exact
    orphaning that happens when an agent kills the shell that launched modkit.

    The watched pid is read from the victim itself and killed by that same pid,
    so the test is immune to the python-launcher trampolines that `uv` inserts
    between subprocess.Popen and the real interpreter."""
    import os
    import signal

    ready = tmp_path / "ready"
    fired = tmp_path / "fired"
    vpid_file = tmp_path / "vpid"

    victim = subprocess.Popen(
        [sys.executable, "-c", f"import os, time; open(r'{vpid_file}', 'w').write(str(os.getpid())); time.sleep(120)"]
    )
    try:
        assert _wait_for_file(vpid_file, timeout=15.0), "victim never reported its pid"
        watched_pid = int(vpid_file.read_text())

        worker_src = tmp_path / "worker.py"
        worker_src.write_text(
            "import os, sys, time\n"
            f"sys.path.insert(0, r'{_REPO_ROOT}')\n"
            "from cli._watchdog import install_parent_death_watchdog\n"
            f"def on_exit(code):\n    open(r'{fired}', 'w').close()\n    os._exit(code)\n"
            f"install_parent_death_watchdog(on_exit=on_exit, parent_pid={watched_pid})\n"
            f"open(r'{ready}', 'w').close()\n"
            "time.sleep(120)\n",
            encoding="utf-8",
        )
        worker = subprocess.Popen([sys.executable, str(worker_src)])
        try:
            assert _wait_for_file(ready, timeout=15.0), "worker never installed the watchdog"
            assert not fired.exists(), "watchdog fired while the watched process was alive"

            os.kill(watched_pid, signal.SIGTERM)  # Windows: TerminateProcess
            assert _wait_for_file(fired, timeout=10.0), "watchdog did not force-exit after the watched process died"
        finally:
            if worker.poll() is None:
                worker.kill()
    finally:
        if victim.poll() is None:
            victim.kill()
        try:
            os.kill(int(vpid_file.read_text()), signal.SIGTERM)
        except Exception:
            pass
