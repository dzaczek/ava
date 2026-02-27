import unittest
from fastapi.testclient import TestClient
from app.main import app, _rate_limiter

class TestRateLimitBypass(unittest.TestCase):
    def setUp(self):
        # Reset the rate limiter before each test
        _rate_limiter._hits.clear()
        self.client = TestClient(app)

    def test_multiple_x_forwarded_for_headers(self):
        """
        Test that an attacker cannot bypass the rate limiter by sending
        multiple X-Forwarded-For headers. Starlette's `request.headers.get()`
        only returns the first header value, so we must use `getlist()`.
        """
        # Make 35 requests where the "attacker" changes the first X-Forwarded-For
        # header, but the proxy (simulated) appends the real IP in a second header.

        real_ip = b"1.2.3.4"

        for i in range(35):
            # TestClient accepts headers as a list of tuples to allow multiple headers with the same name
            headers = [
                (b"x-forwarded-for", f"spoofed_{i}".encode("utf-8")),
                (b"x-forwarded-for", real_ip)
            ]

            response = self.client.get("/health", headers=headers)

            # The rate limiter is set to 30 requests per minute.
            # So the 31st request and beyond should be blocked.
            if i < 30:
                self.assertEqual(response.status_code, 200, f"Request {i+1} failed early with status {response.status_code}")
            else:
                self.assertEqual(response.status_code, 429, f"Request {i+1} bypassed rate limiter! Expected 429, got {response.status_code}")

    def test_comma_separated_x_forwarded_for(self):
        """
        Test that comma-separated X-Forwarded-For values correctly extract the last IP.
        """
        for i in range(35):
            # Simulate a single header with comma-separated values
            headers = [
                (b"x-forwarded-for", f"spoofed_{i}, 1.2.3.4".encode("utf-8")),
            ]

            response = self.client.get("/health", headers=headers)

            if i < 30:
                self.assertEqual(response.status_code, 200)
            else:
                self.assertEqual(response.status_code, 429)

if __name__ == '__main__':
    unittest.main()
