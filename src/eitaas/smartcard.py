"""Non-interactive smart-card diagnostics."""

from __future__ import annotations

import shutil
import subprocess


def _run(command: list[str]) -> dict[str, object]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        return {
            "available": True,
            "ok": result.returncode == 0,
            "summary": "command completed" if result.returncode == 0 else f"command failed (exit {result.returncode})",
        }
    except subprocess.TimeoutExpired:
        return {"available": True, "ok": False, "summary": "command timed out"}
    except OSError as error:
        return {"available": False, "ok": False, "summary": str(error)}


def status() -> dict[str, object]:
    result: dict[str, object] = {}
    if shutil.which("systemctl"):
        result["pcscd"] = _run(["systemctl", "is-active", "pcscd.socket"])
    else:
        result["pcscd"] = {"available": False, "ok": False, "summary": "systemctl not found"}
    if shutil.which("pcsc_scan"):
        result["reader"] = _run(["pcsc_scan", "-n"])
    else:
        result["reader"] = {"available": False, "ok": False, "summary": "pcsc_scan not found"}
    if shutil.which("pkcs11-tool"):
        result["middleware"] = _run(["pkcs11-tool", "--list-slots"])
    else:
        result["middleware"] = {"available": False, "ok": False, "summary": "pkcs11-tool not found"}
    return result
