"""The State record: which Articles have been processed, and with what outcome.

State exists so the pipeline can tell "never seen" from "seen, no audio" from
"seen, failed". Only ``failed`` is retried; ``no_audio`` is terminal once its
recheck window has passed, because retrying an Article that has no audio just
wastes requests every day.
"""

import datetime
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


class StateError(Exception):
    """The State document exists but cannot be trusted.

    Raised rather than falling back to an empty State: an empty State makes the
    pipeline believe nothing has ever been processed, so it would refetch every
    Article and rewrite the Feed from scratch. That silent reset is worse than
    stopping, because it looks exactly like a normal run.
    """

EPISODE = "episode"
NO_AUDIO = "no_audio"
FAILED = "failed"

# An Article can gain audio shortly after publication (TTS generation lags the
# post), so a no_audio verdict is rechecked for this many days before becoming
# terminal. See Q26.
NO_AUDIO_RECHECK_DAYS = 7


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Entry:
    """One Article's processing outcome."""

    guid: str
    title: str
    link: str
    published: str
    status: str
    first_seen: str = field(default_factory=_now_iso)
    checked_at: str = field(default_factory=_now_iso)
    source_url: Optional[str] = None
    duration_sec: Optional[float] = None
    size_bytes: Optional[int] = None
    author: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    summary: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict) -> "Entry":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class State:
    """The whole State document."""

    articles: Dict[str, Entry] = field(default_factory=dict)
    version: int = 1

    def get(self, guid: str) -> Optional[Entry]:
        return self.articles.get(guid)

    def put(self, entry: Entry) -> None:
        self.articles[guid_key(entry.guid)] = entry

    def episodes(self) -> List[Entry]:
        return [e for e in self.articles.values() if e.status == EPISODE]

    def to_json(self) -> str:
        payload = {
            "version": self.version,
            "articles": {
                key: entry.to_dict()
                for key, entry in sorted(self.articles.items())
            },
        }
        return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "State":
        """Parse the State document.

        An empty document is a legitimate first run. Anything else that fails to
        parse is an error: ``text`` came from a file we wrote ourselves, so a
        malformed document means a bad merge, a truncated write or a manual edit,
        and continuing would silently rebuild the Feed as if nothing had ever
        been processed.
        """
        if not text or not text.strip():
            return cls()
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise StateError("State is not valid JSON: {}".format(exc))

        if not isinstance(data, dict):
            raise StateError(
                "State must be a JSON object, got {}".format(type(data).__name__)
            )

        raw_articles = data.get("articles")
        if raw_articles is None:
            raw_articles = {}
        if not isinstance(raw_articles, dict):
            raise StateError(
                "State 'articles' must be an object, got {}".format(
                    type(raw_articles).__name__
                )
            )

        articles = {}
        for key, raw in raw_articles.items():
            if not isinstance(raw, dict):
                log.warning(
                    "Skipping State entry %r: expected an object, got %s",
                    key,
                    type(raw).__name__,
                )
                continue
            try:
                articles[key] = Entry.from_dict(raw)
            except TypeError as exc:
                log.warning("Skipping State entry %r: %s", key, exc)
                continue

        try:
            version = int(data.get("version", 1))
        except (TypeError, ValueError):
            log.warning(
                "State 'version' is not an integer (%r); assuming 1", data.get("version")
            )
            version = 1

        return cls(articles=articles, version=version)


def guid_key(guid: str) -> str:
    """Normalise a guid for use as a State key."""
    return (guid or "").strip()


def _days_since(iso_timestamp: str, now: Optional[datetime.datetime] = None) -> float:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    try:
        then = datetime.datetime.strptime(iso_timestamp, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return float("inf")
    then = then.replace(tzinfo=datetime.timezone.utc)
    return (now - then).total_seconds() / 86400.0


def needs_processing(
    entry: Optional[Entry],
    now: Optional[datetime.datetime] = None,
) -> bool:
    """Whether an Article should be fetched again.

    Unknown Articles always need processing. Failed ones are retried. A
    no_audio verdict is rechecked while it is fresh, then left alone.
    """
    if entry is None:
        return True
    if entry.status == EPISODE:
        return False
    if entry.status == FAILED:
        return True
    if entry.status == NO_AUDIO:
        return _days_since(entry.checked_at, now) < NO_AUDIO_RECHECK_DAYS
    return True
