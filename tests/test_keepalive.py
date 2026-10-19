"""Tests for the keepalive stamp.

The stamp exists so GitHub's 60-day inactivity rule cannot silently disable the
schedule. The property that matters is that it fires *rarely enough not to be
noise* and *often enough to be safe*, so both edges are pinned here.
"""

import datetime
import os
import tempfile
import unittest

import keepalive

TODAY = datetime.date(2026, 10, 19)


class ParseTests(unittest.TestCase):
    def test_reads_an_iso_date(self):
        self.assertEqual(keepalive.parse("2026-10-19\n"), datetime.date(2026, 10, 19))

    def test_missing_file_is_none(self):
        self.assertIsNone(keepalive.parse(""))

    def test_garbage_is_none(self):
        self.assertIsNone(keepalive.parse("not a date"))

    def test_render_round_trips(self):
        self.assertEqual(keepalive.parse(keepalive.render(TODAY)), TODAY)

    def test_render_ends_with_a_newline(self):
        self.assertTrue(keepalive.render(TODAY).endswith("\n"))


class ShouldTouchTests(unittest.TestCase):
    def test_missing_stamp_is_touched(self):
        self.assertTrue(keepalive.should_touch("", TODAY))

    def test_unreadable_stamp_is_touched(self):
        self.assertTrue(keepalive.should_touch("garbage", TODAY))

    def test_fresh_stamp_is_left_alone(self):
        """A busy repository must not get an extra commit every run."""
        self.assertFalse(keepalive.should_touch("2026-10-18\n", TODAY))

    def test_stamp_at_the_interval_is_touched(self):
        stamped = (TODAY - datetime.timedelta(days=keepalive.INTERVAL_DAYS)).isoformat()
        self.assertTrue(keepalive.should_touch(stamped + "\n", TODAY))

    def test_stamp_just_before_the_interval_is_left_alone(self):
        stamped = (
            TODAY - datetime.timedelta(days=keepalive.INTERVAL_DAYS - 1)
        ).isoformat()
        self.assertFalse(keepalive.should_touch(stamped + "\n", TODAY))

    def test_interval_leaves_room_before_githubs_limit(self):
        self.assertLess(keepalive.INTERVAL_DAYS, 60)

    def test_a_quiet_year_produces_at_most_nine_commits(self):
        """The whole point is that the safety net is not itself noise."""
        day = TODAY
        stamp = keepalive.render(day)
        touches = 0
        for _ in range(365):
            day += datetime.timedelta(days=1)
            if keepalive.should_touch(stamp, day):
                stamp = keepalive.render(day)
                touches += 1
        self.assertLessEqual(touches, 9)

    def test_no_window_exceeds_githubs_limit(self):
        """Walk three years: the stamp must never be allowed to go 60 days."""
        day = TODAY
        stamp = keepalive.render(day)
        last_touch = day
        for _ in range(365 * 3):
            day += datetime.timedelta(days=1)
            if keepalive.should_touch(stamp, day):
                self.assertLess(
                    (day - last_touch).days,
                    60,
                    "the stamp was left untouched for {} days".format(
                        (day - last_touch).days
                    ),
                )
                stamp = keepalive.render(day)
                last_touch = day


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, keepalive.KEEPALIVE_PATH)

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_a_missing_stamp(self):
        self.assertTrue(keepalive.refresh(self.path, TODAY))
        with open(self.path, encoding="utf-8") as handle:
            self.assertEqual(keepalive.parse(handle.read()), TODAY)

    def test_does_not_rewrite_a_fresh_stamp(self):
        keepalive.refresh(self.path, TODAY)
        before = os.stat(self.path).st_mtime_ns
        self.assertFalse(keepalive.refresh(self.path, TODAY))
        self.assertEqual(os.stat(self.path).st_mtime_ns, before)

    def test_rewrites_a_stale_stamp(self):
        keepalive.refresh(self.path, TODAY - datetime.timedelta(days=50))
        self.assertTrue(keepalive.refresh(self.path, TODAY))
        with open(self.path, encoding="utf-8") as handle:
            self.assertEqual(keepalive.parse(handle.read()), TODAY)


if __name__ == "__main__":
    unittest.main()
