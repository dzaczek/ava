import sys
import unittest
from unittest.mock import patch
import os

class TestEnvValidation(unittest.TestCase):
    def setUp(self):
        # Clean up any existing app.main import to ensure we test module-level logic
        if 'app.main' in sys.modules:
            del sys.modules['app.main']

        # We need to mock other required vars like OPENAI_API_KEY so we don't fail on them
        # Also need to clear TWILIO_AUTH_TOKEN to be safe
        self.env_patcher = patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}, clear=True)
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        if 'app.main' in sys.modules:
            del sys.modules['app.main']

    def test_missing_twilio_token_raises_error(self):
        # Ensure TWILIO_AUTH_TOKEN is missing or empty
        with patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": ""}):
            # We expect a ValueError or similar when the fix is implemented
            # For now, this test will fail because the app starts successfully
            with self.assertRaises(ValueError) as cm:
                import app.main
            self.assertIn("TWILIO_AUTH_TOKEN must be set", str(cm.exception))

    def test_present_twilio_token_starts_app(self):
        with patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "some_token"}):
            try:
                import app.main
            except ValueError:
                self.fail("app.main raised ValueError unexpectedly!")

if __name__ == '__main__':
    unittest.main()
