# Serve the feed from raw.githubusercontent.com

The feed is committed to the repo and served from its `raw.githubusercontent.com` URL, rather than through GitHub Pages. This removes the Pages build entirely — and with it the `GITHUB_TOKEN` problem, where a commit made by a workflow does not trigger a Pages rebuild, leaving the branch updated but the site stale. It also keeps the feed's history in `main`, which is the point: every Episode's arrival is a reviewable commit.

## Consequences

Raw serves `.xml` as `text/plain; charset=utf-8` rather than an XML media type. Podcast clients are tolerant of this in practice, and the largest comparable project (Olshansk/rss-feeds) distributes its feeds exactly this way, but no vendor guarantees it. HEAD and Range requests both work. Raw serves `.png` with a correct `image/png`, so the cover is unaffected.
