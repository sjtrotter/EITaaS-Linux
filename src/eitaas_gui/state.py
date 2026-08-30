"""Per-user GUI state: the "last readiness pass" marker.

Toolkit-free persistence for ``$XDG_STATE_HOME/eitaas-gui/``. The marker holds
only a timestamp and a hash of the doctor summary (``viewmodel.ReadinessMarker``)
— never profile data, paths, or secrets — in a 0700 directory as a 0600 file.
Everything is best-effort: a missing, oversized, irregular, or unparseable
marker simply means "no recorded pass".
"""

from __future__ import annotations

import datetime
import os
import stat
from pathlib import Path

from . import viewmodel

MARKER_NAME = "last-readiness-pass.json"
_MAX_MARKER_BYTES = 4096


def state_dir() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state_home, "eitaas-gui")


def marker_path() -> Path:
    return state_dir() / MARKER_NAME


def read_marker() -> viewmodel.ReadinessMarker | None:
    """The stored marker, or None when absent, irregular, too large, or invalid."""
    path = marker_path()
    try:
        details = os.lstat(path)
        if not stat.S_ISREG(details.st_mode) or details.st_size > _MAX_MARKER_BYTES:
            return None
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return viewmodel.parse_marker(text)


def record_pass(doctor_hash: str) -> viewmodel.ReadinessMarker:
    """Persist a fresh pass marker; the write is best-effort and never raises."""
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    marker = viewmodel.ReadinessMarker(timestamp, doctor_hash)
    directory = state_dir()
    temp = directory / (MARKER_NAME + ".tmp")
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(handle, 0o600)
            os.write(handle, viewmodel.marker_document(marker).encode("utf-8"))
        finally:
            os.close(handle)
        os.replace(temp, marker_path())
    except OSError:
        try:
            os.unlink(temp)
        except OSError:
            pass
    return marker


def clear_marker() -> None:
    """Forget the recorded pass; missing files are fine."""
    try:
        os.unlink(marker_path())
    except OSError:
        pass
