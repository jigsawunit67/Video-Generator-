from __future__ import annotations

SUPPORTED = ("youtube", "tiktok")


def platforms_from_config(ucfg: dict) -> list[str]:
    raw = ucfg.get("platforms", ucfg.get("platform", []))
    if isinstance(raw, str):
        raw = [raw]
    names = [p.strip().lower() for p in raw if p and p.strip().lower() not in ("none", "off")]
    unknown = [p for p in names if p not in SUPPORTED]
    if unknown:
        raise ValueError(f"Unbekannte Plattform(en): {', '.join(unknown)} – erlaubt: {', '.join(SUPPORTED)}")
    return names


def get_uploader(platform: str):
    if platform == "youtube":
        from .youtube import YouTubeUploader

        return YouTubeUploader()
    if platform == "tiktok":
        from .tiktok import TikTokUploader

        return TikTokUploader()
    raise ValueError(f"Unbekannte Plattform: {platform}")
