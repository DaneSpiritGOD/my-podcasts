# Publish the source URL as the enclosure; do not rehost audio

The AudioAsset is served from a signed Source URL on the source site. We put that URL straight into `enclosure` instead of downloading the MP3 into Releases or object storage. The signature is derived from the audio id and a server-side secret, so the same Article always yields the same URL; it is not time-limited. Rehosting would add storage, bandwidth, a cleanup policy and a download step for no benefit, since the audio is public either way.

## Consequences

Playback traffic goes to the source site, so the source operator sees subscriber behaviour, and a key rotation or a takedown silently breaks every published Episode. The Sentinel exists to make that failure loud rather than silent: it re-checks the oldest published Source URL every run, refreshes signatures from the Article page when they still exist, and opens an issue only when they no longer do.
