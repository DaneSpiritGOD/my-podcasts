"""Tests for State management."""

import datetime
import json
import unittest

from state import (
    EPISODE,
    FAILED,
    NO_AUDIO,
    Entry,
    State,
    StateError,
    needs_processing,
)

NOW = datetime.datetime(2026, 10, 18, 12, 0, 0, tzinfo=datetime.timezone.utc)


def entry(status, checked_at="2026-10-18T11:00:00Z", **kwargs):
    return Entry(
        guid="https://example.test/?p=1",
        title="T",
        link="https://example.test/one/",
        published="Thu, 15 Oct 2026 15:00:22 +0000",
        status=status,
        checked_at=checked_at,
        **kwargs
    )


class NeedsProcessingTests(unittest.TestCase):
    def test_unknown_article_needs_processing(self):
        self.assertTrue(needs_processing(None))

    def test_episode_is_never_reprocessed(self):
        self.assertFalse(needs_processing(entry(EPISODE)))

    def test_failed_is_retried(self):
        self.assertTrue(needs_processing(entry(FAILED)))

    def test_no_audio_is_never_rechecked(self):
        """A no_audio verdict is terminal on first sight.

        Audio is not added to a published Article later, so rechecking one is
        pure cost: it refetches the same page every run and rewrites State, so
        the pipeline commits a no-op that contains nothing but a timestamp.
        """
        just_seen = entry(
            NO_AUDIO,
            first_seen="2026-10-18T11:59:00Z",
            checked_at="2026-10-18T11:59:00Z",
        )
        self.assertFalse(needs_processing(just_seen))

    def test_no_audio_stays_terminal_over_many_days(self):
        """Daily runs must never pick the same no_audio Article up again."""
        first_seen = "2026-10-10T11:00:00Z"
        verdicts = []
        for day in range(10):
            now = datetime.datetime(
                2026, 10, 10, 11, 0, 0, tzinfo=datetime.timezone.utc
            ) + datetime.timedelta(days=day)
            candidate = Entry(
                guid="g",
                title="T",
                link="https://example.test/one/",
                published="Thu, 15 Oct 2026 15:00:22 +0000",
                status=NO_AUDIO,
                first_seen=first_seen,
                checked_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            verdicts.append(needs_processing(candidate))
        self.assertEqual(verdicts, [False] * 10)

    def test_unknown_status_needs_processing(self):
        self.assertTrue(needs_processing(entry("mystery")))

    def test_unparseable_first_seen_is_terminal_for_no_audio(self):
        """An unreadable anchor means the window cannot be shown to be open.

        Treating it as open would refetch forever, so the safe reading is that
        the verdict has stood long enough.
        """
        bad = entry(NO_AUDIO, first_seen="garbage")
        self.assertFalse(needs_processing(bad))


class SerialisationTests(unittest.TestCase):
    def test_round_trip_preserves_entries(self):
        state = State()
        state.put(entry(EPISODE, source_url="https://x.test/a", size_bytes=10))
        restored = State.from_json(state.to_json())
        self.assertEqual(len(restored.articles), 1)
        got = restored.get("https://example.test/?p=1")
        self.assertEqual(got.status, EPISODE)
        self.assertEqual(got.size_bytes, 10)

    def test_none_fields_are_omitted(self):
        state = State()
        state.put(entry(NO_AUDIO))
        payload = json.loads(state.to_json())
        raw = payload["articles"]["https://example.test/?p=1"]
        self.assertNotIn("source_url", raw)
        self.assertNotIn("error", raw)

    def test_empty_state_is_empty_document(self):
        state = State.from_json("")
        self.assertEqual(state.articles, {})

    def test_whitespace_only_is_empty_document(self):
        self.assertEqual(State.from_json("  \n\t ").articles, {})

    def test_corrupt_json_is_an_error_not_an_empty_state(self):
        """A corrupt State must stop the run, not silently reset it.

        Resetting makes the pipeline believe nothing was ever processed, so it
        refetches every Article and rewrites the Feed — indistinguishable from a
        normal run, and it discards the record of which Articles had no audio.
        """
        with self.assertRaises(StateError):
            State.from_json("{not json")

    def test_truncated_json_is_an_error(self):
        with self.assertRaises(StateError):
            State.from_json('{"version":1,"articles":{"a":{"guid"')

    def test_non_object_document_is_an_error(self):
        with self.assertRaises(StateError):
            State.from_json("[]")

    def test_non_object_articles_is_an_error(self):
        with self.assertRaises(StateError):
            State.from_json('{"articles": []}')

    def test_non_object_entry_is_skipped_with_a_warning(self):
        """One bad entry is logged and dropped; the rest of the State survives."""
        payload = json.dumps(
            {
                "version": 1,
                "articles": {
                    "bad": "oops",
                    "null": None,
                    "good": {
                        "guid": "good",
                        "title": "t",
                        "link": "l",
                        "published": "p",
                        "status": EPISODE,
                    },
                },
            }
        )
        with self.assertLogs("state", level="WARNING") as logs:
            state = State.from_json(payload)
        self.assertEqual(list(state.articles), ["good"])
        self.assertEqual(len(logs.records), 2)

    def test_non_integer_version_falls_back_to_one(self):
        with self.assertLogs("state", level="WARNING"):
            state = State.from_json('{"version": "one", "articles": {}}')
        self.assertEqual(state.version, 1)

    def test_unknown_fields_are_ignored(self):
        payload = json.dumps(
            {
                "version": 1,
                "articles": {
                    "g": {
                        "guid": "g",
                        "title": "t",
                        "link": "l",
                        "published": "p",
                        "status": EPISODE,
                        "future_field": "x",
                    }
                },
            }
        )
        state = State.from_json(payload)
        self.assertEqual(state.get("g").status, EPISODE)

    def test_malformed_entry_is_skipped_not_fatal(self):
        payload = json.dumps(
            {
                "version": 1,
                "articles": {
                    "bad": {"guid": "bad"},
                    "good": {
                        "guid": "good",
                        "title": "t",
                        "link": "l",
                        "published": "p",
                        "status": EPISODE,
                    },
                },
            }
        )
        state = State.from_json(payload)
        self.assertEqual(list(state.articles), ["good"])

    def test_output_is_deterministically_ordered(self):
        state = State()
        for guid in ["c", "a", "b"]:
            state.put(
                Entry(guid=guid, title="t", link="l", published="p", status=EPISODE)
            )
        text = state.to_json()
        self.assertLess(text.index('"a"'), text.index('"b"'))
        self.assertLess(text.index('"b"'), text.index('"c"'))

    def test_serialisation_is_stable_across_calls(self):
        state = State()
        state.put(entry(EPISODE))
        self.assertEqual(state.to_json(), state.to_json())

    def test_episodes_filter(self):
        state = State()
        state.put(entry(EPISODE))
        state.put(Entry(guid="n", title="t", link="l", published="p", status=NO_AUDIO))
        self.assertEqual([e.guid for e in state.episodes()], ["https://example.test/?p=1"])


if __name__ == "__main__":
    unittest.main()
