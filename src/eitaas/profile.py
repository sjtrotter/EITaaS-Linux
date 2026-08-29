"""Safe handling of RDP and RDPW connection profiles."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

MAX_PROFILE_SIZE = 1024 * 1024
SENSITIVE_FIELDS = re.compile(
    r"(?i)(loadbalanceinfo|username|domain|workspace|tenant|resource|gateway|"
    r"full address|remoteapplication|signscope|signature|token)"
)


class ProfileError(ValueError):
    """A connection profile failed a safety check."""


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
    if b"\x00" in raw:
        text = raw.decode("utf-16", errors="replace")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
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
        "fields": fields,
    }
