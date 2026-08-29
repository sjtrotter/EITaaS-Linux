import tempfile
import unittest
from pathlib import Path

from eitaas.certificates import CertificateError, fetch


class CertificateTests(unittest.TestCase):
    def test_rejects_non_official_host(self):
        with self.assertRaises(CertificateError):
            fetch("https://example.test/bundle.p7b", "0" * 64)

    def test_requires_pinned_digest(self):
        with self.assertRaises(CertificateError):
            fetch("https://public.cyber.mil/bundle.p7b", "latest")


if __name__ == "__main__":
    unittest.main()
