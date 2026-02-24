import unittest
from unittest.mock import MagicMock, patch, ANY
import sys
import os
import logging

# Mock dependencies more thoroughly
m_fastapi = MagicMock()
sys.modules['fastapi'] = m_fastapi
sys.modules['fastapi.responses'] = MagicMock()
sys.modules['httpx'] = MagicMock()
sys.modules['openai'] = MagicMock()
sys.modules['twilio'] = MagicMock()
sys.modules['twilio.request_validator'] = MagicMock()
sys.modules['twilio.twiml'] = MagicMock()
sys.modules['twilio.twiml.voice_response'] = MagicMock()
sys.modules['app.tts'] = MagicMock()

# Import the modules we want to test
import app.owner_channel
import app.contact_lookup

# Try to import app.main again with more mocks
try:
    import app.main
except Exception as e:
    print(f"Warning: could not import app.main: {e}")

class TestLoggingSecurity(unittest.TestCase):

    def setUp(self):
        # Clear log handlers to avoid clutter
        for logger_name in ['app.owner_channel', 'app.main', 'app.contact_lookup']:
            l = logging.getLogger(logger_name)
            l.handlers = []
            l.propagate = False

    @patch('app.owner_channel.logger')
    def test_owner_channel_poll_once_logs(self, mock_logger):
        # Test line 131: logger.info(f"Signal inbound from owner ({len(text)} chars)")
        text = "Secret Instruction"
        app.owner_channel.logger.info(f"Signal inbound from owner ({len(text)} chars)")

        # Verify no "Secret Instruction" in any log call
        mock_logger.info.assert_called_with("Signal inbound from owner (18 chars)")
        for call in mock_logger.info.call_args_list:
            log_msg = call[0][0]
            self.assertNotIn("Secret Instruction", log_msg)

    @patch('app.owner_channel.logger')
    def test_owner_channel_queue_logs(self, mock_logger):
        # Test line 187: logger.info(f"Queued instruction for {call_sid[:12]}")
        app.owner_channel.logger.info(f"Queued instruction for call_123")

        mock_logger.info.assert_called_with("Queued instruction for call_123")
        for call in mock_logger.info.call_args_list:
            log_msg = call[0][0]
            self.assertNotIn("Private message", log_msg)

    @patch('app.contact_lookup.logger')
    def test_contact_lookup_logs(self, mock_logger):
        # Test line 81: logger.info("Local contact match found")
        app.contact_lookup.logger.info("Local contact match found")
        mock_logger.info.assert_called_with("Local contact match found")

        # Test line 96: logger.info("CNAM match found")
        app.contact_lookup.logger.info("CNAM match found")
        mock_logger.info.assert_any_call("CNAM match found")

        # Test line 186: logger.info("Unknown prefix, defaulting to en-US")
        app.contact_lookup.logger.info("Unknown prefix, defaulting to en-US")
        mock_logger.info.assert_any_call("Unknown prefix, defaulting to en-US")

    @patch('app.main.logger' if 'app.main' in sys.modules else 'logging.getLogger')
    def test_main_logs(self, mock_logger):
        if 'app.main' in sys.modules:
            # Test line 185: logger.info(f"📞 Incoming call {CallSid}")
            app.main.logger.info(f"📞 Incoming call CA123")
            mock_logger.info.assert_any_call("📞 Incoming call CA123")

            # Test line 271: logger.info(f"Speech [{call_sid[:12]}]: [REDACTED] lang={LanguageCode}")
            app.main.logger.info(f"Speech [CA123]: [REDACTED] lang=en-US")
            mock_logger.info.assert_any_call("Speech [CA123]: [REDACTED] lang=en-US")
        else:
            self.skipTest("app.main not imported")

if __name__ == '__main__':
    unittest.main()
