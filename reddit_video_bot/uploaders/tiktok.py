from __future__ import annotations

import logging
import math
import os
import time
from pathlib import Path

import requests

from ..config import ROOT

log = logging.getLogger(__name__)

API = "https://open.tiktokapis.com/v2"
# Falls TikTok beim Erneuern einen neuen Refresh-Token ausgibt, wird er hier gespeichert
TOKEN_CACHE = ROOT / ".tiktok_refresh_token"

MAX_SINGLE_CHUNK = 64 * 1024 * 1024
CHUNK = 10 * 1024 * 1024


class TikTokError(RuntimeError):
    pass


class TikTokUploader:
    """Veröffentlicht Videos über die offizielle TikTok Content Posting API (Direct Post).

    Benötigt TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET und TIKTOK_REFRESH_TOKEN
    (einmalig mit scripts/tiktok_auth.py erzeugen).
    """

    def __init__(self):
        missing = [k for k in ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN")
                   if not os.getenv(k)]
        if missing:
            raise RuntimeError(f"TikTok-Zugangsdaten fehlen: {', '.join(missing)} "
                               "(siehe README, Abschnitt 'TikTok einrichten')")
        self.session = requests.Session()
        self.access_token = self._refresh()
        self.session.headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        })

    def _refresh(self) -> str:
        refresh = os.environ["TIKTOK_REFRESH_TOKEN"]
        if TOKEN_CACHE.exists():
            refresh = TOKEN_CACHE.read_text().strip() or refresh
        resp = requests.post(f"{API}/oauth/token/", timeout=30, data={
            "client_key": os.environ["TIKTOK_CLIENT_KEY"],
            "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": refresh,
        })
        data = resp.json()
        if "access_token" not in data:
            raise TikTokError(f"TikTok-Token konnte nicht erneuert werden: {data}")
        new_refresh = data.get("refresh_token")
        if new_refresh and new_refresh != refresh:
            TOKEN_CACHE.write_text(new_refresh)
            log.warning("TikTok hat einen neuen Refresh-Token ausgegeben (gespeichert in %s). "
                        "Bei GitHub Actions bitte das Secret TIKTOK_REFRESH_TOKEN aktualisieren.",
                        TOKEN_CACHE.name)
        return data["access_token"]

    def _post(self, path: str, body: dict) -> dict:
        resp = self.session.post(f"{API}{path}", json=body, timeout=60)
        data = resp.json()
        err = data.get("error", {})
        if resp.status_code != 200 or err.get("code") not in (None, "ok"):
            raise TikTokError(f"TikTok {path}: {resp.status_code} {err}")
        return data.get("data", {})

    def upload(self, video: Path, *, caption: str, privacy: str = "PUBLIC_TO_EVERYONE",
               duration: float | None = None, disable_comment: bool = False,
               disable_duet: bool = False, disable_stitch: bool = False) -> str:
        # 1) Pflicht laut TikTok: vor jedem Post die Creator-Infos abfragen
        creator = self._post("/post/publish/creator_info/query/", {})
        options = creator.get("privacy_level_options", [])
        if privacy not in options:
            fallback = "SELF_ONLY" if "SELF_ONLY" in options else (options or [privacy])[0]
            log.warning("TikTok erlaubt '%s' für diese App nicht (erlaubt: %s) – nutze '%s'. "
                        "Öffentliche Posts gibt es erst nach dem TikTok-App-Audit.",
                        privacy, options, fallback)
            privacy = fallback
        max_len = creator.get("max_video_post_duration_sec")
        if duration and max_len and duration > max_len:
            raise TikTokError(f"Video ({duration:.0f}s) länger als von TikTok erlaubt ({max_len}s)")

        # 2) Upload initialisieren
        size = video.stat().st_size
        if size <= MAX_SINGLE_CHUNK:
            chunk_size, chunks = size, 1
        else:
            chunk_size = CHUNK
            chunks = size // CHUNK  # letzter Chunk nimmt den Rest mit auf
        init = self._post("/post/publish/video/init/", {
            "post_info": {
                "title": caption[:2200],
                "privacy_level": privacy,
                "disable_comment": disable_comment or creator.get("comment_disabled", False),
                "disable_duet": disable_duet or creator.get("duet_disabled", False),
                "disable_stitch": disable_stitch or creator.get("stitch_disabled", False),
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk_size,
                "total_chunk_count": chunks,
            },
        })
        publish_id, upload_url = init["publish_id"], init["upload_url"]

        # 3) Datei hochladen
        with open(video, "rb") as fh:
            for i in range(chunks):
                start = i * chunk_size
                end = size - 1 if i == chunks - 1 else start + chunk_size - 1
                fh.seek(start)
                part = fh.read(end - start + 1)
                r = requests.put(upload_url, data=part, timeout=300, headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(part)),
                    "Content-Range": f"bytes {start}-{end}/{size}",
                })
                if r.status_code not in (200, 201, 206):
                    raise TikTokError(f"TikTok-Upload Chunk {i + 1}/{chunks}: {r.status_code} {r.text[:300]}")
                log.info("TikTok-Upload: %d%%", math.floor((end + 1) / size * 100))

        # 4) Auf Veröffentlichung warten
        for _ in range(60):
            status = self._post("/post/publish/status/fetch/", {"publish_id": publish_id})
            state = status.get("status")
            if state == "PUBLISH_COMPLETE":
                ids = status.get("publicaly_available_post_id") or status.get("publicly_available_post_id") or []
                log.info("TikTok: veröffentlicht (%s)", privacy)
                return f"tiktok:{ids[0]}" if ids else f"tiktok:publish_id={publish_id}"
            if state == "FAILED":
                raise TikTokError(f"TikTok-Veröffentlichung fehlgeschlagen: {status.get('fail_reason')}")
            time.sleep(5)
        log.warning("TikTok verarbeitet das Video noch – es erscheint in Kürze im Profil")
        return f"tiktok:publish_id={publish_id}"
