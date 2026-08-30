"""Read-only discovery of the bundled one-shot ``eitaas-remmina`` client.

The product client is the isolated Remmina + FreeRDP pair packaged from
``packaging/remmina``. Python never constructs RDP arguments; it only locates
the launcher and reports what the installed bundle contains.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from .profile import ProfileError, validate_profile
from .redaction import redact

LAUNCHER = "eitaas-remmina"
INSTALLED_LAUNCHER = Path("/usr/bin/eitaas-remmina")
PRIVATE_CLIENTS = (
    Path("/usr/libexec/eitaas-remmina/bin/remmina"),
    Path("/usr/lib/eitaas-remmina/bin/remmina"),
)
# Every recipe installs the pinned-source manifest (the bundle SSOT) here.
INSTALLED_MANIFEST = Path("/usr/share/doc/eitaas-remmina/sources.json")
UNKNOWN_VERSION = "unknown"
_SSO_MIB_SONAME = b"libsso-mib.so"
_MAX_LIBRARY_SCAN = 64 * 1024 * 1024


def find_launcher() -> str | None:
    """Return the packaged launcher, else the first on PATH, without executing it."""
    if os.access(INSTALLED_LAUNCHER, os.X_OK) and INSTALLED_LAUNCHER.is_file():
        return str(INSTALLED_LAUNCHER)
    return shutil.which(LAUNCHER)


def validate_launch_profile(path_value: str | os.PathLike[str]) -> Path:
    """Apply the Python profile checks plus the launcher's ``.rdpw`` rule."""
    path = validate_profile(path_value)
    if path.suffix.lower() != ".rdpw":
        raise ProfileError("eitaas-remmina accepts only .rdpw profiles")
    return path


def private_client() -> Path | None:
    """Return the first private-prefix Remmina binary the launcher would exec."""
    for candidate in PRIVATE_CLIENTS:
        if candidate.is_file():
            return candidate
    return None


def pinned_versions(manifest: Path | None = None) -> dict[str, str]:
    """Read Remmina/FreeRDP pins from the installed manifest, else "unknown"."""
    versions = {"remmina": UNKNOWN_VERSION, "freerdp": UNKNOWN_VERSION}
    try:
        data = json.loads((manifest or INSTALLED_MANIFEST).read_text(encoding="utf-8"))
        sources = data.get("sources", {})
        for name in versions:
            version = sources.get(name, {}).get("version")
            if isinstance(version, str) and version:
                versions[name] = version
    except (OSError, ValueError, AttributeError):
        pass
    return versions


def sso_mib_builtin(client: Path | None) -> bool | None:
    """Report whether the bundle's FreeRDP client library links SSO-MIB.

    This reflects build-time linkage only, not whether an identity broker is
    running (see ``identity_broker_available``). The linkage is read from the
    library's dynamic string table (no process is executed). Returns None when
    no library is available to inspect.
    """
    if client is None:
        return None
    prefix = client.parent.parent
    libraries = sorted(prefix.glob("lib*/libfreerdp-client3.so.3*"))
    if not libraries:
        return None
    for library in libraries:
        try:
            if library.stat().st_size > _MAX_LIBRARY_SCAN:
                continue
            if _SSO_MIB_SONAME in library.read_bytes():
                return True
        except OSError:
            continue
    return False


