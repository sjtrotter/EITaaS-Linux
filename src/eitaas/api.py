"""Stable, presentation-neutral application API.

The CLI and graphical frontends consume this module. Presentation code should
not import the platform modules directly or construct client arguments.

All calls are synchronous unless documented otherwise. GUI callers should run
blocking calls on a worker thread. Progress callbacks execute on that same
worker thread and must marshal updates onto the toolkit event loop.
"""

from __future__ import annotations

import datetime
import stat
import subprocess
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Generic, TypeVar

from . import doctor, profiles, remmina, smartcard
from . import __version__
from .profile import inspect_profile
from .redaction import redact

T = TypeVar("T")
# Longest line the session-log reader accepts in one read; longer output is split.
_MAX_LOG_LINE = 64 * 1024
ProgressCallback = Callable[["ProgressEvent"], None]
_BACKGROUND_OPERATIONS = ThreadPoolExecutor(max_workers=2, thread_name_prefix="eitaas-api")


@dataclass(frozen=True)
class ApplicationError:
    """A stable, already-redacted error safe for any presentation layer."""

    code: str
    message: str
    recovery: str | None = None


@dataclass(frozen=True)
class Result(Generic[T]):
    """Operation result that never requires presentation code to catch internals."""

    value: T | None = None
    error: ApplicationError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class ProgressEvent:
    phase: str
    message: str
    cancellable: bool = False


@dataclass(frozen=True)
class RemminaBundleSummary:
    """State of the bundled one-shot ``eitaas-remmina`` client."""

    launcher: bool
    client: bool
    client_path: str | None
    remmina_version: str
    freerdp_version: str


@dataclass(frozen=True)
class DoctorReport:
    platform: str
    session_type: str
    display: bool
    wayland_display: bool
    pcsc_socket: bool
    tools: dict[str, bool]
    remmina: RemminaBundleSummary
    ready: bool
    smartcard: SmartcardReport | None = None
    latest_session_log: str | None = None


@dataclass(frozen=True)
class ProfileField:
    name: str
    field_type: str
    value: str


@dataclass(frozen=True)
class ProfileSummary:
    display_name: str
    size: int
    mode: str
    cloud: str
    fields: tuple[ProfileField, ...]


@dataclass(frozen=True)
class SmartcardComponent:
    name: str
    available: bool
    ok: bool
    summary: str


@dataclass(frozen=True)
class SmartcardReport:
    components: tuple[SmartcardComponent, ...]
    ready: bool


@dataclass(frozen=True)
class StoredProfileSummary:
    """An imported profile in the private store; names only, never paths."""

    name: str
    cloud: str
    size: int
    mode: str
    imported: str
    default: bool


@dataclass(frozen=True)
class ConnectionRequest:
    """``profile`` is an explicit path; ``None`` selects the stored default."""

    profile: str | None = None


@dataclass(frozen=True)
class ConnectionResult:
    exit_code: int
    cancelled: bool = False
    log_path: str | None = None
    # ``smartcard-auth:`` warning lines seen in the session log; a failed
    # smart-card stage can end with exit status 0 when the user closes the window.
    log_warnings: int = 0


@dataclass(frozen=True)
class SessionLogSummary:
    """A redacted session log: its location, the reason-code lines, and the full text."""

    path: str
    reason_lines: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class DiagnosticReport:
    application_version: str
    doctor: DoctorReport | None
    smartcard: SmartcardReport | None
    profile: ProfileSummary | None
    errors: tuple[ApplicationError, ...]


def to_public_dict(value: object) -> object:
    """Convert API dataclasses into JSON-compatible public data."""
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_public_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_public_dict(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_public_dict(item) for item in value]
    return value


