#!/usr/bin/env python3
"""Prepare a complete native Debian source tree from the shared manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with tarfile.open(archive, "r:gz") as source:
        for member in source.getmembers():
            target = (destination / member.name).resolve()
            if destination not in target.parents and target != destination:
                raise ValueError(f"archive path escapes destination: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"archive links are not accepted: {member.name}")
        source.extractall(destination, filter="data")


def fetch(name: str, metadata: dict[str, str], cache: Path) -> Path:
    archive = cache / f"{name}-{metadata['version']}.tar.gz"
    if not archive.exists():
        temporary = archive.with_suffix(".download")
        urllib.request.urlretrieve(metadata["url"], temporary)
        temporary.replace(archive)
    actual = digest(archive)
    if actual != metadata["sha256"]:
        raise ValueError(f"SHA-256 mismatch for {name}: {actual}")
    return archive


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.project_root.resolve()
    package_dir = root / "packaging" / "remmina"
    manifest = json.loads((package_dir / "sources.json").read_text())
    args.cache.mkdir(parents=True, exist_ok=True)

    if args.output.exists():
        raise ValueError(f"output already exists: {args.output}")
    args.output.mkdir(parents=True)

    for name, metadata in manifest["sources"].items():
        safe_extract(fetch(name, metadata, args.cache), args.output)

    remmina_dir = args.output / f"Remmina-{manifest['sources']['remmina']['commit']}"
    for filename in manifest["downstream_sources"][:2]:
        shutil.copy2(package_dir / filename, remmina_dir / "plugins" / "rdp" / filename)

    patches = args.output / "patches"
    patches.mkdir()
    for filename in manifest["patches"]:
        patch = package_dir / filename
        shutil.copy2(patch, patches / filename)
        with patch.open("rb") as source:
            subprocess.run(
                ["patch", "--fuzz=0", "-p1", "-d", str(remmina_dir)],
                stdin=source,
                check=True,
            )

    for filename in (
        "eitaas-remmina",
        "sources.json",
        "THIRD_PARTY_NOTICES.md",
        "EITaaS-LICENSE",
    ):
        shutil.copy2(package_dir / filename, args.output / filename)
    shutil.copytree(package_dir / "debian", args.output / "debian")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
