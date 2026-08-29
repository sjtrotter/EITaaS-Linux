import unittest
from unittest.mock import patch

from eitaas.api import Application


class ApplicationAPITests(unittest.TestCase):
    @patch("eitaas.api.inspect_profile")
    def test_errors_are_redacted_at_boundary(self, inspect):
        inspect.side_effect = ValueError("code=very-secret-value")
        result = Application().inspect_profile("example.rdpw")
        self.assertFalse(result.ok)
        self.assertNotIn("very-secret-value", result.error.message)

    def test_profile_result_uses_basename_only(self):
        with patch("eitaas.api.inspect_profile") as inspect:
            inspect.return_value = {"size": 1, "mode": "0600", "fields": []}
            result = Application().inspect_profile("/sensitive/location/example.rdpw")
        self.assertTrue(result.ok)
        self.assertEqual(result.value.display_name, "example.rdpw")
        self.assertFalse(hasattr(result.value, "path"))


if __name__ == "__main__":
    unittest.main()
