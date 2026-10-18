"""Extraction of the Voice Reader Config from a source Article page.

The source site server-renders a JSON blob named ``MAIVoiceReaderConfig`` on
every Article page. When an Article has a TTS reading, that blob carries the
Source URL together with its duration and size; when it does not, the blob is
either absent or reports a non-ready status.

Everything here is a pure function of the page HTML so it can be tested without
network access.
"""

import json
import re
from dataclasses import dataclass
from typing import Optional

# The config is emitted as ``var MAIVoiceReaderConfig = {...};`` inside a
# <script> tag. The object is a single line, but tolerate whitespace anyway.
_CONFIG_RE = re.compile(
    r"MAIVoiceReaderConfig\s*=\s*(\{.*?\})\s*;\s*$",
    re.MULTILINE | re.DOTALL,
)

# Fallback: the whole script body, when the trailing semicolon layout differs.
_LOOSE_CONFIG_RE = re.compile(
    r"MAIVoiceReaderConfig\s*=\s*(\{)",
)

READY_STATUS = "ready"


@dataclass(frozen=True)
class VoiceReaderConfig:
    """What an Article page says about its AudioAsset."""

    status: str
    source_url: Optional[str]
    duration_sec: Optional[float]
    size_bytes: Optional[int]

    @property
    def has_audio(self) -> bool:
        return (
            self.status == READY_STATUS
            and bool(self.source_url)
            and bool(self.size_bytes)
        )


def _extract_json_object(html: str, start: int) -> Optional[str]:
    """Return the balanced ``{...}`` object beginning at ``start``.

    Brace counting is quote-aware so braces inside strings do not unbalance the
    scan. Returns None if the object never closes.
    """
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(html)):
        ch = html[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return html[start : i + 1]
    return None


def find_config_json(html: str) -> Optional[str]:
    """Locate the raw JSON text of the Voice Reader Config, if present."""
    match = _CONFIG_RE.search(html)
    if match:
        return match.group(1)

    loose = _LOOSE_CONFIG_RE.search(html)
    if loose:
        return _extract_json_object(html, loose.start(1))
    return None


def parse_voice_reader_config(html: str) -> VoiceReaderConfig:
    """Parse the Voice Reader Config out of an Article page.

    An Article with no player panel, no config, or unparseable JSON is reported
    as ``status="absent"`` with no AudioAsset — this is an ordinary outcome, not
    an error.
    """
    raw = find_config_json(html)
    if raw is None:
        return VoiceReaderConfig("absent", None, None, None)

    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return VoiceReaderConfig("absent", None, None, None)

    initial = data.get("initialAudio") if isinstance(data, dict) else None
    if not isinstance(initial, dict):
        return VoiceReaderConfig("absent", None, None, None)

    status = str(initial.get("status") or "absent")
    url = initial.get("audio_url") or None

    duration = initial.get("duration_sec")
    try:
        duration = float(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration = None

    size = initial.get("size_bytes")
    try:
        size = int(size) if size is not None else None
    except (TypeError, ValueError):
        size = None

    return VoiceReaderConfig(status, url if isinstance(url, str) else None, duration, size)
