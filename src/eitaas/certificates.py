"""Auditable certificate bundle download and inspection."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

OFFICIAL_HOSTS = {"public.cyber.mil", "cyber.mil"}
MAX_BUNDLE_SIZE = 10 * 1024 * 1024


class CertificateError(ValueError):
    """Certificate operation could not be completed safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(url: str, expected_sha256: str, destination: str | None = None) -> dict[str, str]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
        raise CertificateError("certificate bundles must use an official cyber.mil HTTPS host")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise CertificateError("a 64-character expected SHA-256 digest is required")
    target = Path(destination).expanduser() if destination else Path(
        os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
    ) / "eitaas" / "certificates" / Path(parsed.path).name
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "EITaaS-Linux/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        content_length = int(response.headers.get("Content-Length", "0"))
        if content_length > MAX_BUNDLE_SIZE:
            raise CertificateError("certificate bundle exceeds the 10 MiB safety limit")
        data = response.read(MAX_BUNDLE_SIZE + 1)
    if len(data) > MAX_BUNDLE_SIZE:
        raise CertificateError("certificate bundle exceeds the 10 MiB safety limit")
    actual = hashlib.sha256(data).hexdigest()
    if actual.lower() != expected_sha256.lower():
        raise CertificateError(f"SHA-256 mismatch; received {actual}")
    descriptor, temporary = tempfile.mkstemp(prefix=".bundle-", dir=target.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return {"path": str(target), "sha256": actual, "source": url}


def inspect(path_value: str) -> dict[str, object]:
    path = Path(path_value).expanduser()
    if not path.is_file() or path.is_symlink():
        raise CertificateError("bundle must be a regular file")
    if path.stat().st_size > MAX_BUNDLE_SIZE:
        raise CertificateError("certificate bundle exceeds the 10 MiB safety limit")
    command = ["openssl", "pkcs7", "-in", str(path), "-inform", "DER", "-print_certs"]
    result = subprocess.run(command, capture_output=True, timeout=15, check=False)
    if result.returncode:
        command[5] = "PEM"
        result = subprocess.run(command, capture_output=True, timeout=15, check=False)
    if result.returncode:
        raise CertificateError("OpenSSL could not parse the PKCS#7 bundle")
    blocks = re.findall(
        rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", result.stdout, re.S
    )
    certificates: list[dict[str, object]] = []
    for block in blocks:
        details = subprocess.run(
            ["openssl", "x509", "-noout", "-subject", "-issuer", "-fingerprint", "-sha256"],
            input=block,
            capture_output=True,
            timeout=5,
            check=True,
        ).stdout.decode(errors="replace").splitlines()
        values = dict(line.split("=", 1) for line in details if "=" in line)
        subject = values.get("subject", "").strip()
        issuer = values.get("issuer", "").strip()
        certificates.append(
            {
                "subject": subject,
                "issuer": issuer,
                "sha256_fingerprint": values.get("sha256 Fingerprint", "").strip(),
                "self_signed_candidate": bool(subject and subject == issuer),
            }
        )
    return {"path": str(path), "sha256": sha256_file(path), "certificates": certificates}

