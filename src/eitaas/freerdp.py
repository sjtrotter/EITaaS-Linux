"""FreeRDP discovery and capability checks."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Client:
    path: str
    backend: str
    version: str
    aad: bool
    pcsc: bool

    def public(self) -> dict[str, object]:
        return asdict(self)


CANDIDATES = {
    "x11": ("xfreerdp3", "xfreerdp"),
    "sdl": ("sdl3-freerdp", "sdl-freerdp3", "sfreerdp3"),
    "wayland": ("wlfreerdp3", "wlfreerdp"),
}


def _output(path: str, option: str) -> str:
    try:
        result = subprocess.run(
            [path, option], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return f"{result.stdout}\n{result.stderr}"


def inspect_client(path: str, backend: str) -> Client:
    version_output = _output(path, "/version")
    build_output = _output(path, "/buildconfig")
    match = re.search(r"(?:FreeRDP version|This is FreeRDP version)\s+([^\s]+)", version_output, re.I)
    version = match.group(1) if match else "unknown"
    return Client(
        path=path,
        backend=backend,
        version=version,
        aad=bool(re.search(r"WITH_AAD=(?:ON|1)", build_output, re.I)),
        pcsc=bool(re.search(r"WITH_(?:PCSC|SMARTCARD_PCSC)=(?:ON|1)", build_output, re.I)),
    )


def discover(backend: str = "auto") -> list[Client]:
    order = ["x11", "sdl", "wayland"] if backend == "auto" else [backend]
    found: list[Client] = []
    for kind in order:
        for name in CANDIDATES[kind]:
            path = shutil.which(name)
            if path:
                found.append(inspect_client(path, kind))
                break
    return found


def select(backend: str = "auto") -> Client:
    clients = discover(backend)
    for client in clients:
        major_match = re.match(r"(\d+)", client.version)
        if major_match and int(major_match.group(1)) >= 3 and client.aad and client.pcsc:
            return client
    session = os.environ.get("XDG_SESSION_TYPE", "unknown")
    raise RuntimeError(
        f"no compatible FreeRDP 3 client with AAD and PC/SC support found "
        f"(requested backend: {backend}; session: {session})"
    )
