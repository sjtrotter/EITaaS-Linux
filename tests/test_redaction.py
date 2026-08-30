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

    def test_bearer_value_is_redacted(self):
        # FreeRDP logs the Authorization header only at TRACE level, which the
        # launcher never enables; redact bearer values anyway (belt and braces).
        for line in (
            "Authorization: Bearer synthetic.opaque-value~1",
            "using Bearer synthetic-opaque-value for the gateway",
            # wst.c appends the token as "ClmTk=Bearer%20..." but other
            # producers lower-case the scheme; the rule is case-insensitive.
            "using bearer synthetic-opaque-value for the gateway",
            "using BEARER synthetic-opaque-value for the gateway",
        ):
            redacted = redact(line)
            self.assertNotIn("synthetic", redacted, redacted)
            self.assertIn("<redacted>", redacted)
        self.assertIn(
            "Bearer <redacted>",
            redact("using Bearer synthetic-opaque-value for the gateway"),
        )

    def test_quoted_json_token_values_are_redacted(self):
        # The OAuth token endpoint answers with this exact shape; the refresh
        # token is opaque, so no JWT rule catches it, and the quotes keep the
        # key away from the bare "key: value" rule.
        body = (
            '{"token_type":"Bearer","access_token":"x",'
            '"refresh_token":"0.AXoAsyntheticREFRESHvalue123","id_token":"y"}'
        )
        redacted = redact(body)
        self.assertNotIn("0.AXoAsyntheticREFRESHvalue123", redacted)
        self.assertEqual(
            redacted,
            '{"token_type":"Bearer","access_token":"<redacted>",'
            '"refresh_token":"<redacted>","id_token":"<redacted>"}',
        )
        for key in ("code", "session", "authorization", "cookie", "secret"):
            with self.subTest(key=key):
                line = f'{{"{key}": "synthetic-value"}}'
                self.assertNotIn("synthetic-value", redact(line))

    def test_cookie_values_are_redacted(self):
        # FreeRDP logs the Azure load-balancing cookie at INFO level in
        # libfreerdp/core/gateway/wst.c, so it reaches the session log by
        # default (issue #88).
        cases = {
            "Got ARRAffinity cookie         synthetic-affinity-value":
                "Got ARRAffinity cookie         <redacted>",
            "Got ARRAffinitySameSite cookie synthetic-samesite-value":
                "Got ARRAffinitySameSite cookie <redacted>",
            "ARRAffinity=synthetic-affinity-value": "ARRAffinity=<redacted>",
            "Set-Cookie: ARRAffinity=synthetic-affinity-value; path=/; HttpOnly":
                "Set-Cookie: ARRAffinity=<redacted>",
            "set-cookie: synthetic-nameless-value": "set-cookie: <redacted>",
            "Cookie: ARRAffinity=synthetic-affinity-value":
                "Cookie: ARRAffinity=<redacted>",
        }
        for line, expected in cases.items():
            with self.subTest(line=line):
                self.assertEqual(redact(line), expected)

    def test_redaction_is_idempotent(self):
        for line in (
            '{"access_token":"synthetic"}',
            "Set-Cookie: ARRAffinity=synthetic-affinity-value",
            "Got ARRAffinity cookie synthetic-affinity-value",
            "password=synthetic",
            "using Bearer synthetic-opaque-value",
        ):
            with self.subTest(line=line):
                once = redact(line)
                self.assertEqual(redact(once), once)


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
