"""Safe handling of RDP and RDPW connection profiles."""

from __future__ import annotations

import os
import re
import stat
import urllib.parse
from pathlib import Path

MAX_PROFILE_SIZE = 1024 * 1024
SENSITIVE_FIELDS = re.compile(
    r"(?i)(loadbalanceinfo|username|domain|workspace|tenant|resource|gateway|"
    r"full address|remoteapplication|signscope|signature|token)"
)


class ProfileError(ValueError):
    """A connection profile failed a safety check."""


CLOUD_FIELDS = {
    "alternate full address",
    "diagnosticserviceurl",
    "full address",
    "gatewayhostname",
    "hubdiscoverygeourl",
    "wvd endpoint pool",
}
GOVERNMENT_SUFFIXES = (".azure.us", ".microsoftonline.us", ".usgovcloudapi.net")
COMMERCIAL_SUFFIXES = (".microsoft.com", ".microsoftonline.com", ".windows.net")


def _profile_text(path: Path) -> str:
    raw = path.read_bytes()
    if b"\x00" in raw:
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8-sig", errors="replace")


def _hostname(value: str) -> str | None:
    candidate = value.strip()
    parsed = urllib.parse.urlsplit(candidate if "://" in candidate else f"//{candidate}")
    return parsed.hostname.lower().rstrip(".") if parsed.hostname else None


def _matches_suffix(host: str, suffixes: tuple[str, ...]) -> bool:
    return any(host == suffix[1:] or host.endswith(suffix) for suffix in suffixes)


def detect_cloud(path_value: str | os.PathLike[str]) -> str:
    """Classify only allowlisted endpoint suffixes without exposing profile values."""
    path = validate_profile(path_value)
    clouds: set[str] = set()
    for line in _profile_text(path).splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3 or parts[0].strip().lower() not in CLOUD_FIELDS:
            continue
        host = _hostname(parts[2])
        if not host:
            continue
        if _matches_suffix(host, GOVERNMENT_SUFFIXES):
            clouds.add("azure_government")
        elif _matches_suffix(host, COMMERCIAL_SUFFIXES):
            clouds.add("azure_commercial")
    if not clouds:
        raise ProfileError("profile does not contain a recognized Azure endpoint set")
    if len(clouds) != 1:
        raise ProfileError("profile contains mixed Azure cloud endpoint sets")
    return clouds.pop()


def validate_profile(path_value: str | os.PathLike[str]) -> Path:
    path = Path(path_value).expanduser()
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ProfileError("profile must be a regular file, not a link or device")
    if info.st_uid != os.getuid():
        raise ProfileError("profile must be owned by the current user")
    if info.st_mode & 0o077:
        raise ProfileError("profile permissions are too broad; run: chmod 600 FILE")
    if info.st_size > MAX_PROFILE_SIZE:
        raise ProfileError("profile exceeds the 1 MiB safety limit")
    if path.suffix.lower() not in {".rdp", ".rdpw"}:
        raise ProfileError("profile extension must be .rdp or .rdpw")
    return path


def inspect_profile(path_value: str | os.PathLike[str]) -> dict[str, object]:
    path = validate_profile(path_value)
    raw = path.read_bytes()
    text = _profile_text(path)
    fields: list[dict[str, str]] = []
    for line in text.splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        name, field_type, value = parts
        show_value = field_type.lower() == "i" and not SENSITIVE_FIELDS.search(name)
        fields.append(
            {
                "name": name,
                "type": field_type,
                "value": value if show_value else "<redacted>",
            }
        )
    return {
        "path": str(path),
        "size": len(raw),
        "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}",
        "cloud": detect_cloud(path),
        "fields": fields,
    }
