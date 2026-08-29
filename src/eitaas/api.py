"""Stable, presentation-neutral application API.

The CLI and graphical frontends consume this module. Presentation code should
not import the platform modules directly or construct FreeRDP arguments.

All calls are synchronous unless documented otherwise. GUI callers should run
blocking calls on a worker thread. Progress callbacks execute on that same
worker thread and must marshal updates onto the toolkit event loop.
"""

from __future__ import annotations

import os
import subprocess
import threading
import urllib.parse
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Generic, Literal, TypeVar

from . import certificates, doctor, smartcard
from . import __version__
from .freerdp import Client, select
from .profile import detect_cloud, inspect_profile, validate_profile
from .redaction import redact

T = TypeVar("T")
Backend = Literal["auto", "x11", "sdl", "wayland"]
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
class FreeRDPClientSummary:
    backend: str
    version: str
    aad: bool
    pcsc: bool
    sso_mib: bool
    webview: bool
    auth_mode: str


@dataclass(frozen=True)
class DoctorReport:
    platform: str
    session_type: str
    display: bool
    wayland_display: bool
    pcsc_socket: bool
    tools: dict[str, bool]
    freerdp: tuple[FreeRDPClientSummary, ...]
    identity_broker: bool
    ready: bool
    smartcard: SmartcardReport | None = None


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
class CertificateSummary:
    subject: str
    issuer: str
    sha256_fingerprint: str
    self_signed_candidate: bool


@dataclass(frozen=True)
class CertificateBundleReport:
    display_name: str
    sha256: str
    certificates: tuple[CertificateSummary, ...]


@dataclass(frozen=True)
class CertificateFetchReport:
    display_name: str
    sha256: str
    source_host: str


@dataclass(frozen=True)
class ConnectionRequest:
    profile: str
    backend: Backend = "auto"
    clipboard: bool = False


@dataclass(frozen=True)
class ConnectionResult:
    exit_code: int
    cancelled: bool = False


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

    Methods return redacted Result values. `connect` is blocking and should run
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
            clients = tuple(
                FreeRDPClientSummary(
                    backend=str(item["backend"]),
                    version=str(item["version"]),
                    aad=bool(item["aad"]),
                    pcsc=bool(item["pcsc"]),
                    sso_mib=bool(item["sso_mib"]),
                    webview=bool(item["webview"]),
                    auth_mode=str(item["auth_mode"]),
                )
                for item in data["freerdp"]
            )
            return Result(
                DoctorReport(
                    platform=str(data["platform"]),
                    session_type=str(data["session_type"]),
                    display=bool(data["display"]),
                    wayland_display=bool(data["wayland_display"]),
                    pcsc_socket=bool(data["pcsc_socket"]),
                    tools={str(key): bool(value) for key, value in data["tools"].items()},
                    freerdp=clients,
                    identity_broker=bool(data["identity_broker"]),
                    ready=bool(
                        doctor.healthy(data)
                        and smartcard_result.ok
                        and smartcard_result.value
                        and smartcard_result.value.ready
                    ),
                    smartcard=smartcard_result.value,
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

    def inspect_certificates(self, path: str) -> Result[CertificateBundleReport]:
        try:
            data = certificates.inspect(path)
            items = tuple(
                CertificateSummary(
                    subject=str(item["subject"]),
                    issuer=str(item["issuer"]),
                    sha256_fingerprint=str(item["sha256_fingerprint"]),
                    self_signed_candidate=bool(item["self_signed_candidate"]),
                )
                for item in data["certificates"]
            )
            return Result(CertificateBundleReport(Path(path).name, str(data["sha256"]), items))
        except Exception as error:
            return self._error("certificate_inspection_failed", error)

    def fetch_certificates(
        self, url: str, expected_sha256: str, destination: str | None = None
    ) -> Result[CertificateFetchReport]:
        try:
            data = certificates.fetch(url, expected_sha256, destination)
            host = urllib.parse.urlsplit(str(data["source"])).hostname or ""
            return Result(
                CertificateFetchReport(Path(str(data["path"])).name, str(data["sha256"]), host)
            )
        except Exception as error:
            return self._error("certificate_fetch_failed", error)

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

    def connect(
        self,
        request: ConnectionRequest,
        on_progress: ProgressCallback | None = None,
        cancel: threading.Event | None = None,
    ) -> Result[ConnectionResult]:
        progress = on_progress or (lambda event: None)
        cancelled = cancel or threading.Event()
        try:
            progress(ProgressEvent("validating", "Validating connection profile"))
            profile = validate_profile(request.profile)
            progress(ProgressEvent("selecting", "Selecting a compatible FreeRDP client"))
            client = select(request.backend)
            cloud = detect_cloud(profile)
            command = self._connection_command(client, profile, request.clipboard, cloud)
            if cancelled.is_set():
                return Result(ConnectionResult(130, cancelled=True))
            progress(ProgressEvent("connecting", "FreeRDP connection started", cancellable=True))
            child_environment = None
            if client.path == "/usr/libexec/eitaas-freerdp/bin/sdl-freerdp":
                # SDL3's Wayland/libdecor event pump races GTK3/WebKitGTK 4.1.
                # Keep the isolated prototype on XWayland until upstream can
                # safely run both event loops on native Wayland.
                child_environment = os.environ.copy()
                child_environment["SDL_VIDEODRIVER"] = "x11"
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=child_environment,
            )
            while process.poll() is None:
                if cancelled.wait(0.1):
                    progress(ProgressEvent("cancelling", "Stopping FreeRDP connection"))
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    return Result(ConnectionResult(process.returncode or 130, cancelled=True))
            return Result(ConnectionResult(process.returncode or 0))
        except Exception as error:
            return self._error("connection_failed", error, "Run eitaas doctor and correct failed checks.")

    @staticmethod
    def _connection_command(
        client: Client, profile: Path, clipboard: bool, cloud: str
    ) -> list[str]:
        cloud_settings = {
            "azure_government": (
                "https://login.microsoftonline.us",
                "https%3A%2F%2Fwww.wvd.azure.us%2F.default%20openid%20profile%20offline_access",
            ),
            "azure_commercial": (
                "https://login.microsoftonline.com",
                "https%3A%2F%2Fwww.wvd.microsoft.com%2F.default%20openid%20profile%20offline_access",
            ),
        }
        if cloud not in cloud_settings:
            raise ValueError("profile cloud is not supported")
        authority, scope = cloud_settings[cloud]
        callback = "https://login.microsoftonline.com/common/oauth2/nativeclient"
        Application._validate_identity_endpoint(
            authority, {"login.microsoftonline.us", "login.microsoftonline.com"}
        )
        Application._validate_identity_endpoint(callback, {"login.microsoftonline.com"})
        return [
            client.path,
            str(profile),
            "/gateway:type:arm",
            "/sec:aad",
            f"/azure:ad:{urllib.parse.urlsplit(authority).hostname},use-tenantid:on,"
            f"avd-access:{callback},avd-scope:{scope}",
            "/smartcard",
            "+clipboard" if clipboard else "-clipboard",
        ]

    @staticmethod
    def _validate_identity_endpoint(url: str, allowed_hosts: set[str]) -> None:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
            raise ValueError("identity endpoint is not an approved HTTPS host")
        if parsed.username or parsed.password:
            raise ValueError("identity endpoint must not contain user information")
