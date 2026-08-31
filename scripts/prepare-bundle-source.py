#!/usr/bin/env python3
"""Assemble the corresponding source for the combined ``eitaas-linux`` package.

``packaging/remmina/sources.json`` is the single source of truth for the pinned
upstream archives, their digests, the ordered patch series, and the downstream
inputs. Two subcommands share that manifest:

``fetch``
    Download and verify the pinned upstream archives into a cache directory and
    optionally copy them, under the file names the RPM spec declares, into an
    ``rpmbuild`` ``SOURCES`` directory.

``tree``
    Build the complete source tree the DEB and Arch recipes compile: the
    repository sources (Python packages, packaging metadata, patches, docs),
    both extracted upstream trees with the smart-card integration copied in and
    the ordered patch series applied, and, for Debian, the ``debian/`` directory.
"""

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


def read_manifest(project_root: Path) -> dict:
    package_dir = project_root / "packaging" / "remmina"
    return json.loads((package_dir / "sources.json").read_text())


def fetch(name: str, metadata: dict[str, str], cache: Path) -> Path:
    """Return the verified cached archive for one pinned upstream source."""
    archive = cache / f"{name}-{metadata['version']}.tar.gz"
    if not archive.exists():
        temporary = archive.with_suffix(".download")
        urllib.request.urlretrieve(metadata["url"], temporary)
        temporary.replace(archive)
    actual = digest(archive)
    if actual != metadata["sha256"]:
        raise ValueError(f"SHA-256 mismatch for {name}: {actual}")
    return archive


def fetch_all(project_root: Path, cache: Path) -> dict[str, Path]:
    manifest = read_manifest(project_root)
    cache.mkdir(parents=True, exist_ok=True)
    return {
        name: fetch(name, metadata, cache)
        for name, metadata in manifest["sources"].items()
    }


def upstream_basename(metadata: dict[str, str]) -> str:
    """The archive file name the RPM spec's SourceN URL declares."""
    return metadata["url"].rsplit("/", 1)[-1]


def command_fetch(args: argparse.Namespace) -> int:
    root = args.project_root.resolve()
    manifest = read_manifest(root)
    archives = fetch_all(root, args.cache)
    for name, archive in archives.items():
        if args.destination is not None:
            args.destination.mkdir(parents=True, exist_ok=True)
            target = args.destination / upstream_basename(manifest["sources"][name])
            shutil.copy2(archive, target)
            archive = target
        print(archive)
    return 0


def repository_sources(project_root: Path, output: Path, source_archive: Path | None) -> None:
    """Populate ``output`` with the repository tree, tarball or Git working copy."""
    if source_archive is None:
        subprocess.run(
            [
                "git", "-c", f"safe.directory={project_root}",
                "-C", str(project_root), "archive", "--format=tar", "HEAD",
            ],
            check=True,
            stdout=(output / ".repository.tar").open("wb"),
        )
        with tarfile.open(output / ".repository.tar") as source:
            source.extractall(output, filter="data")
        (output / ".repository.tar").unlink()
        return

    staging = output / ".repository"
    staging.mkdir()
    safe_extract(source_archive, staging)
    roots = list(staging.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise ValueError(f"source archive must hold one top-level directory: {source_archive}")
    for entry in roots[0].iterdir():
        shutil.move(str(entry), output / entry.name)
    shutil.rmtree(staging)


def command_tree(args: argparse.Namespace) -> int:
    root = args.project_root.resolve()
    package_dir = root / "packaging" / "remmina"
    manifest = read_manifest(root)

    if args.output.exists():
        raise ValueError(f"output already exists: {args.output}")
    args.output.mkdir(parents=True)

    repository_sources(root, args.output, args.source_archive)
    for archive in fetch_all(root, args.cache).values():
        safe_extract(archive, args.output)

    remmina_dir = args.output / f"Remmina-{manifest['sources']['remmina']['commit']}"
    # Statistics are disabled in this minimal client. Exclude their bundled,
    # generated web assets from the corresponding source package as well.
    shutil.rmtree(remmina_dir / "data" / "reports")
    for filename in manifest["downstream_sources"][:2]:
        shutil.copy2(package_dir / filename, remmina_dir / "plugins" / "rdp" / filename)

    for filename in manifest["patches"]:
        with (package_dir / filename).open("rb") as source:
            subprocess.run(
                ["patch", "--fuzz=0", "-p1", "-d", str(remmina_dir)],
                stdin=source,
                check=True,
            )

    if args.debian:
        shutil.copytree(root / "packaging" / "debian", args.output / "debian")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    fetcher = subcommands.add_parser("fetch", help="download and verify the pinned archives")
    fetcher.add_argument("--cache", type=Path, required=True)
    fetcher.add_argument(
        "--destination",
        type=Path,
        help="copy the verified archives here under their declared file names",
    )
    fetcher.set_defaults(handler=command_fetch)

    tree = subcommands.add_parser("tree", help="assemble the combined source tree")
    tree.add_argument("--cache", type=Path, required=True)
    tree.add_argument("--output", type=Path, required=True)
    tree.add_argument(
        "--source-archive",
        type=Path,
        help="canonical repository tarball to use instead of `git archive HEAD`",
    )
    tree.add_argument(
        "--debian", action="store_true", help="also copy packaging/debian to debian/"
    )
    tree.set_defaults(handler=command_tree)

    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
