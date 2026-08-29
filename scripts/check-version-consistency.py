#!/usr/bin/env python3
import argparse
import re
from pathlib import Path


def match(path: Path, pattern: str, label: str) -> str:
    text = path.read_text(encoding="utf-8")
    found = re.search(pattern, text, re.MULTILINE)
    if not found:
        raise SystemExit(f"could not read {label} from {path}")
    return found.group(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="release tag to compare, for example v0.1.0")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.project_root.resolve()

    versions = {
        "pyproject": match(root / "pyproject.toml", r'^version = "([^"]+)"$', "version"),
        "python package": match(
            root / "src/eitaas/__init__.py", r'^__version__ = "([^"]+)"$', "version"
        ),
        "RPM": match(root / "packaging/rpm/eitaas-linux.spec", r'^Version:\s*(\S+)$', "Version"),
        "Debian": match(
            root / "packaging/debian/changelog",
            r'^eitaas-linux \(([^)-]+)(?:-[^)]+)?\)',
            "upstream version",
        ),
        "Arch": match(root / "packaging/arch/PKGBUILD", r'^pkgver=(\S+)$', "pkgver"),
        "manual page": match(root / "docs/eitaas.1", r'"EITaaS-Linux ([^"]+)"', "version"),
    }
    expected = versions["pyproject"]
    mismatches = {name: value for name, value in versions.items() if value != expected}

    if args.tag:
        tag_version = args.tag.removeprefix("refs/tags/").removeprefix("v")
        versions["release tag"] = tag_version
        if tag_version != expected:
            mismatches["release tag"] = tag_version

    if mismatches:
        details = ", ".join(f"{name}={value}" for name, value in mismatches.items())
        raise SystemExit(f"version mismatch; expected {expected}: {details}")

    print(f"all version declarations match {expected}: {', '.join(versions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
