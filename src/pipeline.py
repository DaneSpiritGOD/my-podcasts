"""The pipeline: Source Feed in, Feed and State out.

One run does three things: work out which Articles still need processing, fetch
those Articles to learn whether they have an AudioAsset, and re-render the Feed
from everything State knows. Nothing is published until the run finishes, so a
crash mid-run leaves State untouched.
"""

import datetime
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import feed as feed_mod
import fetch as fetch_mod
import source_feed as source_feed_mod
import state as state_mod
from state import Entry, State
from voice_reader import parse_voice_reader_config

log = logging.getLogger("pipeline.run")

# Publishing locations. These are the raw URLs subscribers actually fetch.
REPO = "DaneSpiritGOD/my-podcasts"
BRANCH = "main"
RAW_BASE = "https://raw.githubusercontent.com/{}/{}/{}".format(REPO, BRANCH, "")
FEED_URL = RAW_BASE + "feed.xml"
COVER_URL = RAW_BASE + "cover.png"
SITE_URL = "https://commandline.microsoft.com/"


@dataclass
class RunReport:
    """What one run did, for logging and for the failure issue."""

    articles_seen: int = 0
    articles_fetched: int = 0
    new_episodes: int = 0
    no_audio: int = 0
    failures: List[str] = field(default_factory=list)
    episodes_total: int = 0

    @property
    def ok(self) -> bool:
        return not self.failures


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def process_article(transport, article: source_feed_mod.Article) -> Entry:
    """Fetch one Article and record whether it yielded an Episode."""
    entry = Entry(
        guid=article.guid,
        title=article.title,
        link=article.link,
        published=article.published,
        status=state_mod.FAILED,
        author=article.author,
        categories=list(article.categories),
        summary=article.summary,
    )

    try:
        html = fetch_mod.fetch_article(transport, article.link)
    except fetch_mod.FetchError as exc:
        entry.error = exc.reason
        # The URL and the reason are the two things a post-mortem needs, and
        # neither is recoverable from the title alone.
        log.warning(
            "article fetch failed: %s (%s)",
            article.title,
            exc.reason,
            extra={"ctx_guid": article.guid, "ctx_url": article.link},
        )
        return entry

    config = parse_voice_reader_config(html)
    entry.checked_at = _now_iso()

    if config.has_audio:
        entry.status = state_mod.EPISODE
        entry.source_url = config.source_url
        entry.duration_sec = config.duration_sec
        entry.size_bytes = config.size_bytes
        entry.error = None
        log.info(
            "episode: %s (%.1fs, %s bytes)",
            article.title,
            config.duration_sec or 0,
            config.size_bytes,
            extra={"ctx_guid": article.guid},
        )
    else:
        entry.status = state_mod.NO_AUDIO
        entry.error = None
        # Not a problem: many Articles genuinely have no reading. Logged at
        # DEBUG so the file still shows *why* an Article was skipped.
        log.debug(
            "no audio: %s (status=%s)",
            article.title,
            config.status,
            extra={"ctx_guid": article.guid},
        )
    return entry


def run(transport, state: State, report: Optional[RunReport] = None) -> RunReport:
    """Process every Article that still needs it, then refresh the Feed.

    Mutates ``state`` in place; the caller decides whether to persist it.
    """
    report = report or RunReport()
    now = datetime.datetime.now(datetime.timezone.utc)

    try:
        feed_xml = fetch_mod.fetch_source_feed(transport)
    except fetch_mod.FetchError as exc:
        report.failures.append("source feed unavailable: {}".format(exc.reason))
        # Report what State still holds. Leaving this at 0 would make a total
        # outage look like every Episode had been lost, which is exactly the
        # wrong conclusion to reach while reading the log afterwards.
        report.episodes_total = len(state.episodes())
        log.error("source feed unavailable: %s", exc.reason, extra={"ctx_url": exc.url})
        return report

    articles = source_feed_mod.parse_source_feed(feed_xml)
    report.articles_seen = len(articles)
    log.info("source feed: %d article(s)", len(articles))

    if not articles:
        # A feed that parses but lists nothing is almost certainly a layout
        # change, not a blog that stopped publishing. Say so plainly.
        log.warning(
            "source feed parsed but listed no articles; "
            "the feed layout may have changed"
        )

    for article in articles:
        existing = state.get(article.guid)
        if not state_mod.needs_processing(existing):
            log.debug("skipping %s (already %s)", article.title, existing.status)
            continue

        report.articles_fetched += 1
        entry = process_article(transport, article)

        # Keep the original first_seen across reprocessing.
        if existing is not None:
            entry.first_seen = existing.first_seen

        if entry.status == state_mod.EPISODE:
            report.new_episodes += 1
        elif entry.status == state_mod.NO_AUDIO:
            report.no_audio += 1
        else:
            report.failures.append("{}: {}".format(article.title, entry.error))

        state.put(entry)

    report.episodes_total = len(state.episodes())
    return report


def episodes_from_state(state: State) -> List[feed_mod.Episode]:
    """Convert State entries into the Episodes the Feed publishes."""
    episodes = []
    for entry in state.episodes():
        if not entry.source_url or not entry.size_bytes:
            continue
        episodes.append(
            feed_mod.Episode(
                guid=entry.guid,
                title=entry.title,
                link=entry.link,
                published=entry.published,
                author=entry.author,
                categories=list(entry.categories),
                summary=entry.summary,
                source_url=entry.source_url,
                duration_sec=entry.duration_sec,
                size_bytes=entry.size_bytes,
            )
        )
    return episodes


def render(state: State) -> str:
    return feed_mod.render_feed(
        episodes_from_state(state),
        feed_url=FEED_URL,
        cover_url=COVER_URL,
        link_url=SITE_URL,
    )
