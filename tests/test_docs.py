"""Guard the current-facing documentation against stale product vocabulary.

The repository once documented a direct-FreeRDP/SDL design, a backend switch,
DoD certificate downloads, and "CAC" as the product term (#75). Those words
must not come back into any document a user or packager reads today. History
keeps its wording: `docs/adr/` and `docs/audits/` are dated records and are
never scanned, and neither is Git history.

A term that a current document must still name — always to say the project
deliberately does *not* use it — is listed in ``ALLOWED`` with the file and a
pattern the offending line has to match. ``ALLOWED`` is asserted to be exact:
an entry that no longer matches anything fails, so the exception list cannot
outlive its reason.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Historical records; their wording is deliberately preserved.
HISTORY = ("docs/adr/", "docs/audits/")
# Where this repository keeps prose. Globbed rather than listed by Git, because
# the package recipes run the suite from an unpacked source tree; they are
# narrow rather than a whole-tree walk, because that tree also holds the
# extracted Remmina and FreeRDP sources, whose documentation is not ours.
DOCUMENT_GLOBS = (
    "*.md",
    "NOTICE",
    "docs/**/*",
    "completions/*",
    "packaging/**/*.md",
    "upstream/**/*.md",
    "po/*.md",
)
# Files a user, packager, or contributor reads about the product as it is.
SCANNED_SUFFIXES = {".md", ".1", ".json", ".txt"}
SCANNED_EXTRA = {"NOTICE"}

FORBIDDEN = {
    # Direct-FreeRDP clients: connections go through the bundled eitaas-remmina.
    "xfreerdp": re.compile(r"(?i)\bxfreerdp\b"),
    "sdl-freerdp": re.compile(r"(?i)\bsdl-freerdp\b"),
    "freerdp-webview": re.compile(r"(?i)\bfreerdp-webview\b"),
    # Client/backend selection was removed with Application.connect (#69).
    "--backend": re.compile(r"--backend\b"),
    "SDL_VIDEODRIVER": re.compile(r"\bSDL_VIDEODRIVER\b"),
    # DoD certificate installation is out of scope (#8) and the command is gone.
    "cyber.mil": re.compile(r"(?i)\bcyber\.mil\b"),
    "eitaas certificates": re.compile(r"(?i)\beitaas certificates\b"),
    # Raising FreeRDP's log level makes it print OAuth tokens (#88).
    "WLOG_LEVEL": re.compile(r"\bWLOG_LEVEL\b"),
    # The product vocabulary is "smart card (PIV)" / "smart card", matching
    # Remmina's own. "CACHE", "cached", and the like keep their word boundary.
    "CAC": re.compile(r"\bCAC\b"),
}

# path -> {term: line pattern that the only acceptable occurrences match}.
ALLOWED = {
    # Both explain that the launcher deliberately exports no FreeRDP log-level
    # override, because at DEBUG FreeRDP logs the OAuth token exchange.
    "docs/eitaas.1": {"WLOG_LEVEL": re.compile(r"deliberately sets no WLOG_LEVEL")},
    "packaging/remmina/README.md": {"WLOG_LEVEL": re.compile(r"no `WLOG_LEVEL` or `WLOG_FILTER`")},
}


def current_documents() -> list[Path]:
    """Current-facing text files in this repository, minus the historical records."""
    documents = set()
    for pattern in DOCUMENT_GLOBS:
        for path in PROJECT_ROOT.glob(pattern):
            if not path.is_file():
                continue
            relative = path.relative_to(PROJECT_ROOT)
            if str(relative).startswith(HISTORY):
                continue
            text = (
                relative.suffix in SCANNED_SUFFIXES
                or relative.name in SCANNED_EXTRA
                or relative.parts[0] == "completions"
            )
            if text:
                documents.add(relative)
    return sorted(documents)


class ForbiddenTermTests(unittest.TestCase):
    """No current-facing document names a removed client, flag, or term."""

    @classmethod
    def setUpClass(cls):
        cls.documents = current_documents()
        cls.hits: dict[str, list[tuple[str, int, str]]] = {term: [] for term in FORBIDDEN}
        for path in cls.documents:
            try:
                text = (PROJECT_ROOT / path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                for term, pattern in FORBIDDEN.items():
                    if pattern.search(line):
                        cls.hits[term].append((str(path), number, line.strip()))

    def test_the_document_set_covers_every_place_prose_lives(self):
        """One representative per glob, so a silently empty scan cannot pass."""
        names = {str(path) for path in self.documents}
        for expected in (
            "README.md",
            "NOTICE",
            "docs/eitaas.1",
            "docs/frontend/ux-spec.md",
            "completions/_eitaas",
            "packaging/remmina/README.md",
            "upstream/remmina/README.md",
            "po/README.md",
        ):
            self.assertIn(expected, names)
        self.assertFalse(any(name.startswith(HISTORY) for name in names))

    def test_no_forbidden_term_outside_the_allowlist(self):
        for term, occurrences in self.hits.items():
            for path, number, line in occurrences:
                allowed = ALLOWED.get(path, {}).get(term)
                with self.subTest(term=term, path=path, line=number):
                    self.assertIsNotNone(
                        allowed, f"{path}:{number} uses the retired term {term!r}: {line}"
                    )
                    self.assertRegex(
                        line,
                        allowed,
                        f"{path}:{number} uses {term!r} outside its documented exception",
                    )

    def test_every_allowlist_entry_is_still_needed(self):
        """An exception that stops matching must be deleted, not left to rot."""
        for path, terms in ALLOWED.items():
            for term in terms:
                with self.subTest(path=path, term=term):
                    self.assertTrue(
                        any(hit[0] == path for hit in self.hits[term]),
                        f"{path} no longer contains {term!r}; drop the allowlist entry",
                    )


class RemovedSurfaceTests(unittest.TestCase):
    """The certificate surface removed in #75 leaves nothing behind."""

    def test_certificate_module_and_documentation_are_gone(self):
        for name in ("src/eitaas/certificates.py", "docs/certificates.md", "tests/test_certificates.py"):
            with self.subTest(name=name):
                self.assertFalse((PROJECT_ROOT / name).exists())

    def test_completions_offer_only_implemented_commands(self):
        from argparse import _SubParsersAction

        from eitaas.cli import parser

        commands = set(
            next(
                action.choices
                for action in parser()._actions
                if isinstance(action, _SubParsersAction)
            )
        )
        for name in ("completions/eitaas.bash", "completions/_eitaas"):
            text = (PROJECT_ROOT / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertTrue(commands.issubset(set(re.findall(r"[a-z-]+", text))))
                self.assertNotIn("certificates", text)


if __name__ == "__main__":
    unittest.main()
