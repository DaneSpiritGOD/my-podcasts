"""Tests for the fetch transport's URL allowlist.

The URLs the pipeline fetches come from the Source Feed, which is remote input.
These tests pin the boundary that stops a compromised feed from turning the
pipeline into a reader for local files or cloud metadata endpoints.
"""

import unittest

import fetch


class CheckURLTests(unittest.TestCase):
    def test_source_site_is_allowed(self):
        fetch.check_url("https://commandline.microsoft.com/feed/")
        fetch.check_url(
            "https://commandline.microsoft.com/?content_audio=1&content_sig=abc"
        )

    def test_file_scheme_is_blocked(self):
        with self.assertRaises(fetch.BlockedURLError):
            fetch.check_url("file:///etc/hosts")

    def test_http_is_blocked(self):
        with self.assertRaises(fetch.BlockedURLError):
            fetch.check_url("http://commandline.microsoft.com/feed/")

    def test_metadata_endpoint_is_blocked(self):
        with self.assertRaises(fetch.BlockedURLError):
            fetch.check_url("https://169.254.169.254/latest/meta-data/")

    def test_other_host_is_blocked(self):
        with self.assertRaises(fetch.BlockedURLError):
            fetch.check_url("https://example.com/")

    def test_host_suffix_does_not_slip_through(self):
        with self.assertRaises(fetch.BlockedURLError):
            fetch.check_url("https://commandline.microsoft.com.evil.test/")

    def test_host_is_case_insensitive(self):
        fetch.check_url("https://COMMANDLINE.MICROSOFT.COM/feed/")

    def test_trailing_dot_in_host_is_normalised(self):
        fetch.check_url("https://commandline.microsoft.com./feed/")

    def test_blocked_url_is_a_fetch_error(self):
        """Callers already handle FetchError, so blocking must be one."""
        self.assertTrue(issubclass(fetch.BlockedURLError, fetch.FetchError))

    def test_blocked_url_reports_the_reason(self):
        try:
            fetch.check_url("file:///etc/hosts")
        except fetch.BlockedURLError as exc:
            self.assertIn("scheme", exc.reason)
            self.assertEqual(exc.url, "file:///etc/hosts")
        else:
            self.fail("expected BlockedURLError")


class TransportTests(unittest.TestCase):
    def test_get_text_refuses_a_blocked_url_without_a_request(self):
        transport = fetch.Transport()
        with self.assertRaises(fetch.BlockedURLError):
            transport.get_text("file:///etc/hosts")

    def test_probe_reports_zero_for_a_blocked_url(self):
        """The Sentinel reads 0 as "unreachable", which opens no issue."""
        self.assertEqual(fetch.Transport().probe("file:///etc/hosts"), 0)


if __name__ == "__main__":
    unittest.main()
