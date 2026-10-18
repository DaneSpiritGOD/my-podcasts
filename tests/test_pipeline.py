"""Tests for the pipeline, using a fake transport."""

import datetime
import json
import unittest

import pipeline
import state as state_mod
from fetch import FetchError
from state import Entry, State

READY_CONFIG = (
    '{"initialAudio":{"status":"ready",'
    '"audio_url":"https://example.test/?content_audio=7&content_sig=sig",'
    '"duration_sec":100.5,"size_bytes":2000}}'
)

NO_AUDIO_PAGE = "<html><body>no player here</body></html>"


def page_with_audio():
    return (
        "<html><script>\nvar MAIVoiceReaderConfig = " + READY_CONFIG + ";\n</script></html>"
    )


def source_feed(*items):
    entries = []
    for index, (title, link) in enumerate(items, start=1):
        entries.append(
            "<item><title>{}</title><link>{}</link>"
            '<guid isPermaLink="false">https://example.test/?p={}</guid>'
            "<pubDate>Thu, 15 Oct 2026 15:00:22 +0000</pubDate>"
            "<dc:creator>Author {}</dc:creator>"
            "<category>Deep Dive</category>"
            "<description><![CDATA[<p>Summary {}</p>]]></description></item>".format(
                title, link, index, index, index
            )
        )
    return (
        '<?xml version="1.0"?><rss version="2.0" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<channel><title>Command Line</title>{}</channel></rss>".format("".join(entries))
    )


class FakeTransport:
    def __init__(self, feed_xml="", pages=None, feed_error=None):
        self.feed_xml = feed_xml
        self.pages = pages or {}
        self.feed_error = feed_error
        self.requested = []

    def get_text(self, url):
        self.requested.append(url)
        if url == pipeline.fetch_mod.SOURCE_FEED_URL:
            if self.feed_error:
                raise FetchError(url, self.feed_error)
            return self.feed_xml
        page = self.pages.get(url)
        if page is None:
            raise FetchError(url, "HTTP 404", status=404)
        if isinstance(page, Exception):
            raise page
        return page

    def probe(self, url):
        return 200


class RunTests(unittest.TestCase):
    def test_article_with_audio_becomes_episode(self):
        transport = FakeTransport(
            source_feed(("One", "https://example.test/one/")),
            {"https://example.test/one/": page_with_audio()},
        )
        state = State()
        report = pipeline.run(transport, state)

        self.assertEqual(report.new_episodes, 1)
        self.assertTrue(report.ok)
        entry = state.get("https://example.test/?p=1")
        self.assertEqual(entry.status, state_mod.EPISODE)
        self.assertEqual(entry.size_bytes, 2000)
        self.assertEqual(entry.duration_sec, 100.5)
        self.assertEqual(entry.author, "Author 1")
        self.assertEqual(entry.categories, ["Deep Dive"])

    def test_article_without_audio_is_recorded_as_no_audio(self):
        transport = FakeTransport(
            source_feed(("One", "https://example.test/one/")),
            {"https://example.test/one/": NO_AUDIO_PAGE},
        )
        state = State()
        report = pipeline.run(transport, state)

        self.assertEqual(report.no_audio, 1)
        self.assertEqual(report.new_episodes, 0)
        self.assertEqual(state.get("https://example.test/?p=1").status, state_mod.NO_AUDIO)

    def test_fetch_failure_is_recorded_and_reported(self):
        transport = FakeTransport(
            source_feed(("One", "https://example.test/one/")),
            {"https://example.test/one/": FetchError("x", "HTTP 503", status=503)},
        )
        state = State()
        report = pipeline.run(transport, state)

        self.assertFalse(report.ok)
        self.assertEqual(len(report.failures), 1)
        entry = state.get("https://example.test/?p=1")
        self.assertEqual(entry.status, state_mod.FAILED)
        self.assertEqual(entry.error, "HTTP 503")

    def test_processed_articles_are_not_refetched(self):
        transport = FakeTransport(
            source_feed(("One", "https://example.test/one/")),
            {"https://example.test/one/": page_with_audio()},
        )
        state = State()
        pipeline.run(transport, state)
        transport.requested.clear()

        report = pipeline.run(transport, state)
        # Only the Source Feed is refetched; the Article is already an Episode.
        self.assertEqual(transport.requested, [pipeline.fetch_mod.SOURCE_FEED_URL])
        self.assertEqual(report.articles_fetched, 0)

    def test_first_seen_is_preserved_across_retries(self):
        transport = FakeTransport(
            source_feed(("One", "https://example.test/one/")),
            {"https://example.test/one/": FetchError("x", "HTTP 503", status=503)},
        )
        state = State()
        pipeline.run(transport, state)
        original = state.get("https://example.test/?p=1").first_seen

        transport.pages["https://example.test/one/"] = page_with_audio()
        pipeline.run(transport, state)
        self.assertEqual(state.get("https://example.test/?p=1").first_seen, original)

    def test_source_feed_failure_aborts_without_touching_state(self):
        transport = FakeTransport(feed_error="HTTP 403")
        state = State()
        report = pipeline.run(transport, state)

        self.assertFalse(report.ok)
        self.assertEqual(state.articles, {})
        self.assertIn("source feed unavailable", report.failures[0])

    def test_multiple_articles_mixed_outcomes(self):
        transport = FakeTransport(
            source_feed(
                ("One", "https://example.test/one/"),
                ("Two", "https://example.test/two/"),
                ("Three", "https://example.test/three/"),
            ),
            {
                "https://example.test/one/": page_with_audio(),
                "https://example.test/two/": NO_AUDIO_PAGE,
                "https://example.test/three/": FetchError("x", "HTTP 500", status=500),
            },
        )
        state = State()
        report = pipeline.run(transport, state)

        self.assertEqual(report.articles_seen, 3)
        self.assertEqual(report.new_episodes, 1)
        self.assertEqual(report.no_audio, 1)
        self.assertEqual(len(report.failures), 1)


class RenderTests(unittest.TestCase):
    def _state_with_episode(self):
        state = State()
        state.put(
            Entry(
                guid="https://example.test/?p=1",
                title="One",
                link="https://example.test/one/",
                published="Thu, 15 Oct 2026 15:00:22 +0000",
                status=state_mod.EPISODE,
                source_url="https://example.test/?content_audio=7&content_sig=sig",
                duration_sec=100.5,
                size_bytes=2000,
                author="Author",
                categories=["Deep Dive"],
                summary="Summary",
            )
        )
        return state

    def test_render_uses_raw_urls(self):
        xml = pipeline.render(self._state_with_episode())
        self.assertIn(pipeline.FEED_URL, xml)
        self.assertIn(pipeline.COVER_URL, xml)
        self.assertIn("https://raw.githubusercontent.com/DaneSpiritGOD/my-podcasts/main/", xml)

    def test_render_includes_episode_enclosure(self):
        xml = pipeline.render(self._state_with_episode())
        self.assertIn('type="audio/mpeg"', xml)
        self.assertIn("content_sig=sig", xml)

    def test_episode_without_source_url_is_skipped(self):
        state = State()
        state.put(
            Entry(
                guid="g",
                title="t",
                link="l",
                published="p",
                status=state_mod.EPISODE,
                source_url=None,
                size_bytes=None,
            )
        )
        self.assertNotIn("<item>", pipeline.render(state))

    def test_render_is_well_formed_with_no_episodes(self):
        xml = pipeline.render(State())
        import xml.etree.ElementTree as ET

        root = ET.fromstring(xml)
        self.assertEqual(root.findall("channel/item"), [])


if __name__ == "__main__":
    unittest.main()
