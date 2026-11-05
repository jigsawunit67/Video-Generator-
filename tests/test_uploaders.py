import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reddit_video_bot.uploaders import platforms_from_config
from reddit_video_bot.uploaders import tiktok


class PlatformConfigTests(unittest.TestCase):
    def test_list_and_legacy(self):
        self.assertEqual(platforms_from_config({"platforms": ["YouTube", "tiktok"]}), ["youtube", "tiktok"])
        self.assertEqual(platforms_from_config({"platform": "youtube"}), ["youtube"])
        self.assertEqual(platforms_from_config({"platforms": []}), [])
        self.assertEqual(platforms_from_config({"platform": "none"}), [])
        with self.assertRaises(ValueError):
            platforms_from_config({"platforms": ["myspace"]})


class Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code, self.text = data, status, ""

    def json(self):
        return self._data


class TikTokTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"TIKTOK_CLIENT_KEY": "k", "TIKTOK_CLIENT_SECRET": "s",
                                                "TIKTOK_REFRESH_TOKEN": "r"})
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = mock.patch.object(tiktok, "TOKEN_CACHE", Path(self.tmp.name) / "tok")
        self.cache.start()

    def tearDown(self):
        self.env.stop()
        self.cache.stop()
        self.tmp.cleanup()

    def test_upload_flow_falls_back_to_private(self):
        calls = []
        ok = {"error": {"code": "ok"}}

        def session_post(url, json=None, timeout=None):
            calls.append((url, json))
            if url.endswith("creator_info/query/"):
                return Resp({**ok, "data": {"privacy_level_options": ["SELF_ONLY"],
                                            "max_video_post_duration_sec": 600}})
            if url.endswith("video/init/"):
                return Resp({**ok, "data": {"publish_id": "p1", "upload_url": "https://up"}})
            return Resp({**ok, "data": {"status": "PUBLISH_COMPLETE"}})

        with mock.patch.object(tiktok.requests, "post",
                               return_value=Resp({"access_token": "a", "refresh_token": "r"})), \
                mock.patch.object(tiktok.requests, "put", return_value=Resp({}, 201)) as put:
            up = tiktok.TikTokUploader()
            up.session.post = session_post
            video = Path(self.tmp.name) / "v.mp4"
            video.write_bytes(b"x" * 1000)
            result = up.upload(video, caption="hi #fyp", duration=60)

        self.assertEqual(result, "tiktok:publish_id=p1")
        init_body = calls[1][1]
        self.assertEqual(init_body["post_info"]["privacy_level"], "SELF_ONLY")
        self.assertEqual(init_body["source_info"],
                         {"source": "FILE_UPLOAD", "video_size": 1000, "chunk_size": 1000, "total_chunk_count": 1})
        self.assertEqual(put.call_args.kwargs["headers"]["Content-Range"], "bytes 0-999/1000")
        self.assertFalse(tiktok.TOKEN_CACHE.exists())

    def test_rotated_refresh_token_is_cached(self):
        with mock.patch.object(tiktok.requests, "post",
                               return_value=Resp({"access_token": "a", "refresh_token": "NEW"})):
            tiktok.TikTokUploader()
        self.assertEqual(tiktok.TOKEN_CACHE.read_text(), "NEW")


if __name__ == "__main__":
    unittest.main()
