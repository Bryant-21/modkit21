"""File-backed NIF session store for CLI use.

Sessions persist NIF state between CLI invocations by saving to disk.
Location: ~/.modkit/sessions/<session_id>/
"""

import json
import os
import shutil
import time
import uuid

from creation_lib.nif.nif_file import NifFile

SESSION_DIR = os.path.join(os.path.expanduser("~"), ".modkit", "sessions")
MAX_AGE_SECONDS = 24 * 60 * 60  # 24 hours


def _session_path(sid: str) -> str:
    return os.path.join(SESSION_DIR, sid)


def _nif_path(sid: str) -> str:
    return os.path.join(_session_path(sid), "state.nif")


def _meta_path(sid: str) -> str:
    return os.path.join(_session_path(sid), "meta.json")


def open_session(nif: NifFile, original_path: str) -> str:
    """Save a NIF to a new session, return session ID."""
    sid = uuid.uuid4().hex[:8]
    sdir = _session_path(sid)
    os.makedirs(sdir, exist_ok=True)
    nif.save(_nif_path(sid))
    with open(_meta_path(sid), "w") as f:
        json.dump({"path": original_path, "created": time.time()}, f)
    return sid


def load_session(sid: str) -> tuple[NifFile, str]:
    """Load NIF from session. Returns (nif, original_path). Raises on missing."""
    nif_p = _nif_path(sid)
    meta_p = _meta_path(sid)
    if not os.path.isfile(nif_p):
        raise FileNotFoundError(f"No session '{sid}'")
    nif = NifFile.load(nif_p)
    original_path = ""
    if os.path.isfile(meta_p):
        with open(meta_p) as f:
            meta = json.load(f)
        original_path = meta.get("path", "")
    return nif, original_path


def save_session(sid: str, nif: NifFile):
    """Write NIF state back to session dir."""
    nif.save(_nif_path(sid))


def close_session(sid: str) -> bool:
    """Delete session directory. Returns True if existed."""
    sdir = _session_path(sid)
    if os.path.isdir(sdir):
        shutil.rmtree(sdir)
        return True
    return False


def cleanup_stale():
    """Remove sessions older than MAX_AGE_SECONDS."""
    if not os.path.isdir(SESSION_DIR):
        return
    now = time.time()
    for name in os.listdir(SESSION_DIR):
        sdir = os.path.join(SESSION_DIR, name)
        if not os.path.isdir(sdir):
            continue
        meta_p = os.path.join(sdir, "meta.json")
        try:
            if os.path.isfile(meta_p):
                with open(meta_p) as f:
                    meta = json.load(f)
                if now - meta.get("created", 0) > MAX_AGE_SECONDS:
                    shutil.rmtree(sdir)
            else:
                # No meta — check dir mtime
                if now - os.path.getmtime(sdir) > MAX_AGE_SECONDS:
                    shutil.rmtree(sdir)
        except Exception:
            pass
