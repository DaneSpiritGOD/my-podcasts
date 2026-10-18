# Alarm on a stale Feed, not on failed requests

The pipeline can fail in a way that looks exactly like success. If the source site starts refusing us, every Article fails to fetch, State does not change, `feed.xml` is re-rendered byte-identical, and the daily run reports success. The Feed has stopped advancing and nobody knows.

The obvious fix — fail the run on any fetch error — is wrong. A single Article returning 503 is normal and heals on the next run. Alarming on it would make the one alarm that matters indistinguishable from the noise, and an alarm you have learned to ignore is worse than no alarm, because it costs you the habit of looking.

So Freshness ignores *why* a run produced nothing and asks only *how old the newest Episode is*. One threshold, `STALE_AFTER_DAYS = 14`, catches a source site that is down, a signature scheme that changed, a parser that stopped matching, and a Source Feed that silently emptied — all of which are indistinguishable from inside the pipeline and all of which end with the same symptom.

## Consequences

The verdict is stateless: no counter lives in State, so the check cannot be lost by the very failure it is meant to catch. It also cannot distinguish "the blog took a two-week break" from "we are broken", and it will occasionally be wrong in that direction. That is accepted — a false alarm every couple of years costs one issue, and the alternative costs a silently dead podcast.

Fourteen days is about four missed publishing slots for a blog that posts 2-4 times a week: late enough that a quiet fortnight is not treated as an outage, early enough that a real one surfaces inside two weeks. `--stale-after-days` overrides it for a one-off run.

Both alarms exit 1, so the workflow distinguishes them from the OUTCOME line rather than from the exit code. Exit 2 is reserved for a run that could not start at all, which is a different problem and gets a different issue.
