#!/usr/bin/env python3
"""Check every declaration of the package version against the canonical one.

`pyproject.toml` holds the canonical version and is the only place a release
bump is authored. It is a PEP 440 string restricted to the two shapes this
project releases:

    X.Y.Z              a final release
    X.Y.Z(a|b|rc)N     a pre-release

Distribution formats do not all spell a pre-release the same way, so the check
is a documented mapping rather than exact string identity (issue #95):

    canonical / PEP 440   1.0.0rc1     pyproject, src/eitaas/__init__.py,
                                       both man pages, AppStream <release>,
                                       Arch pkgver, the git tag (v-prefixed)
    RPM / Debian          1.0.0~rc1    `~` sorts BELOW the bare version in
                                       rpm and dpkg, so the eventual 1.0.0
                                       final upgrades over its candidates

`~` is invalid in both PEP 440 and an Arch `pkgver`, so those keep the
canonical spelling; pacman's `vercmp` already sorts `1.0.0rc1` below `1.0.0`
natively, which `scripts/test-arch-lifecycle.sh` asserts in the Arch CI
container. A final release maps to one identical string everywhere.

The RPM spec therefore carries the canonical version a second time, as
`%global upstream_version`, because the release tarball and its top-level
directory are named after the tag, not after the RPM `Version`.

Any other canonical shape (an epoch, `.devN`, `.postN`, a local version) is
rejected: no agreed distribution mapping exists for it.
"""

import argparse
import re
from pathlib import Path

# X.Y.Z with an optional PEP 440 pre-release segment in its normalized form.
CANONICAL_PATTERN = re.compile(r"(\d+\.\d+\.\d+)((?:a|b|rc)\d+)?")

# name -> (path relative to the project root, pattern, label for errors)
DECLARATIONS = {
    "pyproject": ("pyproject.toml", r'^version = "([^"]+)"$', "version"),
    "python package": (
        "src/eitaas/__init__.py",
        r'^__version__ = "([^"]+)"$',
        "version",
    ),
    "RPM upstream_version": (
        "packaging/rpm/eitaas-linux.spec",
        r"^%global upstream_version (\S+)$",
        "upstream_version",
    ),
    "RPM": ("packaging/rpm/eitaas-linux.spec", r"^Version:\s*(\S+)$", "Version"),
    "Debian": (
        "packaging/debian/changelog",
        r"^eitaas-linux \(([^)-]+)(?:-[^)]+)?\)",
        "upstream version",
    ),
    "Arch": ("packaging/arch/PKGBUILD", r"^pkgver=(\S+)$", "pkgver"),
    "manual page": ("docs/eitaas.1", r'"EITaaS-Linux ([^"]+)"', "version"),
    "GUI manual page": ("docs/eitaas-gui.1", r'"EITaaS-Linux ([^"]+)"', "version"),
    "AppStream metainfo": (
        "data/org.eitaas.Helper.metainfo.xml",
        r'<release version="([^"]+)"',
        "release version",
    ),
}

# Declarations that spell a pre-release the distribution-native way.
NATIVE_DECLARATIONS = ("RPM", "Debian")


def parse_canonical(canonical: str) -> tuple[str, str | None]:
    """Split a canonical version into its release and pre-release segments.

    Raises ValueError for any shape this project does not release.
    """
    found = CANONICAL_PATTERN.fullmatch(canonical)
    if not found:
        raise ValueError(
            f"unsupported canonical version {canonical!r}: releases are X.Y.Z or "
            "a X.Y.Z(a|b|rc)N pre-release; epoch, .devN, .postN, and local "
            "versions have no agreed RPM/Debian/Arch mapping"
        )
    return found.group(1), found.group(2)


def native_version(canonical: str) -> str:
    """Return the RPM/Debian spelling of a canonical version.

    A pre-release marker becomes a `~` segment so it sorts below the final
    release of the same base version; a final release is unchanged.
    """
    release, pre_release = parse_canonical(canonical)
    return f"{release}~{pre_release}" if pre_release else release


def expected_versions(canonical: str) -> dict[str, str]:
    """Return the string every declaration -- and the git tag -- must carry."""
    native = native_version(canonical)
    expected = {name: canonical for name in DECLARATIONS}
    expected.update({name: native for name in NATIVE_DECLARATIONS})
    expected["release tag"] = canonical
    return expected


def match(path: Path, pattern: str, label: str) -> str:
    text = path.read_text(encoding="utf-8")
    found = re.search(pattern, text, re.MULTILINE)
    if not found:
        raise SystemExit(f"could not read {label} from {path}")
    return found.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", help="release tag to compare, for example v1.0.0rc1")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.project_root.resolve()

    versions = {
        name: match(root / path, pattern, label)
        for name, (path, pattern, label) in DECLARATIONS.items()
    }
    canonical = versions["pyproject"]
    try:
        expected = expected_versions(canonical)
    except ValueError as error:
        raise SystemExit(f"pyproject.toml: {error}") from error

    if args.tag:
        tag = args.tag.removeprefix("refs/tags/")
        if not tag.startswith("v"):
            raise SystemExit(f"release tag must be v-prefixed, got {tag!r}")
        versions["release tag"] = tag.removeprefix("v")

    mismatches = [
        (name, value, expected[name])
        for name, value in versions.items()
        if value != expected[name]
    ]
    if mismatches:
        details = ", ".join(
            f"{name}={value} (expected {want})" for name, value, want in mismatches
        )
        raise SystemExit(f"version mismatch; canonical {canonical}: {details}")

    native = expected["RPM"]
    spelling = "" if native == canonical else f" (RPM/Debian {native})"
    print(
        f"all version declarations match canonical {canonical}{spelling}: "
        f"{', '.join(versions)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
