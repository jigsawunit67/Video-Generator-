from __future__ import annotations

import logging
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


class YouTubeUploader:
    """Lädt Videos über die offizielle YouTube Data API v3 hoch.

    Benötigt YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET und YOUTUBE_REFRESH_TOKEN
    (einmalig mit scripts/youtube_auth.py erzeugen).
    """

    def __init__(self):
        missing = [k for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
                   if not os.getenv(k)]
        if missing:
            raise RuntimeError(f"YouTube-Zugangsdaten fehlen: {', '.join(missing)} "
                               "(siehe README, Abschnitt 'YouTube einrichten')")
        creds = Credentials(
            token=None,
            refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
            client_id=os.environ["YOUTUBE_CLIENT_ID"],
            client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
            token_uri=TOKEN_URI,
            scopes=SCOPES,
        )
        creds.refresh(Request())
        self.api = build("youtube", "v3", credentials=creds, cache_discovery=False)

    def upload(self, video: Path, *, title: str, description: str, tags: list[str],
               privacy: str = "public", category_id: str = "24",
               made_for_kids: bool = False) -> str:
        body = {
            "snippet": {
                "title": title[:100],          # YouTube-Limit
                "description": description[:5000],
                "tags": tags,
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": made_for_kids,
            },
        }
        media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024,
                                resumable=True)
        request = self.api.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        retries = 0
        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    log.info("Upload: %d%%", int(status.progress() * 100))
            except HttpError as exc:
                if exc.resp.status in (500, 502, 503, 504) and retries < 5:
                    retries += 1
                    log.warning("Upload-Fehler %s, neuer Versuch (%d)", exc.resp.status, retries)
                    continue
                raise
        video_id = response["id"]
        log.info("Hochgeladen: https://youtube.com/shorts/%s", video_id)
        return f"https://youtube.com/shorts/{video_id}"
