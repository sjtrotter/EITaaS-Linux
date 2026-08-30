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
    valid: bool = True


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


def _open_source(source: Path) -> int:
    """Open the selected file without following links; all checks use the fd."""
    try:
        return os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise ProfileError("profile must be a regular file, not a link or device") from error
        raise _os_error(error, "read the selected profile") from error


def _check_source(fd: int, source: Path) -> os.stat_result:
    """Type/ownership/size/suffix checks on the open descriptor; mode is fixed later."""
    info = os.fstat(fd)
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


def _candidates(store: Path, name: str):
    """Basename first, then ``stem-2``, ``stem-3``…; creation is EEXIST-safe."""
    stem, suffix = Path(name).stem, Path(name).suffix
    yield store / name
    counter = 1
    while True:
        counter += 1
        yield store / f"{stem}-{counter}{suffix}"


def _link_into_store(source: Path, store: Path) -> Path | None:
    """Hard-link the source under a free name; None when on another filesystem."""
    for target in _candidates(store, source.name):
        try:
            os.link(source, target, follow_symlinks=False)
            return target
        except FileExistsError:
            continue
        except OSError as error:
            if error.errno == errno.EXDEV:
                return None
            raise


def _copy_bounded(source_fd: int, target_fd: int) -> None:
    """Copy at most the safety limit, fully writing each chunk, then fsync."""
    remaining = MAX_PROFILE_SIZE + 1
    while remaining:
        chunk = os.read(source_fd, min(_COPY_CHUNK, remaining))
        if not chunk:
            break
        remaining -= len(chunk)
        view = memoryview(chunk)
        while view:
            view = view[os.write(target_fd, view):]
    if not remaining:
        raise ProfileError("profile exceeds the 1 MiB safety limit")
    os.fsync(target_fd)


def _copy_into_store(source_fd: int, source: Path, store: Path) -> tuple[Path, os.stat_result]:
    """Cross-filesystem import: exclusive-create a 0600 copy, return its identity."""
    for target in _candidates(store, source.name):
        try:
            target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
        except FileExistsError:
            continue
        try:
            _copy_bounded(source_fd, target_fd)
            return target, os.fstat(target_fd)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        finally:
            os.close(target_fd)
    raise AssertionError("unreachable")


def _verify_stored(target: Path, expected: os.stat_result) -> None:
    """The store entry must be the very inode that was checked, mode 0600."""
    info = target.lstat()
    same = (info.st_dev, info.st_ino) == (expected.st_dev, expected.st_ino)
    if not stat.S_ISREG(info.st_mode) or not same or info.st_mode & 0o077:
        target.unlink(missing_ok=True)
        raise ProfileError("profile changed while it was being imported")


def _move_into_store(fd: int, source: Path, store: Path) -> Path:
    try:
        target = _link_into_store(source, store)
        if target is not None:
            os.fchmod(fd, 0o600)
            _verify_stored(target, os.fstat(fd))
            source.unlink()
            return target
        target, identity = _copy_into_store(fd, source, store)
        _verify_stored(target, identity)
        source.unlink()
        return target
    except OSError as error:
        raise _os_error(error, "move the profile into the store") from error


def import_profile(source_value: str | os.PathLike[str]) -> StoredProfile:
    """Move a user-owned ``.rdpw`` into the private store and make it default."""
    source = Path(source_value).expanduser()
    fd = _open_source(source)
    try:
        _check_source(fd, source)
        store = _private_dir(store_dir())
        target = _move_into_store(fd, source, store)
    finally:
        os.close(fd)
    try:
        validate_profile(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
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
            handle.flush()
            os.fsync(handle.fileno())
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
        profiles.append(StoredProfile(entry.name, entry, info.st_ctime, valid=_validates(entry)))
    profiles.sort(key=lambda item: (item.imported, item.name), reverse=True)
    if not any(item.name == default_name and item.valid for item in profiles):
        default_name = next((item.name for item in profiles if item.valid), None)
    return [
        StoredProfile(item.name, item.path, item.imported, item.name == default_name, item.valid)
        for item in profiles
    ]


def _validates(path: Path) -> bool:
    try:
        validate_profile(path)
    except (ProfileError, OSError):
        return False
    return True


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
    if not item.valid:
        raise ProfileError("stored profile no longer passes the safety checks")
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
