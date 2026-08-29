"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from . import __version__
from .certificates import CertificateError, fetch as fetch_certificates, inspect as inspect_certificates
from .doctor import healthy, report
from .freerdp import select
from .profile import ProfileError, inspect_profile, validate_profile
from .redaction import redact
from .smartcard import status


def _print(data: object, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return
    if isinstance(data, dict):
        for key, value in data.items():
            print(f"{key}: {value}")
    else:
        print(data)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="eitaas")
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = root.add_subparsers(dest="command", required=True)
    doctor_cmd = commands.add_parser("doctor", help="run read-only system checks")
    doctor_cmd.add_argument("--json", action="store_true")
    inspect_cmd = commands.add_parser("inspect-profile", help="safely summarize an RDPW profile")
    inspect_cmd.add_argument("profile")
    inspect_cmd.add_argument("--json", action="store_true")
    smartcard_cmd = commands.add_parser("smartcard", help="smart-card diagnostics")
    smartcard_commands = smartcard_cmd.add_subparsers(dest="smartcard_command", required=True)
    status_cmd = smartcard_commands.add_parser("status")
    status_cmd.add_argument("--json", action="store_true")
    connect_cmd = commands.add_parser("connect", help="connect using a protected RDPW profile")
    connect_cmd.add_argument("profile")
    connect_cmd.add_argument("--backend", choices=("auto", "x11", "sdl", "wayland"), default="auto")
    connect_cmd.add_argument("--clipboard", action="store_true", help="enable bidirectional clipboard redirection")
    cert_cmd = commands.add_parser("certificates", help="fetch or inspect official certificate bundles")
    cert_commands = cert_cmd.add_subparsers(dest="certificate_command", required=True)
    cert_fetch = cert_commands.add_parser("fetch", help="download a digest-pinned official bundle")
    cert_fetch.add_argument("url")
    cert_fetch.add_argument("--sha256", required=True)
    cert_fetch.add_argument("--output")
    cert_fetch.add_argument("--json", action="store_true")
    cert_inspect = cert_commands.add_parser("inspect", help="inspect a PKCS#7 bundle without trusting it")
    cert_inspect.add_argument("bundle")
    cert_inspect.add_argument("--json", action="store_true")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "doctor":
            data = report()
            _print(data, args.json)
            return 0 if healthy(data) else 1
        if args.command == "inspect-profile":
            _print(inspect_profile(args.profile), args.json)
            return 0
        if args.command == "smartcard":
            data = status()
            _print(data, args.json)
            return 0 if all(bool(item.get("ok")) for item in data.values()) else 1
        if args.command == "connect":
            profile = validate_profile(args.profile)
            client = select(args.backend)
            command = [
                client.path,
                str(profile),
                "/gateway:type:arm",
                "/sec:aad",
                "/azure:ad:login.microsoftonline.us,tenantid:common,avd-access:https://login.microsoftonline.com/common/oauth2/nativeclient",
                "/smartcard",
                "+clipboard" if args.clipboard else "-clipboard",
            ]
            return subprocess.run(command, check=False).returncode
        if args.command == "certificates":
            if args.certificate_command == "fetch":
                _print(fetch_certificates(args.url, args.sha256, args.output), args.json)
            else:
                _print(inspect_certificates(args.bundle), args.json)
            return 0
    except (OSError, ProfileError, CertificateError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"error: {redact(str(error))}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
