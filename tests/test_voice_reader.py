import json
import unittest

from voice_reader import (
    VoiceReaderConfig,
    find_config_json,
    parse_voice_reader_config,
)


def page(config_json: str) -> str:
    return (
        "<html><head></head><body>"
        '<script id="mai-voice-reader-js-extra">\n'
        f"var MAIVoiceReaderConfig = {config_json};\n"
        "</script></body></html>"
    )


READY = {
    "initialAudio": {
        "status": "ready",
        "audio_url": "https://example.test/?content_audio=1&content_sig=abc",
        "duration_sec": 343.078,
        "size_bytes": 6863040,
    }
}


class ParseConfigTests(unittest.TestCase):
    def test_ready_article_yields_audio(self):
        cfg = parse_voice_reader_config(page(json.dumps(READY)))
        self.assertTrue(cfg.has_audio)
        self.assertEqual(cfg.status, "ready")
        self.assertEqual(cfg.duration_sec, 343.078)
        self.assertEqual(cfg.size_bytes, 6863040)

    def test_missing_config_is_absent_not_error(self):
        cfg = parse_voice_reader_config("<html><body>no player</body></html>")
        self.assertEqual(cfg, VoiceReaderConfig("absent", None, None, None))
        self.assertFalse(cfg.has_audio)

    def test_non_ready_status_has_no_audio(self):
        cfg = parse_voice_reader_config(
            page(json.dumps({"initialAudio": {"status": "pending"}}))
        )
        self.assertFalse(cfg.has_audio)
        self.assertEqual(cfg.status, "pending")

    def test_ready_but_no_url_has_no_audio(self):
        payload = {"initialAudio": {"status": "ready", "size_bytes": 10}}
        cfg = parse_voice_reader_config(page(json.dumps(payload)))
        self.assertFalse(cfg.has_audio)

    def test_ready_but_no_size_has_no_audio(self):
        payload = {"initialAudio": {"status": "ready", "audio_url": "https://x.test/a"}}
        cfg = parse_voice_reader_config(page(json.dumps(payload)))
        self.assertFalse(cfg.has_audio)

    def test_malformed_json_is_absent(self):
        cfg = parse_voice_reader_config(page('{"initialAudio": {"status": "rea'))
        self.assertEqual(cfg.status, "absent")

    def test_braces_inside_strings_do_not_unbalance(self):
        payload = {
            "initialAudio": {
                "status": "ready",
                "audio_url": "https://x.test/a?q={weird}&b=}",
                "duration_sec": 1.5,
                "size_bytes": 99,
            }
        }
        cfg = parse_voice_reader_config(page(json.dumps(payload)))
        self.assertTrue(cfg.has_audio)
        self.assertEqual(cfg.size_bytes, 99)

    def test_quoted_escapes_do_not_unbalance(self):
        payload = {"initialAudio": {"status": "ready", "audio_url": 'a"b\\', "size_bytes": 1}}
        cfg = parse_voice_reader_config(page(json.dumps(payload)))
        self.assertEqual(cfg.status, "ready")

    def test_string_duration_and_size_are_coerced(self):
        payload = {
            "initialAudio": {
                "status": "ready",
                "audio_url": "https://x.test/a",
                "duration_sec": "12.5",
                "size_bytes": "1000",
            }
        }
        cfg = parse_voice_reader_config(page(json.dumps(payload)))
        self.assertEqual(cfg.duration_sec, 12.5)
        self.assertEqual(cfg.size_bytes, 1000)
        self.assertTrue(cfg.has_audio)

    def test_bad_numbers_become_none(self):
        payload = {
            "initialAudio": {
                "status": "ready",
                "audio_url": "https://x.test/a",
                "duration_sec": "n/a",
                "size_bytes": "huge",
            }
        }
        cfg = parse_voice_reader_config(page(json.dumps(payload)))
        self.assertIsNone(cfg.duration_sec)
        self.assertIsNone(cfg.size_bytes)

    def test_initial_audio_not_a_dict_is_absent(self):
        cfg = parse_voice_reader_config(page(json.dumps({"initialAudio": []})))
        self.assertEqual(cfg.status, "absent")

    def test_find_config_returns_balanced_object(self):
        raw = find_config_json(page(json.dumps(READY)))
        self.assertTrue(raw.startswith("{"))
        self.assertTrue(raw.endswith("}"))
        self.assertEqual(json.loads(raw), READY)


if __name__ == "__main__":
    unittest.main()
