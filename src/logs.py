"""Logging for the pipeline.

One event stream, two renderings:

* **stderr** is the canonical one. GitHub Actions captures it as the run log,
  which is readable in the UI, downloadable as a zip, and kept for 90 days on a
  public repository. Anything worth knowing after the fact must therefore be in
  the *message*, not only in a structured field.
* **The run log file** is the same stream as JSON lines, for `jq` and for local
  runs. It is ignored by git; the workflow does not upload it, because the
  Actions log already is the durable record.

Every record is timestamped in UTC, because the workflow runs on UTC and the
maintainer reads it from UTC+8: a log line that does not say which zone it is in
is the single most common way a post-mortem goes wrong.

Secrets never reach a log line: this project has none, and the Source URL is
already public in feed.xml.
"""

import json
import logging
import os
import sys

LOG = logging.getLogger("pipeline")

# Kept short so a run log fits comfortably in a terminal and in a pasted issue
# comment.
_FORMAT = "%(asctime)sZ %(levelname)-7s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"

# Third-party loggers that would otherwise be noisy at DEBUG.
_NOISY = ("urllib3",)


def context_suffix(record: logging.LogRecord) -> str:
    """Render the ``ctx_*`` extras as a trailing `` [k=v k=v]``.

    The console is the canonical log, so context that only exists as a JSON
    field would be invisible in the Actions UI. Appending it keeps the message
    line readable while making the guid and URL visible where people look.
    """
    parts = []
    for key, value in sorted(record.__dict__.items()):
        if key.startswith("ctx_") and value is not None:
            parts.append("{}={}".format(key[4:], value))
    return " [{}]".format(" ".join(parts)) if parts else ""


class ConsoleFormatter(logging.Formatter):
    """Human-readable, with structured context appended to the message."""

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        return rendered + context_suffix(record)


class JsonLineFormatter(logging.Formatter):
    """Render each record as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, _DATEFMT) + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # ``extra=`` fields are carried through, so a caller can attach the
        # Article guid or the URL that failed without parsing the message.
        for key, value in record.__dict__.items():
            if key.startswith("ctx_") and value is not None:
                payload[key[4:]] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def configure(verbose: bool = False, log_path: str = "") -> None:
    """Attach handlers to the ``pipeline`` logger tree.

    Idempotent: calling it twice (a test, or run.py imported then invoked) does
    not duplicate output.
    """
    LOG.setLevel(logging.DEBUG)
    LOG.propagate = False

    for handler in list(LOG.handlers):
        LOG.removeHandler(handler)
        handler.close()

    stream = logging.StreamHandler(sys.stderr)
    stream.setLevel(logging.DEBUG if verbose else logging.INFO)
    stream.setFormatter(ConsoleFormatter(_FORMAT, _DATEFMT))
    LOG.addHandler(stream)

    if log_path:
        directory = os.path.dirname(os.path.abspath(log_path))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        # The file keeps DEBUG even when the console is quiet: it is the copy
        # you grep locally, where `jq` beats eyeballs.
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JsonLineFormatter())
        LOG.addHandler(file_handler)

    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)


def read(path: str) -> str:
    """Return the run log, or a note explaining why there is none."""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        return "(no run log: {})".format(exc)