def identity_broker_available() -> bool:
    """Check D-Bus registration without activating the identity broker."""
    gdbus = shutil.which("gdbus")
    if not gdbus:
        return False
    for method in ("ListNames", "ListActivatableNames"):
        try:
            result = subprocess.run(
                [
                    gdbus,
                    "call",
                    "--session",
                    "--dest",
                    "org.freedesktop.DBus",
                    "--object-path",
                    "/org/freedesktop/DBus",
                    "--method",
                    f"org.freedesktop.DBus.{method}",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if result.returncode == 0 and "'com.microsoft.identity.broker1'" in result.stdout:
            return True
    return False


def status() -> dict[str, object]:
    """Describe the installed bundle for ``eitaas doctor``."""
    client = private_client()
    versions = pinned_versions()
    return {
        "launcher": find_launcher() is not None,
        "client": client is not None,
        "client_path": str(client) if client else None,
        "remmina_version": versions["remmina"],
        "freerdp_version": versions["freerdp"],
        "sso_mib": sso_mib_builtin(client),
    }


# ----- per-session diagnostic log ----------------------------------------
#
# ``Application.launch`` writes the child's merged stdout/stderr here, line by
# line and only after ``redaction.redact``. The directory is private to the
# user, every file is 0600 and size-capped, and only the newest files are
# kept, so a person without a terminal can still hand a log to support.

SESSION_LOG_DIR_NAME = "logs"
SESSION_LOG_PREFIX = "session-"
SESSION_LOG_SUFFIX = ".log"
SESSION_LOG_LIMIT = 2 * 1024 * 1024
SESSION_LOG_KEEP = 5
# A log younger than this is assumed to belong to a launch still running and
# is never pruned by another launch's rotation.
SESSION_LOG_ACTIVE_SECONDS = 60
SESSION_LOG_TRUNCATED = "[log truncated at size limit]"
# Lines worth surfacing to a user after a failed connection: the stable
# reason codes from the bundled client and any Remmina warning.
REASON_LINE_MARKERS = ("smartcard-auth:", "-WARNING")
REASON_LINE_COUNT = 5
# A smart-card stage that ended in an error dialog, whatever the exit status.
WARNING_LINE_MARKERS = ("smartcard-auth:", "WARNING")


def session_log_dir() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state_home, "eitaas-remmina", SESSION_LOG_DIR_NAME)


def _session_logs(directory: Path) -> list[Path]:
    """Session logs oldest first; names sort by their timestamp."""
    try:
        entries = [
            entry
            for entry in directory.iterdir()
            if entry.name.startswith(SESSION_LOG_PREFIX) and entry.name.endswith(SESSION_LOG_SUFFIX)
        ]
    except OSError:
        return []
    return sorted(entries, key=lambda entry: entry.name)


def latest_session_log(directory: Path | None = None) -> str | None:
    """Path of the newest session log, or None when no launch has been logged."""
    logs = _session_logs(directory or session_log_dir())
    return str(logs[-1]) if logs else None


def running_remmina_instances() -> int:
    """Count processes named ``remmina`` by scanning /proc; no subprocess is run.

    A private client that shares a GApplication id with an already running
    Remmina would hand its command line to that primary instance instead of
    connecting itself, so the count is recorded at the top of every session log.
    """
    count = 0
    try:
        entries = os.listdir("/proc")
    except OSError:
        return 0
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/comm", encoding="utf-8", errors="replace") as handle:
                if handle.read().strip() == "remmina":
                    count += 1
        except OSError:
            continue
    return count


def reason_lines(text: str, limit: int = REASON_LINE_COUNT) -> tuple[str, ...]:
    """The last ``limit`` lines of a session log that carry a reason code or warning."""
    matches = [line for line in text.splitlines() if any(marker in line for marker in REASON_LINE_MARKERS)]
    return tuple(matches[-limit:])


class SessionLog:
    """Redacting, size-capped writer for one ``eitaas-remmina`` run.

    ``open`` creates the private directory, prunes old logs so at most
    ``SESSION_LOG_KEEP`` remain including the new one, and creates the file
    with mode 0600. ``write`` may be called from a reader thread while
    ``close`` runs on another; both take the same lock. The writer never
    raises after ``open``: a failed write disables further output so the
    child is never blocked on our behalf.
    """

    def __init__(self, path: Path, handle: object, limit: int = SESSION_LOG_LIMIT) -> None:
        self.path = path
        self._handle = handle
        self._limit = limit
        self._size = 0
        self._lock = threading.Lock()
        self._truncated = False
        self._closed = False
        self.warnings = 0

    @classmethod
    def open(
        cls,
        directory: Path | None = None,
        *,
        limit: int = SESSION_LOG_LIMIT,
        keep: int = SESSION_LOG_KEEP,
        now: datetime | None = None,
    ) -> SessionLog:
        directory = directory or session_log_dir()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        fresh = time.time() - SESSION_LOG_ACTIVE_SECONDS
        for stale in _session_logs(directory)[: -max(keep - 1, 0) or None]:
            try:
                if stale.lstat().st_mtime < fresh:
                    stale.unlink()
            except OSError:
                pass
        stamp = (now or datetime.now()).strftime("%Y%m%dT%H%M%S.%f")
        for attempt in range(100):
            suffix = f"-{attempt}" if attempt else ""
            path = directory / f"{SESSION_LOG_PREFIX}{stamp}-{os.getpid()}{suffix}{SESSION_LOG_SUFFIX}"
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                continue
            return cls(path, os.fdopen(fd, "w", encoding="utf-8", errors="replace"), limit)
        raise FileExistsError(f"no free session log name under {directory}")

    def write(self, line: str) -> None:
        """Redact and append one line; silently stops at the size cap or on error."""
        text = redact(line.rstrip("\r\n")) + "\n"
        with self._lock:
            if all(marker in text for marker in WARNING_LINE_MARKERS):
                self.warnings += 1
            if self._closed or self._truncated:
                return
            if self._size + len(text.encode("utf-8")) > self._limit:
                self._truncated = True
                text = SESSION_LOG_TRUNCATED + "\n"
            self._emit(text)

    def _emit(self, text: str) -> None:
        try:
            self._handle.write(text)
            self._handle.flush()
            self._size += len(text.encode("utf-8"))
        except OSError:
            self._closed = True

    def close(self, exit_code: int | None) -> None:
        """Record the exit status as the last line and release the file."""
        with self._lock:
            if not self._closed:
                self._emit(f"exit={exit_code}\n")
            self._closed = True
            try:
                self._handle.close()
            except OSError:
                pass
