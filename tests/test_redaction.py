import unittest

from eitaas.redaction import redact


class RedactionTests(unittest.TestCase):
    def test_query_code_is_redacted(self):
        value = redact("https://example.test/callback?code=secret&state=okay")
        self.assertNotIn("secret", value)
        self.assertIn("state=okay", value)

    def test_key_value_is_redacted(self):
        self.assertNotIn("hunter2", redact("password=hunter2"))

    def test_jwt_is_redacted(self):
        sample = "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxIn0" + ".signature"
        self.assertNotIn(sample, redact(sample))


if __name__ == "__main__":
    unittest.main()
