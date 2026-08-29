#!/bin/sh
set -eu

bad_paths=$(git ls-files | grep -E '(^|/)(\.agents|\.agent|\.codex|\.claude|\.cursor|\.windsurf)(/|$)|\.(rdp|rdpw|har|pcap|pcapng|key|pem|p12|pfx|cer|crt|der|p7b|p7c)$' || true)
bad_paths=$(printf '%s\n' "$bad_paths" | grep -v '^tests/fixtures/synthetic\.rdpw$' || true)
if [ -n "$bad_paths" ]; then
    printf 'Prohibited sensitive or local artifacts are tracked:\n%s\n' "$bad_paths" >&2
    exit 1
fi

if git grep -n -E '(/cert:ignore|Identity=unix-user:\*|ResultInactive=yes)' -- ':!scripts/check-repository-artifacts.sh'; then
    printf 'Unsafe connection or smart-card policy guidance detected.\n' >&2
    exit 1
fi

scripts/check-version-consistency.py
