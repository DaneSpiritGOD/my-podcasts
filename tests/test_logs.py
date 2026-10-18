"""Tests for the run log.

The log is what a post-mortem reads after the fact, when re-running the failed
day is no longer an option. These tests pin the properties that make it usable:
one JSON object per line, UTC timestamps, and context fields carried through.
"""

import json
import logging
import os
import tempfile
import unittest

import logs


class JsonLineFormatterTests(unittest.TestCase):
    def record(self, message="hello", **extra):
        return logging.LogRecord(
            name="pipeline.run",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg=message,
            args=(),
            exc_info=None,
        )

    def test_one_json_object_per_line(self):
        formatter = logs.JsonLineFormatter()
        record = self.record()
        for key, value in {"ctx_guid": "g", "ctx_url": "https://x.test/"}.items():
            setattr(record, key, value)
        line = formatter.format(record)
        payload = json.loads(line)
        self.assertEqual(payload["message"], "hello")
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["logger"], "pipeline.run")

    def test_timestamp_is_utc_marked(self):
        formatter = logs.JsonLineFormatter()
        payload = json.loads(formatter.format(self.record()))
        self.assertTrue(payload["ts"].endswith("Z"))

    def test_context_fields_are_promoted(self):
        formatter = logs.JsonLineFormatter()
        record = self.record()
        record.ctx_guid = "https://example.test/?p=7"
        record.ctx_url = "https://example.test/seven/"
        payload = json.loads(formatter.format(record))
        self.assertEqual(payload["guid"], "https://example.test/?p=7")
        self.assertEqual(payload["url"], "https://example.test/seven/")

    def test_absent_context_is_omitted(self):
        formatter = logs.JsonLineFormatter()
        payload = json.loads(formatter.format(self.record()))
        self.assertNotIn("guid", payload)


class ConsoleFormatterTests(unittest.TestCase):
    """The console is the canonical log: it becomes the Actions run log."""

    def record(self):
        return logging.LogRecord(
            name="pipeline.run",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="article fetch failed: PyRIT (HTTP 503)",
            args=(),
            exc_info=None,
        )

    def test_context_is_visible_on_the_console(self):
        record = self.record()
        record.ctx_guid = "https://example.test/?p=327"
        line = logs.ConsoleFormatter(logs._FORMAT, logs._DATEFMT).format(record)
        self.assertIn("guid=https://example.test/?p=327", line)

    def test_context_does_not_break_the_human_format(self):
        record = self.record()
        record.ctx_url = "https://example.test/one/"
        line = logs.ConsoleFormatter(logs._FORMAT, logs._DATEFMT).format(record)
        self.assertIn("WARNING pipeline.run: article fetch failed", line)
        self.assertTrue(line.endswith("]"))

    def test_no_context_means_no_brackets(self):
        line = logs.ConsoleFormatter(logs._FORMAT, logs._DATEFMT).format(self.record())
        self.assertNotIn("[", line)

    def test_context_is_sorted_for_stable_output(self):
        record = self.record()
        record.ctx_zzz = "z"
        record.ctx_aaa = "a"
        line = logs.ConsoleFormatter(logs._FORMAT, logs._DATEFMT).format(record)
        self.assertLess(line.index("aaa="), line.index("zzz="))


class ConfigureTests(unittest.TestCase):
    def tearDown(self):
        logs.configure()

    def test_writes_json_lines_to_the_log_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "run.log")
            logs.configure(log_path=path)
            logs.LOG.info("first")
            logs.LOG.warning("second")
            for handler in logs.LOG.handlers:
                handler.flush()

            with open(path, encoding="utf-8") as handle:
                lines = [json.loads(line) for line in handle if line.strip()]

        self.assertEqual([line["message"] for line in lines], ["first", "second"])

    def test_file_keeps_debug_even_when_console_is_quiet(self):
        """The file is the record; it must be more detailed than the console."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "run.log")
            logs.configure(verbose=False, log_path=path)
            logs.LOG.debug("a detail only the file will keep")
            for handler in logs.LOG.handlers:
                handler.flush()

            with open(path, encoding="utf-8") as handle:
                messages = [json.loads(line)["message"] for line in handle if line.strip()]

        self.assertIn("a detail only the file will keep", messages)

    def test_configure_is_idempotent(self):
        logs.configure()
        logs.configure()
        logs.configure()
        self.assertEqual(len(logs.LOG.handlers), 1)

    def test_no_file_handler_without_a_path(self):
        logs.configure()
        self.assertEqual(len(logs.LOG.handlers), 1)

    def test_creates_missing_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested", "dir", "run.log")
            logs.configure(log_path=path)
            logs.LOG.info("x")
            for handler in logs.LOG.handlers:
                handler.flush()
            self.assertTrue(os.path.exists(path))


class ReadTests(unittest.TestCase):
    def test_read_returns_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "run.log")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("line\n")
            self.assertEqual(logs.read(path), "line\n")

    def test_missing_log_is_explained_not_raised(self):
        self.assertIn("no run log", logs.read("/nonexistent/run.log"))


if __name__ == "__main__":
    unittest.main()
