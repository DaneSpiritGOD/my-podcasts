"""Tests for the Sentinel."""

import unittest

import sentinel
import state as state_mod
from fetch import FetchError
from state import Entry, State

OLD_URL = "https://example.test/?content_audio=7&content_sig=old"
NEW_URL = "https://example.test/?content_audio=7&content_sig=new"


def episode(source_url=OLD_URL, published="Thu, 10 Sep 2026 13:54:24 +0000"):
    return Entry(
        guid="https://example.test/?p=7",
        title="An Episode",
        link="https://example.test/seven/",
        published=published,
        status=state_mod.EPISODE,
        source_url=source_url,
        size_bytes=2000,
        duration_sec=100.5,
    )


def page(url=NEW_URL):
    return (
        '<html><script>var MAIVoiceReaderConfig = {"initialAudio":'
        '{"status":"ready","audio_url":"' + url + '",'
        '"duration_sec":101,"size_bytes":2001}};</script></html>'
    )


class FakeTransport:
    def __init__(self, status=200, page_html=None, page_error=None):
        self.status = status
        self.page_html = page_html
        self.page_error = page_error

    def probe(self, url):
        return self.status

    def get_text(self, url):
        if self.page_error:
            raise self.page_error
        return self.page_html or ""


class SentinelTests(unittest.TestCase):
    def test_no_episodes_is_ok(self):
        result = sentinel.check(FakeTransport(), State())
        self.assertEqual(result.outcome, sentinel.OK)
        self.assertFalse(result.needs_attention)

    def test_live_url_is_ok(self):
        state = State()
        state.put(episode())
        result = sentinel.check(FakeTransport(status=200), state)
        self.assertEqual(result.outcome, sentinel.OK)
        self.assertFalse(result.needs_attention)

    def test_range_style_206_is_ok(self):
        state = State()
        state.put(episode())
        self.assertEqual(sentinel.check(FakeTransport(status=206), state).outcome, sentinel.OK)

    def test_unreachable_network_is_not_an_issue(self):
        state = State()
        state.put(episode())
        result = sentinel.check(FakeTransport(status=0), state)
        self.assertEqual(result.outcome, sentinel.UNREACHABLE)
        self.assertFalse(result.needs_attention)

    def test_dead_url_is_refreshed_from_article_page(self):
        state = State()
        state.put(episode())
        result = sentinel.check(
            FakeTransport(status=403, page_html=page()), state
        )
        self.assertEqual(result.outcome, sentinel.REFRESHED)
        self.assertFalse(result.needs_attention)
        self.assertEqual(state.get("https://example.test/?p=7").source_url, NEW_URL)
        self.assertEqual(state.get("https://example.test/?p=7").size_bytes, 2001)

    def test_dead_url_with_no_audio_on_page_is_broken(self):
        state = State()
        state.put(episode())
        result = sentinel.check(
            FakeTransport(status=403, page_html="<html>nothing</html>"), state
        )
        self.assertEqual(result.outcome, sentinel.BROKEN)
        self.assertTrue(result.needs_attention)
        self.assertIn("no longer offers audio", result.detail)

    def test_dead_url_and_dead_page_is_broken(self):
        state = State()
        state.put(episode())
        result = sentinel.check(
            FakeTransport(status=403, page_error=FetchError("x", "HTTP 500")), state
        )
        self.assertEqual(result.outcome, sentinel.BROKEN)
        self.assertTrue(result.needs_attention)

    def test_same_url_republished_but_failing_is_broken(self):
        state = State()
        state.put(episode())
        result = sentinel.check(
            FakeTransport(status=403, page_html=page(OLD_URL)), state
        )
        self.assertEqual(result.outcome, sentinel.BROKEN)
        self.assertTrue(result.needs_attention)

    def test_checks_oldest_episode(self):
        state = State()
        state.put(episode(published="Thu, 15 Oct 2026 15:00:22 +0000"))
        older = episode(source_url="https://example.test/?content_audio=1&content_sig=z")
        older.guid = "https://example.test/?p=1"
        older.published = "Thu, 10 Sep 2026 13:54:24 +0000"
        state.put(older)

        result = sentinel.check(FakeTransport(status=200), state)
        self.assertEqual(result.guid, "https://example.test/?p=1")

    def test_oldest_is_chronological_not_alphabetical(self):
        """RFC 822 strings sort by weekday name, which picks the wrong Episode.

        "Fri, 02 Oct" sorts before "Thu, 10 Sep" as a string, so a naive
        min() checks the October Episode and never looks at the September one.
        """
        state = State()
        september = episode(published="Thu, 10 Sep 2026 13:54:24 +0000")
        september.guid = "https://example.test/?p=september"
        october = episode(published="Fri, 02 Oct 2026 16:05:10 +0000")
        october.guid = "https://example.test/?p=october"
        state.put(september)
        state.put(october)

        result = sentinel.check(FakeTransport(status=200), state)
        self.assertEqual(result.guid, "https://example.test/?p=september")

    def test_oldest_respects_time_zone_offsets(self):
        state = State()
        later_utc = episode(published="Fri, 02 Oct 2026 00:30:00 +0000")
        later_utc.guid = "https://example.test/?p=later"
        earlier_elsewhere = episode(published="Fri, 02 Oct 2026 02:00:00 +0800")
        earlier_elsewhere.guid = "https://example.test/?p=earlier"
        state.put(later_utc)
        state.put(earlier_elsewhere)

        result = sentinel.check(FakeTransport(status=200), state)
        self.assertEqual(result.guid, "https://example.test/?p=earlier")


class RefreshAllTests(unittest.TestCase):
    def test_refreshes_every_episode(self):
        state = State()
        state.put(episode())
        changed = sentinel.refresh_all(FakeTransport(page_html=page()), state)
        self.assertEqual(changed, 1)
        self.assertEqual(state.get("https://example.test/?p=7").source_url, NEW_URL)

    def test_unchanged_url_is_not_counted(self):
        state = State()
        state.put(episode())
        changed = sentinel.refresh_all(FakeTransport(page_html=page(OLD_URL)), state)
        self.assertEqual(changed, 0)

    def test_fetch_failure_is_skipped(self):
        state = State()
        state.put(episode())
        changed = sentinel.refresh_all(
            FakeTransport(page_error=FetchError("x", "boom")), state
        )
        self.assertEqual(changed, 0)
        self.assertEqual(state.get("https://example.test/?p=7").source_url, OLD_URL)


if __name__ == "__main__":
    unittest.main()
