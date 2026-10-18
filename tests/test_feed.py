"""Tests for Feed generation."""

import unittest
import xml.etree.ElementTree as ET

from feed import (
    Episode,
    FEED_TITLE,
    format_duration,
    render_feed,
    select_episodes,
)

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"


def episode(**overrides):
    base = dict(
        guid="https://example.test/?p=1",
        title="An Episode",
        link="https://example.test/one/",
        published="Thu, 15 Oct 2026 15:00:22 +0000",
        author="Jane Doe",
        categories=["Deep Dive"],
        summary="A summary.",
        source_url="https://example.test/?content_audio=1&content_sig=abc",
        duration_sec=343.078,
        size_bytes=6863040,
    )
    base.update(overrides)
    return Episode(**base)


def render(episodes, **kwargs):
    options = dict(
        feed_url="https://example.test/feed.xml",
        cover_url="https://example.test/cover.png",
        link_url="https://example.test/",
    )
    options.update(kwargs)
    return render_feed(episodes, **options)


class FeedStructureTests(unittest.TestCase):
    def setUp(self):
        self.xml = render([episode()])
        self.root = ET.fromstring(self.xml)
        self.channel = self.root.find("channel")

    def test_is_well_formed_rss_20(self):
        self.assertEqual(self.root.tag, "rss")
        self.assertEqual(self.root.get("version"), "2.0")

    def test_channel_identity(self):
        self.assertEqual(self.channel.findtext("title"), FEED_TITLE)
        self.assertEqual(self.channel.findtext("language"), "en-us")

    def test_itunes_image_and_category_present(self):
        self.assertEqual(
            self.channel.find("{%s}image" % ITUNES).get("href"),
            "https://example.test/cover.png",
        )
        self.assertEqual(
            self.channel.find("{%s}category" % ITUNES).get("text"), "Technology"
        )

    def test_atom_self_link(self):
        self_link = self.channel.find("{http://www.w3.org/2005/Atom}link")
        self.assertEqual(self_link.get("href"), "https://example.test/feed.xml")
        self.assertEqual(self_link.get("rel"), "self")

    def test_block_and_locked_are_absent(self):
        # ADR-0004: omitting these is deliberate.
        self.assertIsNone(self.channel.find("{%s}block" % ITUNES))
        self.assertNotIn("podcast:locked", self.xml)

    def test_no_podcast_namespace(self):
        self.assertNotIn("podcasting2", self.xml)


class EpisodeRenderingTests(unittest.TestCase):
    def setUp(self):
        self.root = ET.fromstring(render([episode()]))
        self.item = self.root.find("channel/item")

    def test_guid_is_permalink_false(self):
        guid = self.item.find("guid")
        self.assertEqual(guid.get("isPermaLink"), "false")
        self.assertEqual(guid.text, "https://example.test/?p=1")

    def test_enclosure_points_at_source_url(self):
        enclosure = self.item.find("enclosure")
        self.assertEqual(
            enclosure.get("url"),
            "https://example.test/?content_audio=1&content_sig=abc",
        )
        self.assertEqual(enclosure.get("type"), "audio/mpeg")
        self.assertEqual(enclosure.get("length"), "6863040")

    def test_duration_is_rendered(self):
        self.assertEqual(
            self.item.find("{%s}duration" % ITUNES).text, "5:43"
        )

    def test_author_and_summary(self):
        self.assertEqual(self.item.find("{%s}author" % ITUNES).text, "Jane Doe")
        self.assertEqual(self.item.find("description").text, "A summary.")

    def test_categories_are_items(self):
        self.assertEqual(
            [c.text for c in self.item.findall("category")], ["Deep Dive"]
        )

    def test_missing_author_omits_tag(self):
        root = ET.fromstring(render([episode(author=None)]))
        item = root.find("channel/item")
        self.assertIsNone(item.find("{%s}author" % ITUNES))

    def test_missing_duration_omits_tag(self):
        root = ET.fromstring(render([episode(duration_sec=None)]))
        item = root.find("channel/item")
        self.assertIsNone(item.find("{%s}duration" % ITUNES))


class EscapingTests(unittest.TestCase):
    def test_special_characters_survive_round_trip(self):
        tricky = 'A & B <c> "d" \'e\''
        root = ET.fromstring(render([episode(title=tricky, summary=tricky)]))
        item = root.find("channel/item")
        self.assertEqual(item.findtext("title"), tricky)
        self.assertEqual(item.findtext("description"), tricky)

    def test_url_with_ampersand_survives(self):
        root = ET.fromstring(render([episode()]))
        enclosure = root.find("channel/item/enclosure")
        self.assertIn("&content_sig=abc", enclosure.get("url"))


class SelectionTests(unittest.TestCase):
    def test_newest_first(self):
        old = episode(guid="old", published="Thu, 10 Sep 2026 13:54:24 +0000")
        new = episode(guid="new", published="Thu, 15 Oct 2026 15:00:22 +0000")
        self.assertEqual([e.guid for e in select_episodes([old, new])], ["new", "old"])

    def test_limit_keeps_most_recent(self):
        episodes = [
            episode(guid="e%d" % day, published="Thu, %02d Oct 2026 15:00:22 +0000" % day)
            for day in range(1, 11)
        ]
        kept = select_episodes(episodes, limit=3)
        self.assertEqual([e.guid for e in kept], ["e10", "e9", "e8"])

    def test_ordering_is_chronological_not_alphabetical(self):
        # RFC 822 weekday names sort alphabetically, which would put Wednesday
        # before Thursday regardless of the actual date.
        entries = [
            episode(guid="wed", published="Wed, 07 Oct 2026 18:00:00 +0000"),
            episode(guid="thu", published="Thu, 15 Oct 2026 15:00:22 +0000"),
            episode(guid="fri", published="Fri, 02 Oct 2026 16:06:15 +0000"),
        ]
        self.assertEqual(
            [e.guid for e in select_episodes(entries)], ["thu", "wed", "fri"]
        )

    def test_unparseable_date_sorts_last(self):
        entries = [
            episode(guid="bad", published="not a date"),
            episode(guid="good", published="Thu, 15 Oct 2026 15:00:22 +0000"),
        ]
        self.assertEqual([e.guid for e in select_episodes(entries)], ["good", "bad"])

    def test_default_limit_is_fifty(self):
        episodes = [
            episode(guid="e%d" % n, published="Thu, 15 Oct 2026 %02d:00:22 +0000" % (n % 24))
            for n in range(60)
        ]
        self.assertEqual(len(select_episodes(episodes)), 50)


class DurationTests(unittest.TestCase):
    def test_minutes_and_seconds(self):
        self.assertEqual(format_duration(343.078), "5:43")

    def test_hours(self):
        self.assertEqual(format_duration(3661), "1:01:01")

    def test_none_and_zero(self):
        self.assertIsNone(format_duration(None))
        self.assertIsNone(format_duration(0))


class EmptyFeedTests(unittest.TestCase):
    def test_empty_feed_is_still_valid(self):
        root = ET.fromstring(render([]))
        self.assertEqual(root.find("channel").findall("item"), [])
        self.assertIsNone(root.find("channel/lastBuildDate"))


if __name__ == "__main__":
    unittest.main()
