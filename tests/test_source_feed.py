"""Tests for Source Feed parsing."""

import unittest

from source_feed import Article, parse_date, parse_source_feed, strip_html

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:content="http://purl.org/rss/1.0/modules/content/"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel>
  <title>Command Line</title>
  <item>
    <title>First &amp; Foremost</title>
    <link>https://example.test/first/</link>
    <guid isPermaLink="false">https://example.test/?p=1</guid>
    <pubDate>Thu, 15 Oct 2026 15:00:22 +0000</pubDate>
    <dc:creator><![CDATA[Jane Doe]]></dc:creator>
    <category><![CDATA[Deep Dive]]></category>
    <category>Open Source</category>
    <description><![CDATA[<p>A short <b>summary</b>.</p>]]></description>
  </item>
  <item>
    <title>No Author</title>
    <link>https://example.test/second/</link>
    <guid>https://example.test/?p=2</guid>
    <pubDate>Tue, 13 Oct 2026 16:03:25 +0000</pubDate>
    <description><![CDATA[<p>Second.</p>]]></description>
  </item>
  <item>
    <title>Missing guid</title>
    <link>https://example.test/third/</link>
    <pubDate>Tue, 13 Oct 2026 16:03:25 +0000</pubDate>
  </item>
  <item>
    <title>Missing link</title>
    <guid>https://example.test/?p=4</guid>
    <pubDate>Tue, 13 Oct 2026 16:03:25 +0000</pubDate>
  </item>
</channel>
</rss>
"""


class ParseSourceFeedTests(unittest.TestCase):
    def setUp(self):
        self.articles = parse_source_feed(FEED)

    def test_skips_items_without_guid_or_link(self):
        self.assertEqual(len(self.articles), 2)
        self.assertEqual(
            [a.title for a in self.articles], ["First & Foremost", "No Author"]
        )

    def test_extracts_metadata(self):
        first = self.articles[0]
        self.assertEqual(first.guid, "https://example.test/?p=1")
        self.assertEqual(first.link, "https://example.test/first/")
        self.assertEqual(first.author, "Jane Doe")
        self.assertEqual(first.categories, ["Deep Dive", "Open Source"])

    def test_summary_is_plain_text(self):
        self.assertEqual(self.articles[0].summary, "A short summary .")

    def test_missing_author_is_none(self):
        self.assertIsNone(self.articles[1].author)
        self.assertEqual(self.articles[1].categories, [])

    def test_dates_are_normalised_to_rfc822(self):
        self.assertEqual(
            self.articles[0].published, "Thu, 15 Oct 2026 15:00:22 +0000"
        )

    def test_channel_without_items(self):
        self.assertEqual(parse_source_feed("<rss><channel></channel></rss>"), [])

    def test_not_a_feed_returns_empty(self):
        self.assertEqual(parse_source_feed("<rss></rss>"), [])


class HelperTests(unittest.TestCase):
    def test_strip_html_unescapes_and_collapses(self):
        self.assertEqual(strip_html("<p>a &amp; b</p>\n<i>c</i>"), "a & b c")

    def test_strip_html_handles_empty(self):
        self.assertEqual(strip_html(""), "")

    def test_parse_date_preserves_offset(self):
        self.assertEqual(
            parse_date("Thu, 15 Oct 2026 23:00:22 +0800"),
            "Thu, 15 Oct 2026 15:00:22 +0000",
        )

    def test_parse_date_keeps_unparseable_input(self):
        self.assertEqual(parse_date("not a date"), "not a date")

    def test_parse_date_handles_empty(self):
        self.assertEqual(parse_date(""), "")


if __name__ == "__main__":
    unittest.main()
