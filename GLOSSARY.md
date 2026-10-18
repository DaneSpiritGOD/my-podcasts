# my-podcasts

Turns the Command Line blog (commandline.microsoft.com) into a personal podcast feed that can be followed in a podcast app.

## Language

**Article**:
A post on the source blog. Articles exist whether or not they have audio.
_Avoid_: post, item, entry

**Episode**:
An Article that has audio, and therefore appears in the feed. An Article without audio never becomes an Episode.
_Avoid_: item, track

**AudioAsset**:
The TTS reading of an Article, identified by its size in bytes and duration in seconds.
_Avoid_: MP3, enclosure, file

**Source URL**:
The signed address an AudioAsset is served from: `?content_audio=<id>&content_sig=<sig>`. The signature is deterministic rather than time-limited — the same Article always yields the same Source URL, and a tampered or missing signature is rejected.
_Avoid_: MP3 link, download link, CDN URL

**Voice Reader Config**:
The server-rendered `MAIVoiceReaderConfig` JSON on an Article page. It is the single source of truth for an Article's AudioAsset — it carries the signed URL, `duration_sec`, and `size_bytes`.
_Avoid_: audio tag, player, embed

**Feed**:
The RSS document our subscribers actually fetch. It is public and anonymously readable by design.
_Avoid_: podcast feed, RSS output

**Source Feed**:
The blog's own `/feed/`, which lists the 10 most recent Articles. It is an input to the pipeline, never something we serve.
_Avoid_: upstream feed, original RSS

**State**:
The record of which Articles have been processed and with what outcome, including Articles that turned out to have no audio.
_Avoid_: cache, database, index

**Backfill**:
Processing Articles published before the pipeline first ran. Backfill is bounded; it is not "everything ever published".
_Avoid_: history, import

**Sentinel**:
The daily check that the oldest published Source URL still resolves. A failure means the signature scheme changed, not that one Episode is broken.
_Avoid_: health check, monitor, ping

**Freshness**:
The daily check that the Feed is still advancing: how old is the newest Episode? It ignores why a run failed, because every failure mode ends with the same symptom.
_Avoid_: staleness, liveness, heartbeat

**Run Log**:
The record of one run: stderr, which Actions captures and keeps for 90 days, plus the same events as JSON lines in `run.log`. It is what a post-mortem reads after the fact, when re-running the failed day is no longer an option.
_Avoid_: output, trace, debug log

