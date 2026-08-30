"""Read-only system diagnostics."""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

from . import remmina


def report() -> dict[str, object]:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    pcsc_socket = Path(runtime, "pcscd", "pcscd.comm") if runtime else None
    system_socket = Path("/run/pcscd/pcscd.comm")
    return {
        "platform": platform.platform(),
        "session_type": os.environ.get("XDG_SESSION_TYPE", "unknown"),
        "display": bool(os.environ.get("DISPLAY")),
        "wayland_display": bool(os.environ.get("WAYLAND_DISPLAY")),
        "remmina": remmina.status(),
        "identity_broker": remmina.identity_broker_available(),
        "tools": {
            name: bool(shutil.which(name))
            for name in ("pcsc_scan", "pkcs11-tool", "systemctl", "openssl", "certutil")
        },
        "pcsc_socket": bool(system_socket.exists() or (pcsc_socket and pcsc_socket.exists())),
    }


def healthy(data: dict[str, object]) -> bool:
    """The bundled client is usable when its launcher and private binary exist."""
    bundle = data.get("remmina")
    if not isinstance(bundle, dict):
        return False
    return bool(bundle.get("launcher") and bundle.get("client"))
