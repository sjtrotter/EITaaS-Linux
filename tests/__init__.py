"""Test-suite guard: no test may touch the developer's real XDG directories.

``unittest discover -s tests`` imports this package first. The XDG variables
are pointed at a suite-private temporary directory, and every TestCase run is
wrapped so that the profile store, the default-profile config, and the
session-log directory must resolve outside ``Path.home()`` before and after
the test; otherwise the test fails. Individual tests still point the XDG
variables at their own temporary directories.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

if "src" not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eitaas import profiles, remmina  # noqa: E402

_SUITE_HOME = Path(tempfile.mkdtemp(prefix="eitaas-tests-"))
for _variable, _name in (
    ("XDG_DATA_HOME", "share"),
    ("XDG_CONFIG_HOME", "config"),
    ("XDG_STATE_HOME", "state"),
):
    os.environ[_variable] = str(_SUITE_HOME / _name)


def _private_locations() -> dict[str, Path]:
    return {
        "profile store": profiles.store_dir(),
        "profile config": profiles.config_path(),
        "session logs": remmina.session_log_dir(),
    }


def assert_outside_home() -> None:
    home = Path.home().resolve()
    for label, location in _private_locations().items():
        resolved = Path(os.path.abspath(location))
        if resolved == home or home in resolved.parents:
            raise AssertionError(f"{label} resolves under the real home directory: {resolved}")


_original_run = unittest.TestCase.run


def _guarded_run(self, result=None):  # type: ignore[no-untyped-def]
    assert_outside_home()
    try:
        return _original_run(self, result)
    finally:
        assert_outside_home()


unittest.TestCase.run = _guarded_run  # type: ignore[method-assign]
