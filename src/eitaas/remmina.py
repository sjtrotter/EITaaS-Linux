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
from pathlib import Path

from .profile import ProfileError, validate_profile

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
