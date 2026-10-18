# The repository is public

The repo is public. Release assets on a private repo are not anonymously downloadable, and Pages on a private repo requires a paid plan, so a private repo has nowhere to serve audio or a feed from. Since the audio is public regardless — the Source URL needs no auth — a private repo would only hide the code and `state.json`, which are not the sensitive part.

## Consequences

The feed and its history are discoverable, which is accepted: `itunes:block` and `podcast:locked` are deliberately omitted (see ADR-0004), and the feed is kept out of directories by simply not submitting it. Until the cutover to public, `raw.githubusercontent.com` returns 404 for the feed, so subscriber verification cannot be done; that is a known, deliberate deferral, not a bug.
