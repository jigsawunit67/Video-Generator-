import tempfile
import unittest
from pathlib import Path

from reddit_video_bot.reddit import is_suitable
from reddit_video_bot.state import State
from reddit_video_bot.subtitles import _ts, build_ass, group_words
from reddit_video_bot.text import clean_text, prepare_for_speech, truncate_words
from reddit_video_bot.tts import Word

CFG = {"min_score": 100, "min_words": 5, "max_words": 50, "allow_nsfw": False, "blocked_words": ["update:"]}


def post(**kw):
    base = {"id": "x", "is_self": True, "score": 500, "title": "A title",
            "selftext": "one two three four five six seven"}
    base.update(kw)
    return base


class TextTests(unittest.TestCase):
    def test_clean_markdown_and_links(self):
        t = clean_text("**Hello** [link](https://x.com) see https://foo.bar &amp; ~~bye~~")
        self.assertEqual(t, "Hello link see & bye")

    def test_abbreviations_case_sensitive(self):
        t = prepare_for_speech("AITA? My SO said so. I (23F) told my BF idk")
        self.assertIn("Am I the asshole", t)
        self.assertIn("significant other said so", t)
        self.assertIn("23 year old female", t)
        self.assertIn("boyfriend", t)
        self.assertIn("I don't know", t)

    def test_newlines_become_sentences(self):
        self.assertEqual(prepare_for_speech("first line\nsecond line?\nthird"),
                         "first line. second line? third")

    def test_truncate(self):
        self.assertEqual(truncate_words("a b c", 5), "a b c")
        self.assertTrue(truncate_words("word " * 20, 5).endswith("..."))


class RedditFilterTests(unittest.TestCase):
    def test_accepts_good_post(self):
        self.assertTrue(is_suitable(post(), CFG))

    def test_rejects(self):
        self.assertFalse(is_suitable(post(over_18=True), CFG))
        self.assertFalse(is_suitable(post(score=1), CFG))
        self.assertFalse(is_suitable(post(is_self=False), CFG))
        self.assertFalse(is_suitable(post(stickied=True), CFG))
        self.assertFalse(is_suitable(post(selftext="too short"), CFG))
        self.assertFalse(is_suitable(post(title="UPDATE: something"), CFG))
        self.assertFalse(is_suitable(post(selftext="[removed]"), CFG))


class SubtitleTests(unittest.TestCase):
    def test_timestamp(self):
        self.assertEqual(_ts(3725.5), "1:02:05.50")

    def test_grouping_breaks_on_punctuation(self):
        words = [Word(w, i * 0.3, i * 0.3 + 0.25) for i, w in enumerate("Hi, I am Bob and".split())]
        groups = group_words(words, 3)
        self.assertEqual([[w.text for w in g] for g in groups], [["Hi,"], ["I", "am", "Bob"], ["and"]])

    def test_build_ass(self):
        words = [Word("hello", 2.0, 2.3), Word("world", 2.4, 2.8)]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.ass"
            build_ass(p, "My {title}", "tifu", 1.5, words, {}, 1080, 1920, 3.5)
            content = p.read_text()
        self.assertIn("r/tifu", content)
        self.assertIn("My (title)", content)
        self.assertEqual(content.count("Style: Caption"), 1)
        self.assertEqual(content.count(",Caption,"), 2)


class StateTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            s = State(p)
            s.mark_used("abc", title="t")
            self.assertTrue(State(p).is_used("abc"))
            self.assertFalse(State(p).is_used("zzz"))


if __name__ == "__main__":
    unittest.main()


class VoiceAndPauseTests(unittest.TestCase):
    def test_voice_never_repeats(self):
        from reddit_video_bot.pipeline import pick_voice
        cfg = {"voices": ["a", "b", "c"], "voice": "x"}
        for _ in range(50):
            self.assertNotEqual(pick_voice(cfg, "a"), "a")
        self.assertEqual(pick_voice({"voice": "solo"}, "solo"), "solo")

    def test_tighten_pauses_shifts_timestamps(self):
        import subprocess
        from reddit_video_bot import video
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d) / "in.wav", Path(d) / "out.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                            "-t", "6", str(src)], check=True)
            words = [Word("a", 0.5, 1.0), Word("b", 3.0, 3.5), Word("c", 3.6, 4.0)]  # 2 s Pause nach "a"
            out = video.tighten_pauses(src, dst, words, max_gap=0.2)
            self.assertAlmostEqual(out[1].start - out[0].end, 0.2, places=2)   # Pause gekürzt
            self.assertAlmostEqual(out[2].start - out[1].end, 0.1, places=2)   # kurze Lücke bleibt
            self.assertAlmostEqual(video.probe_duration(dst), 4.0 - 1.8 + 0.12, delta=0.05)
