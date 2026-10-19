#!/usr/bin/env python3
"""Entry point for the daily run.

Reads State from disk, processes whatever Articles still need it, checks that
the Feed is still advancing, then writes the Feed and State back.

Exit codes are the workflow's whole vocabulary, so they are deliberate:

  0  healthy
  1  needs a human: the Sentinel found broken Episodes, or the Feed has gone
     stale
  2  the run could not even start: State is unreadable, so nothing was written
     and nothing was published

A transient fetch failure on one Article is not a failure code: it is retried
tomorrow by design, and treating it as an error would train the maintainer to
ignore the alarm that matters.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import freshness as freshness_mod
import fetch as fetch_mod
import keepalive as keepalive_mod
import logs
import pipeline
import sentinel as sentinel_mod
import state as state_mod

DEFAULT_STATE = "state.json"
DEFAULT_FEED = "feed.xml"
DEFAULT_LOG = "run.log"
DEFAULT_KEEPALIVE = keepalive_mod.KEEPALIVE_PATH

EXIT_OK = 0
EXIT_ATTENTION = 1
EXIT_UNSTARTABLE = 2

log = logs.LOG


def read(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def write(path, text):
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def outcome_line(report, sentinel_result, fresh) -> str:
    """One machine-readable line summarising the run.

    The workflow greps this to decide what to do and to title the issue, so it
    is written last and in a fixed order.
    """
    return (
        "OUTCOME stale={stale} sentinel={sentinel} failures={failures} "
        "articles_seen={articles_seen} fetched={articles_fetched} "
        "new_episodes={new_episodes} no_audio={no_audio} "
        "episodes_total={episodes_total} newest_age={age}"
    ).format(
        stale="yes" if fresh.stale else "no",
        sentinel=sentinel_result.outcome,
        failures=len(report.failures),
        age=fresh.summary(),
        articles_seen=report.articles_seen,
        articles_fetched=report.articles_fetched,
        new_episodes=report.new_episodes,
        no_audio=report.no_audio,
        episodes_total=report.episodes_total,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Refresh the podcast Feed.")
    parser.add_argument("--state", default=DEFAULT_STATE)
    parser.add_argument("--feed", default=DEFAULT_FEED)
    parser.add_argument(
        "--keepalive",
        default=DEFAULT_KEEPALIVE,
        help="stamp file that keeps the schedule alive (empty to disable)",
    )
    parser.add_argument(
        "--log",
        default=DEFAULT_LOG,
        help="write a JSON-lines run log here (empty to disable)",
    )
    parser.add_argument(
        "--refresh-all",
        action="store_true",
        help="re-read every Episode's Article page to pick up new Source URLs",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing files",
    )
    parser.add_argument(
        "--stale-after-days",
        type=float,
        default=freshness_mod.STALE_AFTER_DAYS,
        help="report the Feed as stale when the newest Episode is older than this",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log at DEBUG")
    args = parser.parse_args(argv)

    # Configure logging first so that even a State failure leaves a record.
    logs.configure(verbose=args.verbose, log_path="" if args.dry_run else args.log)
    log.info(
        "run start state=%s feed=%s dry_run=%s", args.state, args.feed, args.dry_run
    )

    try:
        state = state_mod.State.from_json(read(args.state))
    except state_mod.StateError as exc:
        # Never fall back to an empty State here: that would rebuild the Feed
        # from nothing and overwrite the file we just failed to read.
        log.error("cannot read %s: %s", args.state, exc)
        print("OUTCOME unstartable state=unreadable", file=sys.stdout)
        return EXIT_UNSTARTABLE

    log.info(
        "state loaded: %d article(s), %d episode(s)",
        len(state.articles),
        len(state.episodes()),
    )

    transport = fetch_mod.Transport()
    report = pipeline.run(transport, state)

    for failure in report.failures:
        log.warning("failure: %s", failure)

    sentinel_result = sentinel_mod.check(transport, state)
    log.info(
        "sentinel: %s (%s)", sentinel_result.outcome, sentinel_result.detail
    )

    if args.refresh_all:
        changed = sentinel_mod.refresh_all(transport, state)
        log.info("refreshed %d Source URL(s)", changed)

    fresh = freshness_mod.check(state, threshold_days=args.stale_after_days)
    if fresh.stale:
        log.warning(
            "stale feed: %s; newest Episode was %r published %s",
            fresh.detail,
            fresh.newest_title,
            fresh.newest_published,
        )
    else:
        log.info("freshness: %s", fresh.detail)

    feed_xml = pipeline.render(state)

    if args.dry_run:
        log.info("dry run: not writing files")
    else:
        write(args.state, state.to_json())
        write(args.feed, feed_xml)
        log.info("wrote %s and %s", args.state, args.feed)

        # GitHub disables scheduled workflows in a public repository after 60
        # days without activity, and whether this workflow's own commits count
        # is undocumented. The stamp removes the guess: it is refreshed only
        # when it is about to age out, so a quiet repository still gets a commit
        # roughly every six weeks and a busy one gets none.
        if args.keepalive:
            if keepalive_mod.refresh(args.keepalive):
                log.info("refreshed keepalive stamp %s", args.keepalive)
            else:
                log.info("keepalive stamp %s is current", args.keepalive)

    summary = outcome_line(report, sentinel_result, fresh)
    log.info(summary)
    # Also on stdout so it is greppable without the log file.
    print(summary)

    # The two alarms are independent. A fresh Feed can still have every
    # published Episode unplayable (a takedown), so both verdicts have to be
    # consulted; reading only freshness would make the sentinel's issue
    # unreachable.
    if sentinel_result.needs_attention or fresh.needs_attention:
        return EXIT_ATTENTION
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
