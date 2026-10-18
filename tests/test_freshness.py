"""Tests for the freshness check.

Freshness deliberately ignores *why* a run produced nothing and looks only at
how old the newest Episode is, because that is the one symptom every failure
mode shares.
"""

import datetime
import unittest

import freshness
import state as state_mod
from state import Entry, State

NOW = datetime.datetime(2026, 10, 18, 12, 0, 0, tzinfo=datetime.timezone.utc)


def episode(published, guid="https://example.test/?p=1"):
    return Entry(
        guid=guid,
        title="An Episode",
        link="https://example.test/one/",
        published=published,
        status=state_mod.EPISODE,
        source_url="https://example.test/?content_audio=1&content_sig=abc",
        size_bytes=2000,
    )


class FreshnessTests(unittest.TestCase):
    def test_empty_state_is_not_stale(self):
        """A first run has nothing to be stale against."""
        result = freshness.check(State(), NOW)
        self.assertFalse(result.stale)
        self.assertFalse(result.needs_attention)

    def test_recent_episode_is_fresh(self):
        state = State()
        state.put(episode("Thu, 15 Oct 2026 15:00:22 +0000"))
        result = freshness.check(state, NOW)
        self.assertFalse(result.stale)
        # 15 Oct 15:00:22 to 18 Oct 12:00:00 is 2 days 20:59:38.
        self.assertAlmostEqual(result.age_days, 2.87, places=2)

    def test_old_episode_is_stale(self):
        state = State()
        state.put(episode("Thu, 10 Sep 2026 13:54:24 +0000"))
        result = freshness.check(state, NOW)
        self.assertTrue(result.stale)
        self.assertTrue(result.needs_attention)

    def test_threshold_is_exclusive(self):
        state = State()
        # Exactly 14 days old: not yet stale.
        state.put(episode("Sun, 04 Oct 2026 12:00:00 +0000"))
        self.assertFalse(freshness.check(state, NOW).stale)

    def test_threshold_is_configurable(self):
        state = State()
        state.put(episode("Thu, 15 Oct 2026 15:00:22 +0000"))
        self.assertTrue(freshness.check(state, NOW, threshold_days=1).stale)

    def test_newest_episode_is_the_one_measured(self):
        """A stale old Episode must not mask a fresh new one."""
        state = State()
        state.put(episode("Thu, 10 Sep 2026 13:54:24 +0000", guid="old"))
        state.put(episode("Thu, 15 Oct 2026 15:00:22 +0000", guid="new"))
        result = freshness.check(state, NOW)
        self.assertFalse(result.stale)
        self.assertEqual(result.newest_title, "An Episode")

    def test_comparison_is_chronological_not_alphabetical(self):
        """Same trap as the Sentinel: "Fri" sorts before "Thu" as a string."""
        state = State()
        state.put(episode("Fri, 02 Oct 2026 16:05:10 +0000", guid="october"))
        state.put(episode("Thu, 15 Oct 2026 15:00:22 +0000", guid="mid-october"))
        result = freshness.check(state, NOW)
        self.assertEqual(result.newest_published, "Thu, 15 Oct 2026 15:00:22 +0000")

    def test_no_audio_entries_do_not_count(self):
        state = State()
        state.put(episode("Thu, 15 Oct 2026 15:00:22 +0000"))
        state.put(
            Entry(
                guid="noise",
                title="No Audio",
                link="l",
                published="Thu, 01 Jan 2026 00:00:00 +0000",
                status=state_mod.NO_AUDIO,
            )
        )
        self.assertFalse(freshness.check(state, NOW).stale)

    def test_unparseable_date_is_stale(self):
        """An Episode we cannot date is not evidence that the Feed is advancing."""
        state = State()
        state.put(episode("not a date"))
        result = freshness.check(state, NOW)
        self.assertTrue(result.stale)
        self.assertIn("parseable", result.detail)

    def test_summary_is_human_readable(self):
        state = State()
        state.put(episode("Thu, 15 Oct 2026 15:00:22 +0000"))
        self.assertEqual(freshness.check(state, NOW).summary(), "2.9d")

    def test_summary_without_a_date_is_unknown(self):
        self.assertEqual(freshness.Freshness(True).summary(), "unknown")


if __name__ == "__main__":
    unittest.main()
