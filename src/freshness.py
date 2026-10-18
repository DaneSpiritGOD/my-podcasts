"""Is the Feed still advancing?

The Sentinel asks whether *published* Episodes still play. It says nothing
about whether the pipeline is still producing new ones. If the source site
starts refusing us, every Article fails to fetch, State does not change,
feed.xml is rewritten byte-identical, and the workflow reports success every
day. Nobody finds out until a listener notices the show has gone quiet.

So Freshness ignores *why* a run failed and looks only at the result: how old
is the newest Episode? That one question covers a source site that is down, a
signature scheme that changed, a parser that stopped matching, and a Source
Feed that silently emptied — all of which are indistinguishable from inside the
pipeline, and all of which end with the same symptom.

Deliberately stateless: no counter lives in State, so a Freshness verdict
cannot itself be lost by the failure it is meant to catch.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import feed as feed_mod
from state import State

# The source blog publishes roughly 2-4 Articles a week, but it does take
# breaks. Fourteen days is about four missed publishing slots: late enough that
# a quiet fortnight is not treated as an outage, early enough that a real one
# surfaces inside two weeks.
STALE_AFTER_DAYS = 14


@dataclass(frozen=True)
class Freshness:
    """How old the newest Episode is, and whether that is too old."""

    stale: bool
    newest_published: Optional[str] = None
    newest_title: Optional[str] = None
    age_days: Optional[float] = None
    detail: str = ""

    @property
    def needs_attention(self) -> bool:
        return self.stale

    def summary(self) -> str:
        if self.age_days is None:
            return "unknown"
        return "{:.1f}d".format(self.age_days)


def check(
    state: State,
    now=None,
    threshold_days: float = STALE_AFTER_DAYS,
) -> Freshness:
    """Report whether the newest Episode is older than ``threshold_days``.

    A State with no Episodes is not stale: there is nothing to compare against,
    and a first run is indistinguishable from a pipeline that has never
    succeeded. The Sentinels of the world cannot help here; that case is caught
    by the run itself failing loudly.
    """
    now = now or datetime.now(timezone.utc)
    episodes = state.episodes()
    if not episodes:
        return Freshness(False, detail="no Episodes published yet")

    newest = max(episodes, key=lambda e: feed_mod.published_datetime(e.published))
    published_at = feed_mod.published_datetime(newest.published)

    if published_at == feed_mod.EPOCH:
        return Freshness(
            True,
            newest.published,
            newest.title,
            None,
            "newest Episode has no parseable publication date",
        )

    age_days = (now - published_at).total_seconds() / 86400.0
    if age_days > threshold_days:
        return Freshness(
            True,
            newest.published,
            newest.title,
            age_days,
            "newest Episode is {:.1f} days old (threshold {:.0f})".format(
                age_days, threshold_days
            ),
        )

    return Freshness(
        False,
        newest.published,
        newest.title,
        age_days,
        "newest Episode is {:.1f} days old".format(age_days),
    )
