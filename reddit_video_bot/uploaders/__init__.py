from __future__ import annotations


def get_uploader(platform: str):
    platform = (platform or "none").lower()
    if platform == "youtube":
        from .youtube import YouTubeUploader

        return YouTubeUploader()
    if platform in ("none", "", "off"):
        return None
    raise ValueError(f"Unbekannte Plattform: {platform}")
