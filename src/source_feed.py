"""Parsing of the source blog's RSS feed into Article records.

The Source Feed is an input only: it tells us which Articles exist and carries
the metadata we republish (title, author, categories, summary, publication
date). It never carries the TTS audio, so an Article must still be fetched to
learn whether it has an AudioAsset.
"""

import datetime
import email.utils
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional

NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Article:
    """A post on the source blog, as described by the Source Feed."""

    guid: str
    title: str
    link: str
    published: str
    author: Optional[str]
    categories: List[str]
    summary: str


def _text(node: Optional[ET.Element]) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def strip_html(value: str) -> str:
    """Reduce an HTML fragment to plain text on a single line."""
    text = _TAG_RE.sub(" ", value or "")
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def parse_date(value: str) -> str:
    """Normalise an RFC 822 date to UTC RFC 822.

    Returns the input unchanged when it cannot be parsed, so a malformed date on
    one Article never fails the whole run.
    """
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return value
    if parsed is None:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return email.utils.format_datetime(parsed.astimezone(datetime.timezone.utc))


def parse_source_feed(xml_text: str) -> List[Article]:
    """Parse the Source Feed into Articles, newest first as the feed lists them.

    Articles without a usable guid or link are skipped: both are required to
    identify the Article later.
    """
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []

    articles: List[Article] = []
    for item in channel.findall("item"):
        guid = _text(item.find("guid"))
        link = _text(item.find("link"))
        if not guid or not link:
            continue

        categories = [
            (c.text or "").strip()
            for c in item.findall("category")
            if (c.text or "").strip()
        ]

        summary = strip_html(_text(item.find("description")))
        if not summary:
            summary = strip_html(_text(item.find("content:encoded", NS)))

        articles.append(
            Article(
                guid=guid,
                title=_text(item.find("title")),
                link=link,
                published=parse_date(_text(item.find("pubDate"))),
                author=_text(item.find("dc:creator", NS)) or None,
                categories=categories,
                summary=summary,
            )
        )
    return articles
