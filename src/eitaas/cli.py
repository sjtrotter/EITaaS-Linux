"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .api import Application, ConnectionRequest, Result, to_public_dict


def _print(data: object, as_json: bool) -> None:
    data = to_public_dict(data)
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return
    items = data if isinstance(data, list) else [data]
    for index, item in enumerate(items):
        if index:
            print()
        if isinstance(item, dict):
            for key, value in item.items():
                print(f"{key}: {value}")
        else:
            print(item)


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
    connect_cmd = commands.add_parser(
        "connect", help="validate a protected RDPW profile and start eitaas-remmina"
    )
    connect_cmd.add_argument(
        "profile", nargs="?", help="explicit .rdpw path; default: the imported default profile"
    )
    profile_cmd = commands.add_parser("profile", help="manage imported profiles")
    profile_commands = profile_cmd.add_subparsers(dest="profile_command", required=True)
    profile_import = profile_commands.add_parser(
        "import", help="move a downloaded .rdpw into the private store and make it default"
    )
    profile_import.add_argument("path")
    profile_import.add_argument("--json", action="store_true")
    profile_list = profile_commands.add_parser("list", help="list imported profiles")
    profile_list.add_argument("--json", action="store_true")
    profile_select = profile_commands.add_parser("select", help="make an imported profile the default")
    profile_select.add_argument("name")
    profile_select.add_argument("--json", action="store_true")
    profile_remove = profile_commands.add_parser("remove", help="delete an imported profile")
    profile_remove.add_argument("name")
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


def _profile_command(app: Application, args: argparse.Namespace) -> Result[object]:
    if args.profile_command == "import":
        return app.import_profile(args.path)
    if args.profile_command == "list":
        return app.list_profiles()
    if args.profile_command == "select":
        return app.select_profile(args.name)
    return app.remove_profile(args.name)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    app = Application()
    result: Result[object]
    if args.command == "doctor":
        result = app.doctor()
        if result.ok:
            _print(result.value, args.json)
            return 0 if result.value and result.value.ready else 1
    elif args.command == "inspect-profile":
        result = app.inspect_profile(args.profile)
        if result.ok:
            _print(result.value, args.json)
            return 0
    elif args.command == "smartcard":
        result = app.smartcard_status()
        if result.ok:
            _print(result.value, args.json)
            return 0 if result.value and result.value.ready else 1
    elif args.command == "connect":
        result = app.launch(ConnectionRequest(args.profile))
        if result.ok:
            return result.value.exit_code if result.value else 2
    elif args.command == "profile":
        result = _profile_command(app, args)
        if result.ok:
            if result.value is not None and result.value is not True:
                _print(result.value, args.json)
            return 0
    elif args.command == "certificates":
        result = (
            app.fetch_certificates(args.url, args.sha256, args.output)
            if args.certificate_command == "fetch"
            else app.inspect_certificates(args.bundle)
        )
        if result.ok:
            _print(result.value, args.json)
            return 0
    else:
        return 2
    if result.error:
        print(f"error [{result.error.code}]: {result.error.message}", file=sys.stderr)
        if result.error.recovery:
            print(f"recovery: {result.error.recovery}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
