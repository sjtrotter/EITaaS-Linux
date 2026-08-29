#!/usr/bin/env python3
import argparse
import subprocess
import tarfile
from pathlib import Path, PurePosixPath


FORBIDDEN_SUFFIXES = {
    ".cer", ".crt", ".der", ".har", ".key", ".p12", ".p7b", ".p7c",
    ".pcap", ".pcapng", ".pem", ".pfx", ".rdp", ".rdpw",
}
REQUIRED_PATHS = {
    "LICENSE",
    "NOTICE",
    "README.md",
    "pyproject.toml",
    "packaging/arch/PKGBUILD",
    "packaging/debian/control",
    "packaging/rpm/eitaas-linux.spec",
    "src/eitaas/__init__.py",
}
ALLOWED_SYNTHETIC_SENSITIVE_PATHS = {"tests/fixtures/synthetic.rdpw"}


def git_files(project_root: Path, source_ref: str) -> set[str]:
    result = subprocess.run(
        [
            "git", "-c", f"safe.directory={project_root}", "-C",
            str(project_root), "ls-tree", "-r", "--name-only", source_ref,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return set(result.stdout.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--ref", default="HEAD")
    args = parser.parse_args()
    project_root = args.project_root.resolve()

    with tarfile.open(args.archive, "r:gz") as source:
        members = source.getmembers()

    if not members:
        raise SystemExit("source archive is empty")

    roots: set[str] = set()
    archived_files: set[str] = set()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise SystemExit(f"unsafe archive path: {member.name}")
        roots.add(path.parts[0])
        if member.issym() or member.islnk():
            raise SystemExit(f"links are not allowed in source archive: {member.name}")
        if not (member.isfile() or member.isdir()):
            raise SystemExit(f"unsupported archive member: {member.name}")
        if member.isfile():
            relative = PurePosixPath(*path.parts[1:])
            relative_text = str(relative)
            archived_files.add(relative_text)
            if (
                relative.suffix.lower() in FORBIDDEN_SUFFIXES
                and relative_text not in ALLOWED_SYNTHETIC_SENSITIVE_PATHS
            ):
                raise SystemExit(f"sensitive file type in source archive: {relative}")
            if any(part in {".agents", ".codex", ".git"} for part in relative.parts):
                raise SystemExit(f"local state in source archive: {relative}")

    if len(roots) != 1:
        raise SystemExit("source archive must have exactly one top-level directory")
    root = next(iter(roots))
    if not root.startswith("eitaas-linux-"):
        raise SystemExit(f"unexpected top-level directory: {root}")

    missing = REQUIRED_PATHS - archived_files
    if missing:
        raise SystemExit(f"required source files missing: {sorted(missing)}")

    tracked_files = git_files(project_root, args.ref)
    if archived_files != tracked_files:
        missing_tracked = sorted(tracked_files - archived_files)
        unexpected = sorted(archived_files - tracked_files)
        raise SystemExit(
            f"archive differs from Git tree; missing={missing_tracked}, "
            f"unexpected={unexpected}"
        )

    print(f"verified {args.archive}: {len(archived_files)} tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
