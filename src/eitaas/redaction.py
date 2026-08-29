"""Conservative redaction for diagnostic output."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE_KEYS = re.compile(
    r"(?i)(access[_-]?token|refresh[_-]?token|id[_-]?token|code|session|"
    r"loadbalanceinfo|password|passwd|authorization|loginhint|username)"
)
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?\b")
KEY_VALUE = re.compile(
    r"(?i)\b(access[_-]?token|refresh[_-]?token|id[_-]?token|code|session|"
    r"loadbalanceinfo|password|passwd|authorization|loginhint|username)"
    r"\s*[:=]\s*([^\s;&]+)"
)


def redact_url(value: str) -> str:
    """Preserve a URL destination while removing sensitive query values."""
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<redacted-url>"
    if not parts.scheme or not parts.netloc:
        return value
    query = urlencode(
        [(key, "<redacted>" if SENSITIVE_KEYS.search(key) else val) for key, val in parse_qsl(parts.query, keep_blank_values=True)]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def redact(value: str) -> str:
    """Remove common secrets from arbitrary command output."""
    value = JWT.sub("<redacted-token>", value)
    value = KEY_VALUE.sub(lambda match: f"{match.group(1)}=<redacted>", value)
    return re.sub(r"https?://[^\s]+", lambda match: redact_url(match.group(0)), value)

