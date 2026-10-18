"""The Sentinel: keeps published Source URLs from silently dying.

Because Episodes are published by pointing at the source site rather than at
copies we hold, a change on that side can break every published Episode at
once. The Sentinel checks the oldest published Episode each run and reacts in
two stages:

1. Re-fetch the Article page and pick up a fresh Source URL. This handles the
   recoverable case — the signature changed but the audio is still there.
2. If the audio is genuinely gone, report it so a human is told.

Only stage 2 warrants an issue: a refresh that works is not news.
"""

from dataclasses import dataclass
from typing import Optional

import feed as feed_mod
import fetch as fetch_mod
import state as state_mod
from state import State
from voice_reader import parse_voice_reader_config

OK = "ok"
REFRESHED = "refreshed"
BROKEN = "broken"
UNREACHABLE = "unreachable"


@dataclass
class SentinelResult:
    outcome: str
    guid: Optional[str] = None
    title: Optional[str] = None
    detail: str = ""

    @property
    def needs_attention(self) -> bool:
        return self.outcome == BROKEN


def check(transport, state: State) -> SentinelResult:
    """Verify the oldest published Episode still resolves.

    A missing or empty State is not a failure: there is nothing published yet.
    """
    episodes = state.episodes()
    if not episodes:
        return SentinelResult(OK, detail="no Episodes published yet")

    oldest = min(episodes, key=lambda e: feed_mod.published_datetime(e.published))
    status = transport.probe(oldest.source_url or "")

    if status in (0,):
        return SentinelResult(
            UNREACHABLE, oldest.guid, oldest.title, "could not reach the source site"
        )

    if status < 400:
        return SentinelResult(OK, oldest.guid, oldest.title, "HTTP {}".format(status))

    # The published URL is dead. Try to recover a fresh one from the page.
    try:
        html = fetch_mod.fetch_article(transport, oldest.link)
    except fetch_mod.FetchError as exc:
        return SentinelResult(
            BROKEN,
            oldest.guid,
            oldest.title,
            "Source URL returned HTTP {} and the Article page is unavailable ({})".format(
                status, exc.reason
            ),
        )

    config = parse_voice_reader_config(html)
    if not config.has_audio:
        return SentinelResult(
            BROKEN,
            oldest.guid,
            oldest.title,
            "Source URL returned HTTP {} and the Article page no longer offers audio".format(
                status
            ),
        )

    if config.source_url == oldest.source_url:
        return SentinelResult(
            BROKEN,
            oldest.guid,
            oldest.title,
            "Source URL returned HTTP {} although the Article page still publishes it".format(
                status
            ),
        )

    oldest.source_url = config.source_url
    if config.size_bytes:
        oldest.size_bytes = config.size_bytes
    if config.duration_sec:
        oldest.duration_sec = config.duration_sec
    state.put(oldest)

    return SentinelResult(
        REFRESHED,
        oldest.guid,
        oldest.title,
        "recovered a fresh Source URL from the Article page",
    )


def refresh_all(transport, state: State) -> int:
    """Refresh Source URLs for every Episode, e.g. after a known key rotation.

    Returns the number of Episodes whose Source URL changed. Episodes whose
    page no longer offers audio are left untouched and reported by the caller's
    run log.
    """
    changed = 0
    for entry in state.episodes():
        try:
            html = fetch_mod.fetch_article(transport, entry.link)
        except fetch_mod.FetchError:
            continue
        config = parse_voice_reader_config(html)
        if config.has_audio and config.source_url != entry.source_url:
            entry.source_url = config.source_url
            if config.size_bytes:
                entry.size_bytes = config.size_bytes
            if config.duration_sec:
                entry.duration_sec = config.duration_sec
            state.put(entry)
            changed += 1
    return changed
