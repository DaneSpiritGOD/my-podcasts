"""Keep the scheduled workflow from being disabled for inactivity.

GitHub disables scheduled workflows in a *public* repository once there has been
no repository activity for 60 days. Whether a commit made by the workflow itself
counts as activity is not documented, so relying on it would be a guess — and
the failure is silent: the cron simply stops, and the pipeline that would have
noticed a stale Feed is the very thing that stopped running.

A stamp file fixes this with a commit of its own. It is touched only when it is
about to age out, so a busy repository never sees an extra commit and a quiet
one still produces roughly one every six weeks.
"""

import datetime
from typing import Optional

KEEPALIVE_PATH = ".keepalive"

# Comfortably inside GitHub's 60-day window: the margin absorbs a stretch of
# failed runs, and the file is refreshed long before the clock would expire.
INTERVAL_DAYS = 45

_LIMIT_DAYS = 60

assert INTERVAL_DAYS < _LIMIT_DAYS, "the interval must leave room before the limit"


def parse(text: str) -> Optional[datetime.date]:
    """Read the stamped date, or None when it is missing or unusable."""
    try:
        return datetime.datetime.strptime((text or "").strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def render(day: datetime.date) -> str:
    return day.strftime("%Y-%m-%d") + "\n"


def should_touch(
    text: str,
    now: Optional[datetime.date] = None,
    interval_days: int = INTERVAL_DAYS,
) -> bool:
    """Whether the stamp needs refreshing.

    A missing or unreadable stamp is refreshed: without a baseline there is no
    way to show the window is still open, and the cost is one commit.
    """
    now = now or datetime.date.today()
    stamped = parse(text)
    if stamped is None:
        return True
    return (now - stamped).days >= interval_days


def refresh(path: str, now: Optional[datetime.date] = None) -> bool:
    """Touch the stamp file if it is due. Returns whether it changed."""
    now = now or datetime.date.today()
    try:
        with open(path, encoding="utf-8") as handle:
            current = handle.read()
    except OSError:
        current = ""

    if not should_touch(current, now):
        return False

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(render(now))
    return True
