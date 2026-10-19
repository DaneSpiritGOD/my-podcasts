# Commit a keepalive stamp so the schedule cannot die of silence

GitHub disables scheduled workflows in a public repository after 60 days with no repository activity. A podcast pipeline is exactly the wrong shape for that: the source blog publishes 2-4 Articles a week, but it takes breaks, and a month of silence is a normal week scaled up. If the workflow is disabled, the cron simply stops — and the pipeline that would have noticed a stale Feed is the very thing that stopped running, so nothing raises an issue either.

Whether a commit made by the workflow itself counts as activity is undocumented, and relying on an undocumented behaviour is a guess whose failure mode is the silent one above.

The fix is a stamp file, `.keepalive`, refreshed when the run is about to be considered inactive. It is a date, committed to the repository like the Feed and State it protects.

## Consequences

The interval is 45 days, not 60: the margin absorbs a stretch of failed runs and keeps the refresh well inside the window. A busy repository never sees the commit — the stamp only changes when it is about to age out — so the cost falls only on the quiet repository that needs it.

The stamp could be removed by hand and nothing would warn about it: a missing stamp is refreshed on the next run, which is a self-healing default rather than an alarm. The alternative — alerting on the stamp's absence — would add a third alarm condition that only fires about the alarm system itself.
