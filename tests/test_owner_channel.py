import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
from collections import deque
from app.owner_channel import OwnerChannel
import logging

# Disable logging during tests
logging.getLogger("app.owner_channel").setLevel(logging.CRITICAL)

class TestOwnerChannel(unittest.TestCase):
    def test_pruning_logic(self):
        """
        Verify that _seen_timestamps uses a deque with maxlen=500,
        correctly pruning old timestamps and keeping the most recent ones.
        """
        channel = OwnerChannel()
        channel.signal_sender = "+1234567890"

        # Create 600 messages with increasing timestamps
        messages = []
        for i in range(600):
            messages.append({
                "envelope": {
                    "timestamp": 1000 + i,
                    "dataMessage": {"message": "hello"},
                    "source": "+1987654321"
                }
            })

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = messages

        with patch("app.owner_channel.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_resp

            asyncio.run(channel._poll_once())

            seen = channel._seen_timestamps

            # Verify it's a deque with correct settings
            self.assertIsInstance(seen, deque)
            self.assertEqual(seen.maxlen, 500)

            # Verify size is capped at 500
            self.assertEqual(len(seen), 500)

            # Verify the LATEST timestamp (1599) is present
            self.assertIn(1599, seen)

            # Verify the OLDEST timestamp (1000) is gone (pruned)
            self.assertNotIn(1000, seen)

if __name__ == '__main__':
    unittest.main()
