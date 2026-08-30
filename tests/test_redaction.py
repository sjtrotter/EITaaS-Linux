import unittest

from eitaas.redaction import redact


class RedactionTests(unittest.TestCase):
    def test_query_code_is_redacted(self):
        value = redact("https://example.test/callback?code=secret&state=okay")
        self.assertNotIn("secret", value)
        self.assertNotIn("okay", value, "OAuth state is a transaction secret")
        self.assertIn("state=", value)

    def test_key_value_is_redacted(self):
        self.assertNotIn("hunter2", redact("password=hunter2"))

    def test_jwt_is_redacted(self):
        sample = "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxIn0" + ".signature"
        self.assertNotIn(sample, redact(sample))


class LogRedactionTests(unittest.TestCase):
    def test_remmina_debug_keys_with_prefixes_are_redacted(self):
        for line in (
            "proxy_password: synthetic-proxy-password",
            "proxy_username: synthetic-proxy-user",
            "login_hint=synthetic-hint",
            "loginhint: synthetic-hint",
            "upn=user@example.invalid",
            "email=user@example.invalid",
            "user=synthetic-user",
            "serial=synthetic-serial",
            "object=synthetic-object",
            "state=synthetic-state",
            "sid=synthetic-sid",
            "token=synthetic-token",
        ):
            with self.subTest(line=line):
                self.assertNotIn("synthetic", redact(line).replace("synthetic-id", ""))
                self.assertNotIn("example.invalid", redact(line))
                self.assertIn("<redacted>", redact(line))

    def test_pkcs11_uris_are_redacted_whole(self):
        line = ("loading pkcs11:model=PKCS%2315%20emulated;manufacturer=piv_II;serial=synthetic;"
                "token=PIV_II;id=%01;object=Certificate%20for%20PIV%20Authentication;type=cert done")
        self.assertEqual(redact(line), "loading <redacted-pkcs11-uri> done")
        self.assertEqual(redact("'pkcs11:token=X' failed"), "'<redacted-pkcs11-uri>' failed")

    def test_stage_lines_keep_their_counts_and_codes(self):
        line = ("smartcard-auth: discovery-finished (tokens=3 certificates=4 label-filter kept=2 dropped=2)"
                " discovery-token-empty (count=1 last-exit=1) challenge-received (scheme=client-certificate"
                " unverified-host=login.microsoftonline.us port=443 proxy=0 retry=0"
                " application=org.eitaas.Remmina remote=0)")
        self.assertEqual(redact(line), line)


if __name__ == "__main__":
    unittest.main()
