"""Repo-root pytest configuration — suite-wide safety guards.

A native OS file/folder dialog opening during a test run is always a bug: on a
headless CI runner the dialog never closes, so the run blocks in
``pick_folder._wait`` until the job's timeout kills it. This autouse fixture
replaces the pfd-backed picker helpers in ``creation_lib.ui.widgets.pick_folder``
with functions that raise, so any test that reaches a real dialog fails fast
instead of hanging.

The helpers must be patched on the actual submodule object: the ``widgets``
package re-exports ``pick_folder``/``pick_file``/``pick_save_file`` as names, so
the dotted path ``creation_lib.ui.widgets.pick_folder`` resolves to the *function*
via attribute lookup — ``import_module`` returns the module regardless. Callers
do ``from creation_lib.ui.widgets.pick_folder import pick_file`` at call time, so
patching the module attribute is what they pick up.

Patching runs during fixture setup via ``monkeypatch``; a test that legitimately
drives these helpers and patches them itself layers on top of this guard and is
restored afterwards.
"""
import importlib

import pytest


@pytest.fixture(autouse=True)
def _block_native_file_dialogs(monkeypatch):
    try:
        pick_folder_mod = importlib.import_module("creation_lib.ui.widgets.pick_folder")
    except Exception:
        yield
        return

    def _blocked(*_args, **_kwargs):
        raise RuntimeError("native dialog opened during tests")

    for name in ("pick_folder", "pick_file", "pick_save_file"):
        monkeypatch.setattr(pick_folder_mod, name, _blocked)
    yield
