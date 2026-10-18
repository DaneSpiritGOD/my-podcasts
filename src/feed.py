"""Generation of the podcast Feed.

The Feed is RSS 2.0 with the iTunes namespace, which is what podcast clients
expect. It is a pure function of the Episode records so it can be tested
without network access.
"""

import datetime
import email.utils
import html
from dataclasses import dataclass
from typing import List, Optional

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM_NS = "http://www.w3.org/2005/Atom"

# Feed-level identity. Changing any of these is visible to subscribers and some
# clients cache them, so they are deliberately constants rather than config.
FEED_TITLE = "Command Line"
FEED_DESCRIPTION = "By builders, for builders. Audio readings of posts from the Microsoft Command Line blog."
FEED_AUTHOR = "Microsoft Command Line"
FEED_LANGUAGE = "en-us"
FEED_CATEGORY = "Technology"
FEED_EXPLICIT = "no"
FEED_TYPE = "episodic"

MAX_EPISODES = 50


@dataclass(frozen=True)
class Episode:
    """An Article that has audio, ready to be published."""

    guid: str
    title: str
    link: str
    published: str
    author: Optional[str]
    categories: List[str]
    summary: str
    source_url: str
    duration_sec: Optional[float]
    size_bytes: int


def escape(value: str) -> str:
    """Escape text for inclusion in XML character data or an attribute."""
    return html.escape(value or "", quote=True)


def format_duration(seconds: Optional[float]) -> Optional[str]:
    """Render a duration the way `itunes:duration` expects: H:MM:SS or M:SS."""
    if not seconds or seconds <= 0:
        return None
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return "{}:{:02d}:{:02d}".format(hours, minutes, secs)
    return "{}:{:02d}".format(minutes, secs)


EPOCH = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


def published_datetime(published: str) -> datetime.datetime:
    """Parse an RFC 822 date into an aware datetime, or EPOCH if it is unusable.

    RFC 822 dates must never be compared as strings: the weekday name sorts
    alphabetically, which puts Wednesday before Thursday regardless of date.
    """
    try:
        parsed = email.utils.parsedate_to_datetime(published or "")
    except (TypeError, ValueError):
        return EPOCH
    if parsed is None:
        return EPOCH
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _sort_key(episode: "Episode"):
    """Order Episodes chronologically."""
    return published_datetime(episode.published)


def select_episodes(episodes: List[Episode], limit: int = MAX_EPISODES) -> List[Episode]:
    """Keep the most recent Episodes, newest first.

    Feed size is capped so the document stays small; Episodes that fall out of
    the window are still remembered in State and never reprocessed.
    """
    ordered = sorted(episodes, key=_sort_key, reverse=True)
    return ordered[:limit]


def _render_episode(episode: Episode) -> str:
    parts = [
        "    <item>",
        "      <title>{}</title>".format(escape(episode.title)),
        "      <link>{}</link>".format(escape(episode.link)),
        '      <guid isPermaLink="false">{}</guid>'.format(escape(episode.guid)),
        "      <pubDate>{}</pubDate>".format(escape(episode.published)),
    ]

    if episode.author:
        parts.append(
            "      <itunes:author>{}</itunes:author>".format(escape(episode.author))
        )

    for category in episode.categories:
        parts.append(
            '      <category>{}</category>'.format(escape(category))
        )

    parts.append(
        "      <description>{}</description>".format(escape(episode.summary))
    )
    parts.append(
        "      <itunes:summary>{}</itunes:summary>".format(escape(episode.summary))
    )
    parts.append('      <itunes:explicit>{}</itunes:explicit>'.format(FEED_EXPLICIT))

    duration = format_duration(episode.duration_sec)
    if duration:
        parts.append(
            "      <itunes:duration>{}</itunes:duration>".format(duration)
        )

    parts.append(
        '      <enclosure url="{}" length="{}" type="audio/mpeg" />'.format(
            escape(episode.source_url), episode.size_bytes
        )
    )
    parts.append("    </item>")
    return "\n".join(parts)


def render_feed(
    episodes: List[Episode],
    *,
    feed_url: str,
    cover_url: str,
    link_url: str,
    limit: int = MAX_EPISODES,
) -> str:
    """Render the complete Feed document."""
    selected = select_episodes(episodes, limit)
    last_build = selected[0].published if selected else ""

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:itunes="{}" xmlns:atom="{}">'.format(
            ITUNES_NS, ATOM_NS
        ),
        "  <channel>",
        "    <title>{}</title>".format(escape(FEED_TITLE)),
        "    <link>{}</link>".format(escape(link_url)),
        "    <description>{}</description>".format(escape(FEED_DESCRIPTION)),
        "    <language>{}</language>".format(FEED_LANGUAGE),
        "    <itunes:author>{}</itunes:author>".format(escape(FEED_AUTHOR)),
        "    <itunes:summary>{}</itunes:summary>".format(escape(FEED_DESCRIPTION)),
        "    <itunes:type>{}</itunes:type>".format(FEED_TYPE),
        "    <itunes:explicit>{}</itunes:explicit>".format(FEED_EXPLICIT),
        '    <itunes:category text="{}" />'.format(escape(FEED_CATEGORY)),
        '    <itunes:image href="{}" />'.format(escape(cover_url)),
        "    <image>",
        "      <url>{}</url>".format(escape(cover_url)),
        "      <title>{}</title>".format(escape(FEED_TITLE)),
        "      <link>{}</link>".format(escape(link_url)),
        "    </image>",
        '    <atom:link href="{}" rel="self" type="application/rss+xml" />'.format(
            escape(feed_url)
        ),
    ]

    if last_build:
        lines.append("    <lastBuildDate>{}</lastBuildDate>".format(escape(last_build)))

    lines.extend(_render_episode(episode) for episode in selected)
    lines.append("  </channel>")
    lines.append("</rss>")
    return "\n".join(lines) + "\n"
