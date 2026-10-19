"""End-to-end tests for the CLI.

These pin the contract the workflow depends on: exit codes, the OUTCOME line,
and the fact that a dry run never touches the working tree.

The transport is replaced with an offline fake. A test that reaches the real
source site is a test that fails for reasons unrelated to the code, and this
suite must stay green with no network at all.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import fetch as fetch_mod
import run as run_mod


class OfflineTransport:
    """A transport that refuses every request, like a total outage."""

    def __init__(self, *args, **kwargs):
        pass

    def get_text(self, url):
        raise fetch_mod.FetchError(url, "offline test double")

    def probe(self, url):
        return 0


class BrokenEpisodeTransport:
    """The source site is reachable, but one Episode's audio is gone for good.

    This is the shape of a takedown: the Source URL 403s and the Article page
    no longer offers audio, so the Sentinel cannot recover it.
    """

    def __init__(self, *args, **kwargs):
        pass

    def get_text(self, url):
        if url.rstrip("/").endswith("/feed"):
            return (
                '<?xml version="1.0"?><rss version="2.0"><channel>'
                "<title>Command Line</title></channel></rss>"
            )
        return "<html><body>no player here</body></html>"

    def probe(self, url):
        return 403


def write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def state_doc(published="Thu, 15 Oct 2026 15:00:22 +0000"):
    return json.dumps(
        {
            "version": 1,
            "articles": {
                "https://example.test/?p=1": {
                    "guid": "https://example.test/?p=1",
                    "title": "An Episode",
                    "link": "https://example.test/one/",
                    "published": published,
                    "status": "episode",
                    "source_url": "https://example.test/?content_audio=1&content_sig=abc",
                    "size_bytes": 2000,
                    "duration_sec": 100.0,
                }
            },
        }
    )


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.state_path = os.path.join(self.dir, "state.json")
        self.feed_path = os.path.join(self.dir, "feed.xml")
        self.log_path = os.path.join(self.dir, "run.log")
        patcher = mock.patch.object(fetch_mod, "Transport", OfflineTransport)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self, *extra):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = run_mod.main(
                [
                    "--state",
                    self.state_path,
                    "--feed",
                    self.feed_path,
                    "--log",
                    self.log_path,
                    *extra,
                ]
            )
        return code, stdout.getvalue(), stderr.getvalue()

    def outcome(self, stdout):
        lines = [l for l in stdout.splitlines() if l.startswith("OUTCOME")]
        self.assertEqual(len(lines), 1, stdout)
        return lines[0]

    def test_unreadable_state_exits_two_and_writes_nothing(self):
        write(self.state_path, '{"articles": {oops')
        code, stdout, _ = self.invoke("--dry-run")
        self.assertEqual(code, run_mod.EXIT_UNSTARTABLE)
        self.assertIn("unstartable", stdout)
        self.assertFalse(os.path.exists(self.feed_path))

    def test_unreadable_state_is_logged(self):
        write(self.state_path, "{not json")
        _, _, stderr = self.invoke("--dry-run")
        self.assertIn("cannot read", stderr)

    def test_stale_state_exits_one(self):
        write(self.state_path, state_doc("Thu, 10 Sep 2026 13:54:24 +0000"))
        code, stdout, _ = self.invoke("--dry-run")
        self.assertEqual(code, run_mod.EXIT_ATTENTION)
        self.assertIn("stale=yes", self.outcome(stdout))

    def test_fresh_state_exits_zero(self):
        write(self.state_path, state_doc())
        code, stdout, _ = self.invoke("--dry-run", "--stale-after-days", "365")
        self.assertEqual(code, run_mod.EXIT_OK)
        self.assertIn("stale=no", self.outcome(stdout))

    def test_broken_sentinel_exits_one_even_when_the_feed_is_fresh(self):
        """A takedown is not a staleness problem, and must still exit 1.

        The two alarms are independent: the Feed can be perfectly fresh while
        every published Episode is unplayable. Reading only the freshness
        verdict here would make the sentinel's issue unreachable.
        """
        write(self.state_path, state_doc())
        with mock.patch.object(fetch_mod, "Transport", BrokenEpisodeTransport):
            code, stdout, _ = self.invoke(
                "--dry-run", "--stale-after-days", "365"
            )
        self.assertEqual(code, run_mod.EXIT_ATTENTION)
        line = self.outcome(stdout)
        self.assertIn("stale=no", line)
        self.assertIn("sentinel=broken", line)

    def test_recoverable_sentinel_does_not_exit_one(self):
        """A refresh that works is not news: it must not page a human."""

        class RefreshableTransport(BrokenEpisodeTransport):
            def get_text(self, url):
                if url.rstrip("/").endswith("/feed"):
                    return super().get_text(url)
                return (
                    '<html><script>var MAIVoiceReaderConfig = '
                    '{"initialAudio":{"status":"ready",'
                    '"audio_url":"https://example.test/?content_audio=1&content_sig=fresh",'
                    '"duration_sec":100,"size_bytes":2000}};</script></html>'
                )

        write(self.state_path, state_doc())
        with mock.patch.object(fetch_mod, "Transport", RefreshableTransport):
            code, stdout, _ = self.invoke("--dry-run", "--stale-after-days", "365")
        self.assertEqual(code, run_mod.EXIT_OK)
        self.assertIn("sentinel=refreshed", self.outcome(stdout))

    def test_offline_source_feed_does_not_change_the_episode_count(self):
        """A failed run must not add or drop Episodes."""
        write(self.state_path, state_doc())
        _, stdout, _ = self.invoke("--dry-run", "--stale-after-days", "365")
        line = self.outcome(stdout)
        self.assertIn("episodes_total=1", line)
        self.assertIn("failures=1", line)

    def test_outcome_line_carries_the_verdicts(self):
        write(self.state_path, state_doc())
        _, stdout, _ = self.invoke("--dry-run")
        line = self.outcome(stdout)
        for field in ("stale=", "sentinel=", "failures=", "newest_age="):
            self.assertIn(field, line)

    def test_dry_run_does_not_write_the_feed(self):
        write(self.state_path, state_doc())
        self.invoke("--dry-run")
        self.assertFalse(os.path.exists(self.feed_path))

    def test_dry_run_does_not_write_a_log_file(self):
        write(self.state_path, state_doc())
        self.invoke("--dry-run")
        self.assertFalse(os.path.exists(self.log_path))

    def test_real_run_writes_feed_state_and_log(self):
        write(self.state_path, state_doc())
        code, _, _ = self.invoke("--stale-after-days", "365")
        self.assertEqual(code, run_mod.EXIT_OK)
        self.assertTrue(os.path.exists(self.feed_path))
        self.assertTrue(os.path.exists(self.log_path))

        with open(self.log_path, encoding="utf-8") as handle:
            messages = [json.loads(l)["message"] for l in handle if l.strip()]
        self.assertTrue(any(m.startswith("run start") for m in messages))
        self.assertTrue(any(m.startswith("OUTCOME") for m in messages))

    def test_log_records_are_json_lines(self):
        write(self.state_path, state_doc())
        self.invoke("--stale-after-days", "365")
        with open(self.log_path, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    self.assertIsInstance(json.loads(line), dict)

    def test_stale_run_still_writes_the_feed(self):
        """Stale is a warning, not a reason to stop publishing what we have."""
        write(self.state_path, state_doc("Thu, 10 Sep 2026 13:54:24 +0000"))
        self.invoke()
        self.assertTrue(os.path.exists(self.feed_path))


if __name__ == "__main__":
    unittest.main()
