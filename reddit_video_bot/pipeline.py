from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path

import requests

from . import subtitles, tts, video
from .config import resolve
from .reddit import RedditClient, Story, find_story
from .state import State
from .text import prepare_for_speech
from .uploaders import get_uploader

log = logging.getLogger(__name__)

MAX_STORY_ATTEMPTS = 5


class StoryTooLong(Exception):
    pass


def _ensure_backgrounds(bg_dir: Path) -> None:
    """Optional: Hintergrundclips aus BACKGROUND_URLS herunterladen (z.B. für GitHub Actions)."""
    urls = [u.strip() for u in os.getenv("BACKGROUND_URLS", "").replace("\n", ",").split(",") if u.strip()]
    if not urls:
        return
    bg_dir.mkdir(parents=True, exist_ok=True)
    for i, url in enumerate(urls):
        target = bg_dir / f"remote_{i}{Path(url.split('?')[0]).suffix or '.mp4'}"
        if target.exists():
            continue
        log.info("Lade Hintergrundclip %s", url)
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(target, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)


def make_video(story: Story, cfg: dict, workdir: Path) -> tuple[Path, float]:
    tcfg, vcfg = cfg["tts"], cfg["video"]
    voice, rate, pitch = tcfg["voice"], tcfg.get("rate", "+0%"), tcfg.get("pitch", "+0Hz")

    parts: list[Path] = []
    word_lists: list[list[tts.Word]] = []
    if tcfg.get("read_title", True):
        p = workdir / "title.mp3"
        word_lists.append(tts.synthesize(prepare_for_speech(story.title), p, voice, rate, pitch))
        parts.append(p)
    p = workdir / "body.mp3"
    word_lists.append(tts.synthesize(prepare_for_speech(story.body), p, voice, rate, pitch))
    parts.append(p)

    narration = workdir / "narration.wav"
    starts = video.build_narration(parts, narration)
    total = video.probe_duration(narration)

    title_end = 0.0
    body_words = word_lists[-1]
    if tcfg.get("read_title", True):
        title_end = starts[1] - 0.05
    body_words = [tts.Word(w.text, w.start + starts[-1], w.end + starts[-1]) for w in body_words]

    duration = total + 0.6
    if duration > vcfg.get("max_duration", 175):
        raise StoryTooLong(f"{duration:.0f}s")
    ass = workdir / "subs.ass"
    subtitles.build_ass(ass, story.title, story.subreddit, title_end, body_words,
                        cfg.get("subtitles", {}), vcfg.get("width", 1080), vcfg.get("height", 1920),
                        duration)

    out_dir = resolve(vcfg.get("output_dir", "output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{story.subreddit}_{story.id}.mp4"

    background = video.pick_file(resolve(vcfg.get("backgrounds_dir", "assets/backgrounds")), video.VIDEO_EXT)
    if background is None and not vcfg.get("fallback_background", True):
        raise RuntimeError("Keine Hintergrundclips in assets/backgrounds gefunden")
    if background is None:
        log.warning("Keine Hintergrundclips gefunden – nutze generierten Hintergrund")
    music = video.pick_file(resolve(vcfg.get("music_dir", "assets/music")), video.AUDIO_EXT)

    log.info("Rendere %s (%.1fs, Hintergrund: %s)", out.name, duration,
             background.name if background else "generiert")
    video.render(narration=narration, ass=ass, out=out, duration=duration, cfg=vcfg,
                 background=background, music=music)
    return out, duration


def _fmt(template: str, story: Story) -> str:
    return template.format(title=story.title, subreddit=story.subreddit, author=story.author,
                           url=story.url, score=story.score)


def run_once(cfg: dict, *, upload: bool = True, dry_run: bool = False) -> Path | None:
    state = State(resolve(cfg.get("state_file", "data/used_posts.json")))
    vcfg, ucfg = cfg["video"], cfg.get("upload", {})
    _ensure_backgrounds(resolve(vcfg.get("backgrounds_dir", "assets/backgrounds")))

    uploader = get_uploader(ucfg.get("platform", "none")) if upload and not dry_run else None
    client = RedditClient()

    skipped: set[str] = set()
    for _ in range(MAX_STORY_ATTEMPTS):
        story = find_story(cfg["reddit"], lambda pid: state.is_used(pid) or pid in skipped, client)
        if story is None:
            log.error("Keine passende Story gefunden")
            return None
        log.info("Story: r/%s – %s (%d Wörter, %d Upvotes)", story.subreddit, story.title,
                 story.words, story.score)

        try:
            with tempfile.TemporaryDirectory(prefix="rvb_") as tmp:
                out, _ = make_video(story, cfg, Path(tmp))
        except StoryTooLong as exc:
            log.info("Story zu lang fürs Video (%s) – nächste", exc)
            skipped.add(story.id)
            if not dry_run:
                state.mark_used(story.id, skipped="too_long")
            continue

        log.info("Video fertig: %s", out)
        if dry_run or uploader is None:
            if not dry_run:
                state.mark_used(story.id, subreddit=story.subreddit, title=story.title, video=str(out))
            return out

        url = uploader.upload(
            out,
            title=_fmt(ucfg.get("title_template", "{title}"), story),
            description=_fmt(ucfg.get("description_template", ""), story),
            tags=ucfg.get("tags", []),
            privacy=ucfg.get("privacy", "public"),
            category_id=str(ucfg.get("category_id", "24")),
            made_for_kids=bool(ucfg.get("made_for_kids", False)),
        )
        state.mark_used(story.id, subreddit=story.subreddit, title=story.title, video=url)
        if ucfg.get("delete_after_upload", True):
            out.unlink(missing_ok=True)
        return out
    log.error("Nach %d Versuchen keine passende Story", MAX_STORY_ATTEMPTS)
    return None


def check_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise SystemExit(f"'{tool}' nicht gefunden – bitte ffmpeg installieren")
