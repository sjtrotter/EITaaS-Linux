"""Per-user store of imported protected ``.rdpw`` profiles.

An exported profile usually lands in a world-readable download directory.
``import_profile`` moves it (not copies) into a private per-user directory,
restricts it to mode ``0600``, and records it as the default profile used by
``eitaas connect`` and the graphical helper when no explicit path is given.

Only file names and modes live here; profile contents are never parsed or
stored anywhere else, and the configuration file holds only the default
basename. This is an import list, not a connection manager (ADR-0002).
"""

from __future__ import annotations

import configparser
import errno
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .profile import MAX_PROFILE_SIZE, ProfileError, validate_profile

PROFILE_SUFFIX = ".rdpw"
STORE_SUBDIR = Path("eitaas-remmina", "profiles")
CONFIG_SUBDIR = "eitaas"
CONFIG_FILE = "profiles.ini"
_SECTION = "profiles"
_DEFAULT_KEY = "default"
_COPY_CHUNK = 64 * 1024


@dataclass(frozen=True)
class StoredProfile:
    """A profile inside the private store, identified by basename."""

    name: str
    path: Path
    imported: float
    default: bool = False


def store_dir() -> Path:
    """``$XDG_DATA_HOME/eitaas-remmina/profiles`` (GLib's user data dir)."""
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / STORE_SUBDIR


def config_path() -> Path:
    """``$XDG_CONFIG_HOME/eitaas/profiles.ini`` holding only the default name."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / CONFIG_SUBDIR / CONFIG_FILE


def _os_error(error: OSError, action: str) -> ProfileError:
    """Translate an OSError without leaking the full path it carries."""
    return ProfileError(f"could not {action}: {error.strerror or error.__class__.__name__}")


def _private_dir(path: Path) -> Path:
    """Create ``path`` (mode 0700) and refuse links or foreign ownership."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.mkdir(mode=0o700, exist_ok=True)
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ProfileError("profile store must be a directory, not a link")
        if info.st_uid != os.getuid():
            raise ProfileError("profile store must be owned by the current user")
        if info.st_mode & 0o077:
            path.chmod(0o700)
    except OSError as error:
        raise _os_error(error, "prepare the profile store") from error
    return path


def _check_import_source(source: Path) -> os.stat_result:
    """Apply the ownership/type/size/suffix checks; permissions are fixed later."""
    try:
        info = source.lstat()
    except OSError as error:
        raise _os_error(error, "read the selected profile") from error
    if not stat.S_ISREG(info.st_mode):
        raise ProfileError("profile must be a regular file, not a link or device")
    if info.st_uid != os.getuid():
        raise ProfileError("profile must be owned by the current user")
    if info.st_size > MAX_PROFILE_SIZE:
        raise ProfileError("profile exceeds the 1 MiB safety limit")
    if source.suffix.lower() != PROFILE_SUFFIX:
        raise ProfileError("eitaas-remmina accepts only .rdpw profiles")
    if source.parent.resolve() == store_dir().resolve():
        raise ProfileError("profile is already in the store")
    return info


def _unique_target(store: Path, name: str) -> Path:
    """Preserve the basename, adding a numeric suffix if it is taken."""
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate = store / name
    counter = 1
    while candidate.exists() or candidate.is_symlink():
        counter += 1
        candidate = store / f"{stem}-{counter}{suffix}"
    return candidate


def _copy_then_unlink(source: Path, target: Path) -> None:
    """Cross-filesystem move: copy without following links, fsync, unlink."""
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
        try:
            while chunk := os.read(source_fd, _COPY_CHUNK):
                os.write(target_fd, chunk)
            os.fsync(target_fd)
        finally:
            os.close(target_fd)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    finally:
        os.close(source_fd)
    source.unlink()


def _move(source: Path, target: Path) -> None:
    try:
        try:
            os.rename(source, target)
        except OSError as error:
            if error.errno != errno.EXDEV:
                raise
            _copy_then_unlink(source, target)
            return
        target.chmod(0o600)
    except OSError as error:
        raise _os_error(error, "move the profile into the store") from error


def import_profile(source_value: str | os.PathLike[str]) -> StoredProfile:
    """Move a user-owned ``.rdpw`` into the private store and make it default."""
    source = Path(source_value).expanduser()
    _check_import_source(source)
    store = _private_dir(store_dir())
    target = _unique_target(store, source.name)
    _move(source, target)
    validate_profile(target)
    set_default(target.name)
    return StoredProfile(target.name, target, target.lstat().st_ctime, default=True)


def _read_default_name() -> str | None:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(config_path(), encoding="utf-8")
    except (OSError, configparser.Error):
        return None
    return parser.get(_SECTION, _DEFAULT_KEY, fallback=None) or None


def _write_default_name(name: str | None) -> None:
    path = config_path()
    _private_dir(path.parent)
    parser = configparser.ConfigParser(interpolation=None)
    parser[_SECTION] = {_DEFAULT_KEY: name} if name else {}
    try:
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".profiles-", text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            parser.write(handle)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError as error:
        raise _os_error(error, "write the profile configuration") from error


def list_profiles() -> list[StoredProfile]:
    """Stored profiles, most recently imported first; names only."""
    store = store_dir()
    try:
        entries = list(store.iterdir()) if store.is_dir() else []
    except OSError:
        return []
    default_name = _read_default_name()
    profiles = []
    for entry in entries:
        try:
            info = entry.lstat()
        except OSError:
            continue
        if not stat.S_ISREG(info.st_mode) or entry.suffix.lower() != PROFILE_SUFFIX:
            continue
        profiles.append(StoredProfile(entry.name, entry, info.st_ctime))
    profiles.sort(key=lambda item: (item.imported, item.name), reverse=True)
    if profiles and not any(item.name == default_name for item in profiles):
        default_name = profiles[0].name
    return [
        StoredProfile(item.name, item.path, item.imported, item.name == default_name)
        for item in profiles
    ]


def default_profile() -> StoredProfile | None:
    """The configured default, else the most recently imported profile."""
    for item in list_profiles():
        if item.default:
            return item
    return None


def _stored(name: str) -> StoredProfile:
    if name != Path(name).name or not name or name.startswith("."):
        raise ProfileError("profile name must be a plain file name")
    for item in list_profiles():
        if item.name == name:
            return item
    raise ProfileError("no imported profile has that name")


def set_default(name: str) -> StoredProfile:
    """Make an already imported profile the default for ``connect``."""
    item = _stored(name)
    _write_default_name(item.name)
    return StoredProfile(item.name, item.path, item.imported, default=True)


def remove_profile(name: str) -> None:
    """Delete a stored profile; the next most recent import becomes default."""
    item = _stored(name)
    try:
        item.path.unlink()
    except OSError as error:
        raise _os_error(error, "remove the profile") from error
    if _read_default_name() == item.name:
        _write_default_name(None)