class Application:
    """Facade shared by CLI and graphical presentations.

    Methods return redacted Result values. `launch` is blocking and should run
    on a worker thread in a GUI. Set the supplied cancellation event to request
    termination; the child receives terminate, then kill after a short grace
    period. The callback is never given child output or command arguments.
    """

    def _error(self, code: str, error: BaseException, recovery: str | None = None) -> Result[object]:
        return Result(error=ApplicationError(code, redact(str(error)), recovery))

    def doctor(self) -> Result[DoctorReport]:
        try:
            data = doctor.report()
            smartcard_result = self.smartcard_status()
            bundle = data["remmina"]
            summary = RemminaBundleSummary(
                launcher=bool(bundle["launcher"]),
                client=bool(bundle["client"]),
                client_path=str(bundle["client_path"]) if bundle["client_path"] else None,
                remmina_version=str(bundle["remmina_version"]),
                freerdp_version=str(bundle["freerdp_version"]),
            )
            return Result(
                DoctorReport(
                    platform=str(data["platform"]),
                    session_type=str(data["session_type"]),
                    display=bool(data["display"]),
                    wayland_display=bool(data["wayland_display"]),
                    pcsc_socket=bool(data["pcsc_socket"]),
                    tools={str(key): bool(value) for key, value in data["tools"].items()},
                    remmina=summary,
                    ready=bool(
                        doctor.healthy(data)
                        and smartcard_result.ok
                        and smartcard_result.value
                        and smartcard_result.value.ready
                    ),
                    smartcard=smartcard_result.value,
                    latest_session_log=(
                        str(data["latest_session_log"]) if data.get("latest_session_log") else None
                    ),
                )
            )
        except Exception as error:
            return self._error("doctor_failed", error)

    def doctor_async(self) -> Future[Result[DoctorReport]]:
        """Run all doctor checks away from a GUI toolkit event loop."""
        return _BACKGROUND_OPERATIONS.submit(self.doctor)

    def inspect_profile(self, path: str) -> Result[ProfileSummary]:
        try:
            data = inspect_profile(path)
            fields = tuple(
                ProfileField(str(item["name"]), str(item["type"]), str(item["value"]))
                for item in data["fields"]
            )
            return Result(
                ProfileSummary(
                    Path(path).name,
                    int(data["size"]),
                    str(data["mode"]),
                    str(data["cloud"]),
                    fields,
                )
            )
        except Exception as error:
            return self._error(
                "profile_invalid", error, "Choose a current .rdp or .rdpw file owned by you with mode 0600."
            )

    def _stored_summary(self, item: profiles.StoredProfile) -> StoredProfileSummary:
        summary = self.inspect_profile(str(item.path)).value
        imported = datetime.datetime.fromtimestamp(item.imported).isoformat(timespec="seconds")
        return StoredProfileSummary(
            name=item.name,
            cloud=summary.cloud if summary else "unknown",
            size=summary.size if summary else 0,
            mode=summary.mode if summary else "unknown",
            imported=imported,
            default=item.default,
        )

    def import_profile(self, path: str) -> Result[StoredProfileSummary]:
        """Move a downloaded ``.rdpw`` into the private store as the default."""
        try:
            return Result(self._stored_summary(profiles.import_profile(path)))
        except Exception as error:
            return self._error(
                "profile_import_failed",
                error,
                "Choose the .rdpw file you exported from the web client; it must be a regular file owned by you.",
            )

    def import_profile_async(self, path: str) -> Future[Result[StoredProfileSummary]]:
        return _BACKGROUND_OPERATIONS.submit(self.import_profile, path)

    def list_profiles(self) -> Result[tuple[StoredProfileSummary, ...]]:
        try:
            return Result(tuple(self._stored_summary(item) for item in profiles.list_profiles()))
        except Exception as error:
            return self._error("profile_store_failed", error)

    def list_profiles_async(self) -> Future[Result[tuple[StoredProfileSummary, ...]]]:
        return _BACKGROUND_OPERATIONS.submit(self.list_profiles)

    def default_profile(self) -> Result[StoredProfileSummary | None]:
        try:
            item = profiles.default_profile()
            return Result(self._stored_summary(item) if item else None)
        except Exception as error:
            return self._error("profile_store_failed", error)

    def select_profile(self, name: str) -> Result[StoredProfileSummary]:
        """Make an imported profile the default used by ``launch``."""
        try:
            return Result(self._stored_summary(profiles.set_default(name)))
        except Exception as error:
            return self._error("profile_store_failed", error, "Use a name from the imported profile list.")

    def remove_profile(self, name: str) -> Result[bool]:
        """Delete an imported profile from the private store."""
        try:
            profiles.remove_profile(name)
            return Result(True)
        except Exception as error:
            return self._error("profile_store_failed", error, "Use a name from the imported profile list.")

    def smartcard_status(self) -> Result[SmartcardReport]:
        try:
            data = smartcard.status()
            components = tuple(
                SmartcardComponent(
                    name=str(name),
                    available=bool(item["available"]),
                    ok=bool(item["ok"]),
                    summary=redact(str(item["summary"])),
                )
                for name, item in data.items()
            )
            return Result(SmartcardReport(components, all(item.ok for item in components)))
        except Exception as error:
            return self._error("smartcard_check_failed", error)

    def smartcard_status_async(self) -> Future[Result[SmartcardReport]]:
        """Run bounded PC/SC and middleware checks on a worker thread."""
        return _BACKGROUND_OPERATIONS.submit(self.smartcard_status)

    def diagnostics(self, profile: str | None = None) -> Result[DiagnosticReport]:
        """Build a safe support report without full paths or raw command output."""
        doctor_result = self.doctor()
        smartcard_result = Result(
            doctor_result.value.smartcard if doctor_result.value else None,
            doctor_result.error,
        )
        profile_result = self.inspect_profile(profile) if profile else None
        results = [doctor_result, smartcard_result]
        if profile_result:
            results.append(profile_result)
        errors = tuple(item.error for item in results if item.error is not None)
        return Result(
            DiagnosticReport(
                application_version=__version__,
                doctor=doctor_result.value,
                smartcard=smartcard_result.value,
                profile=profile_result.value if profile_result else None,
                errors=errors,
            )
        )

    @staticmethod
    def _launch_path(request: ConnectionRequest) -> Path:
        if request.profile:
            return Path(request.profile)
        stored = profiles.default_profile()
        if stored is None:
            raise RuntimeError("no imported profile; run: eitaas profile import FILE.rdpw")
        return stored.path

    def launch(
        self,
        request: ConnectionRequest,
        on_progress: ProgressCallback | None = None,
        cancel: threading.Event | None = None,
    ) -> Result[ConnectionResult]:
        """Validate the profile and run the bundled ``eitaas-remmina`` launcher.

        Without an explicit ``request.profile`` the stored default profile
        (``eitaas profile import``) is used. The child receives exactly ``[launcher, profile]`` with no shell, no
        environment changes, stdin on ``DEVNULL``, and stdout/stderr on a pipe
        that a reader thread drains into a private, redacted session log
        (``remmina.SessionLog``); nothing is printed to a terminal. Endpoint
        allowlisting and the refusal of terminal OAuth are enforced inside the
        bundled client (Remmina patches), not here.
        """
        progress = on_progress or (lambda event: None)
        cancelled = cancel or threading.Event()
        try:
            progress(ProgressEvent("validating", "Validating connection profile"))
            profile = remmina.validate_launch_profile(self._launch_path(request))
            launcher = remmina.find_launcher()
            if launcher is None:
                raise RuntimeError(f"{remmina.LAUNCHER} launcher is not installed")
            if cancelled.is_set():
                return Result(ConnectionResult(130, cancelled=True))
            progress(ProgressEvent("starting", "Remote desktop client started", cancellable=True))
            log = self._open_session_log(profile)
            process = subprocess.Popen(
                [launcher, str(profile)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE if log else subprocess.DEVNULL,
                stderr=subprocess.STDOUT if log else subprocess.DEVNULL,
            )
            reader = self._start_output_reader(process, log)
            was_cancelled = False
            while process.poll() is None:
                if cancelled.wait(0.1):
                    progress(ProgressEvent("cancelling", "Stopping remote desktop client"))
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    was_cancelled = True
                    break
            code = process.returncode
            if was_cancelled and code < 0:
                code = 130
            log_path = self._close_session_log(log, reader, code, process.stdout)
            return Result(ConnectionResult(code or 0, cancelled=was_cancelled, log_path=log_path,
                                           log_warnings=log.warnings if log else 0))
        except Exception as error:
            return self._error("launch_failed", error, "Run eitaas doctor and correct failed checks.")

    @staticmethod
    def _open_session_log(profile: Path) -> remmina.SessionLog | None:
        """Best effort: a log that cannot be created must not prevent connecting."""
        try:
            log = remmina.SessionLog.open()
        except OSError:
            return None
        log.write(f"eitaas-linux {__version__} profile={profile.name}")
        log.write(f"remmina instances already running: {remmina.running_remmina_instances()}")
        return log

    @staticmethod
    def _start_output_reader(
        process: subprocess.Popen, log: remmina.SessionLog | None
    ) -> threading.Thread | None:
        """Drain the child's pipe on a daemon thread so the child never blocks on a full pipe."""
        if log is None or process.stdout is None:
            return None
        stream = process.stdout

        def pump() -> None:
            try:
                for raw in iter(lambda: stream.readline(_MAX_LOG_LINE), b""):
                    log.write(raw.decode("utf-8", errors="replace"))
            except (OSError, ValueError, TypeError):
                pass  # a broken pipe ends logging, never the connection

        thread = threading.Thread(target=pump, name="eitaas-session-log", daemon=True)
        thread.start()
        return thread

    @staticmethod
    def _close_session_log(
        log: remmina.SessionLog | None,
        reader: threading.Thread | None,
        exit_code: int | None,
        process_stdout: object = None,
    ) -> str | None:
        if log is None:
            return None
        if reader is not None:
            # A grandchild holding the pipe open must not stall the result;
            # closing our end of the pipe lets the reader thread finish.
            reader.join(timeout=2)
            if process_stdout is not None:
                try:
                    process_stdout.close()
                except OSError:
                    pass
        log.close(exit_code)
        return str(log.path)

    def session_log(self, path: str) -> Result[SessionLogSummary]:
        """Read one session log written by ``launch``; only files inside the log directory are served."""
        try:
            candidate = Path(path)
            directory = remmina.session_log_dir().resolve()
            if candidate.parent.resolve() != directory or not candidate.name.startswith(remmina.SESSION_LOG_PREFIX):
                raise ValueError("not a session log")
            info = candidate.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > remmina.SESSION_LOG_LIMIT + 4096:
                raise ValueError("not a session log")
            text = candidate.read_text(encoding="utf-8", errors="replace")
            return Result(SessionLogSummary(str(candidate), remmina.reason_lines(text), text))
        except Exception as error:
            return self._error("session_log_failed", error)
