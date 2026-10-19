# my-podcasts

A personal podcast feed for the [Microsoft Command Line](https://commandline.microsoft.com/) blog.

The blog embeds a "Listen to article" TTS reading in every post, but offers no podcast feed of its own. This repo builds one: a GitHub Action checks the blog daily, collects the audio for new posts, and publishes a standard RSS feed you can follow in any podcast app.

**Feed URL:**

```
https://raw.githubusercontent.com/DaneSpiritGOD/my-podcasts/main/feed.xml
```

Subscribe by URL — in Apple Podcasts on iOS: **Library → ⋯ → Follow a Show by URL**; on macOS: **File → Follow a Show by URL**.

The feed is not submitted to any podcast directory, so it is only reachable by this link.

## How it works

```
GitHub Actions (daily at 01:00 UTC)
  → read the blog's RSS feed, compare against state.json
  → for each new post, extract its audio URL, duration and size
  → append new Episodes to feed.xml, commit back to main
  → raise a GitHub issue if something needs a human
```

Design notes, for the curious:

- **Audio is never copied.** Each `enclosure` links directly to the audio URL the blog itself serves, so the repo holds no media and pays no bandwidth. A daily check recovers the links if the site ever rotates them ([ADR-0001](docs/adr/0001-publish-source-url-as-enclosure.md)).
- **Self-healing.** A post that fails to fetch today is retried tomorrow; a transient outage delays an Episode but never loses it.
- **Alarms, not silence.** Broken audio links and a feed that has stopped advancing both open a GitHub issue automatically ([ADR-0005](docs/adr/0005-alarm-on-a-stale-feed.md)).
- **Kept alive.** A committed stamp file ensures GitHub's 60-day inactivity rule can never silently disable the schedule ([ADR-0006](docs/adr/0006-commit-a-keepalive-stamp.md)).

Further decisions are recorded in [docs/adr/](docs/adr/); project vocabulary in [GLOSSARY.md](GLOSSARY.md).

## Running locally

Requires Python 3.12 (pinned in [`.python-version`](.python-version)); no other dependencies.

```sh
python3 src/run.py             # refresh feed.xml and state.json
python3 src/run.py --dry-run   # report what would change, write nothing
python3 src/run.py --refresh-all  # re-check every Episode's audio link
```

Exit codes: `0` healthy · `1` needs a human · `2` could not start.

Run the tests with:

```sh
./test
```

## Repository layout

| Path | Purpose |
| --- | --- |
| `feed.xml` | The published podcast feed |
| `state.json` | Record of every post processed, and its outcome |
| `src/` | The pipeline (extraction, feed rendering, alarms, keepalive) |
| `tests/` | Test suite — run with `./test` |
| `assets/` | Cover art sources |
| `.github/workflows/` | The daily refresh workflow |

## License

The code is [MIT](LICENSE). Aggregated content — titles, summaries and the TTS audio — belongs to Microsoft and remains under that site's terms; this repo links to the audio but does not host it.
