# my-podcasts

Turns posts from the [Command Line](https://commandline.microsoft.com/) blog into a podcast feed, so its built-in "Listen to article" readings can be followed in a podcast app.

## How it works

```
Actions (daily 01:00 UTC)
  → read the Source Feed, compare against State
  → fetch each new Article, read its Voice Reader Config
  → record the outcome: Episode, no audio, or failed
  → run the Sentinel against the oldest published Episode
  → run Freshness against the newest published Episode
  → rewrite feed.xml + state.json → commit back to main
  → upload the Run Log, raise an issue if a human is needed
  → subscribers fetch feed.xml from its raw URL
```

The audio itself is never copied. Each Episode's `enclosure` points straight at the Source URL the Article publishes, which is stable for the life of that audio — see [ADR-0001](docs/adr/0001-publish-source-url-as-enclosure.md). The Sentinel exists because that makes every Episode depend on the source site continuing to honour those URLs.

Freshness exists because a pipeline can fail while reporting success: if the source site stops answering, nothing changes, `feed.xml` is re-rendered identically, and the run looks healthy every day. It asks only how old the newest Episode is, and raises an issue once that passes 14 days — see [ADR-0005](docs/adr/0005-alarm-on-a-stale-feed.md).

## Subscribing

The feed is `https://raw.githubusercontent.com/DaneSpiritGOD/my-podcasts/main/feed.xml`.

Add it by URL: in Apple Podcasts on iOS, **Library → ⋯ → Follow a Show by URL**; on macOS, **File → Follow a Show by URL**.

The repo is public and the feed is not submitted to any directory, so it is not discoverable through search — see [ADR-0002](docs/adr/0002-repository-is-public.md) and [ADR-0004](docs/adr/0004-omit-block-and-locked-tags.md).

## License

The **code** in this repository is MIT — see [LICENSE](LICENSE).

That does not extend to the content it aggregates. Article text, titles and the TTS audio are Microsoft's, are served by `commandline.microsoft.com`, and remain under whatever terms that site sets. This project does not copy the audio; `feed.xml` only links to it. `feed.xml` and `state.json` are generated output containing that third-party metadata, not part of the licensed work.

If you fork this to point at a different blog, that blog's terms apply to your output.

## Running it locally

No dependencies beyond Python 3.12. The version is pinned in `.python-version`,
which the workflow reads, so CI and a local run use the same interpreter.

```sh
python3 src/run.py            # refresh state.json and feed.xml
python3 src/run.py --dry-run  # report without writing
python3 src/run.py -v         # log at DEBUG
python3 src/run.py --refresh-all      # re-read every Episode page for new Source URLs
python3 src/run.py --stale-after-days 30  # override the Freshness threshold
```

Exit codes are the workflow's whole vocabulary:

| Code | Meaning |
| --- | --- |
| `0` | healthy |
| `1` | a human is needed — the Sentinel found broken Episodes, or the Feed is stale |
| `2` | the run could not start — State is unreadable, so nothing was written |

A transient fetch failure on one Article is not a failure code: it is retried tomorrow by design.

### Reading a run afterwards

Two ways in, and they are the same events.

**In the browser.** Every run's log is captured by Actions and kept for 90 days (the cap on a public repo). Open the run, and the **Refresh feed** summary at the top already shows the `OUTCOME` line plus the last 40 log lines, so the usual question — "did yesterday work?" — is answered without downloading anything. The full log is one click away, and the whole run can be downloaded as a zip.

**Locally.** A run also writes `run.log` next to the Feed: the same events as JSON lines, which is much easier to query than prose. It is git-ignored and not uploaded; it exists for `jq` and for debugging on your own machine.

```sh
grep OUTCOME run.log | tail -5          # one line per run: stale/sentinel/failures
jq -r 'select(.level=="WARNING") | .ts + " " + .message' run.log
```

The console log is the canonical one, so anything worth knowing after the fact is in the message itself, not only in a JSON field. Context such as the failing `guid` and `url` is appended in brackets:

```
2026-10-19T03:12:01Z WARNING pipeline.run: article fetch failed: PyRIT (HTTP 503) [guid=... url=...]
```

Retention is the reason there is no archive step: 90 days of daily runs is a quarter of history, and if a problem survived 90 days it was already visible in `feed.xml`, which is committed forever.

## Tests

```sh
./test
```

## Layout

| Path | What it is |
| --- | --- |
| `src/voice_reader.py` | Extracts the Voice Reader Config from an Article page |
| `src/source_feed.py` | Parses the Source Feed into Articles |
| `src/feed.py` | Renders the Feed |
| `src/state.py` | The State record and its retry rules |
| `src/pipeline.py` | Wires the above together |
| `src/sentinel.py` | Detects and recovers broken Source URLs |
| `src/freshness.py` | Detects a Feed that has stopped advancing |
| `src/logs.py` | The Run Log: JSON lines on disk, readable text on stderr |
| `src/fetch.py` | The HTTP transport, and the scheme/host allowlist |
| `src/keepalive.py` | Refreshes the `.keepalive` stamp that keeps the schedule alive |
| `src/run.py` | CLI entry point used by the workflow |
| `assets/` | Cover art sources (official vector logo + mark) |

Vocabulary is defined in [GLOSSARY.md](GLOSSARY.md); decisions are in [docs/adr/](docs/adr/).
