"""Conservative redaction for diagnostic output."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Longer alternatives first so "access_token" is not cut to "token".
_SENSITIVE = (
    r"access[_-]?token|refresh[_-]?token|id[_-]?token|token|code|session|"
    r"loadbalanceinfo|password|passwd|authorization|login[_-]?hint|username|"
    r"upn|email|user|serial|object|state|sid|secret|blob|guid"
)
SENSITIVE_KEYS = re.compile(rf"(?i)({_SENSITIVE})")
# A sensitive word may be the tail of a compound key. Separated forms
# ("proxy_password", "login-hint") and camelCase/PascalCase compounds are both
# accepted, so FreeRDP's ARM fields ("redirectedAuthBlob", "RedirectionGuid")
# match too. The camel boundary is asserted case-sensitively with (?-i:...)
# because the rules below are case-insensitive as a whole.
_KEY_PREFIX = r"(?:[\w-]*(?:[_-]|(?-i:(?<=[a-z0-9])(?=[A-Z]))))?"
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?\b")
# Remmina prints "proxy_password: x"; the key may carry a word prefix.
# An already redacted value is left alone so redact() is idempotent.
KEY_VALUE = re.compile(rf"(?i)\b({_KEY_PREFIX}(?:{_SENSITIVE}))\s*[:=]\s*(?!<redacted>)([^\s;&]+)")
# JSON bodies quote both sides, so KEY_VALUE never sees the ":" next to the
# key. FreeRDP's OAuth token-endpoint response is exactly this shape
# ({"token_type":"Bearer","access_token":"..."}), and its refresh token is
# opaque, not a JWT. "cookie" is only sensitive in this quoted form; the bare
# "Set-Cookie:" header is handled by COOKIE_HEADER below.
QUOTED_KEY_VALUE = re.compile(
    rf'(?i)"({_KEY_PREFIX}(?:{_SENSITIVE}|cookie))"(\s*:\s*)"(?:<redacted>|[^"]*)"'
)
# Set-Cookie/Cookie header values; the cookie name is kept, its value is not.
COOKIE_HEADER = re.compile(
    r"(?i)((?:set-)?cookie\s*:\s*)([^=\s;,]{1,64}=)?(?:<redacted>|[^\r\n]*)"
)
# FreeRDP's AVD web-socket transport logs the Azure load-balancing cookie at
# INFO level: "Got ARRAffinity cookie <value>" (libfreerdp/core/gateway/wst.c,
# see issue #88); it also travels as a plain "ARRAffinity=<value>" pair.
AFFINITY_COOKIE = re.compile(
    r"(?i)\b(ARRAffinity(?:SameSite)?)(\s+cookie\s+|\s*=\s*)([^\s;,]+)"
)
# A PKCS #11 URI carries the token serial, label, and object label.
PKCS11_URI = re.compile(r"pkcs11:[^\s'\"]+")
# HTTP Authorization values ("Bearer <token>"), in any casing; FreeRDP logs
# the header only at TRACE level, which the launcher never enables, but
# redact them anyway.
BEARER = re.compile(r"(?i)\bBearer\s+(?!<redacted>)[A-Za-z0-9._~+/-]+=*")


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
    value = BEARER.sub("Bearer <redacted>", value)
    value = PKCS11_URI.sub("<redacted-pkcs11-uri>", value)
    value = QUOTED_KEY_VALUE.sub(lambda match: f'"{match.group(1)}"{match.group(2)}"<redacted>"', value)
    value = COOKIE_HEADER.sub(lambda match: f"{match.group(1)}{match.group(2) or ''}<redacted>", value)
    value = AFFINITY_COOKIE.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", value)
    value = KEY_VALUE.sub(lambda match: f"{match.group(1)}=<redacted>", value)
    return re.sub(r"https?://[^\s]+", lambda match: redact_url(match.group(0)), value)

