from __future__ import annotations

import logging
import os
import random
import shutil
import tempfile
from pathlib import Path

import requests

from . import subtitles, tts, video
from .config import resolve
from .reddit import RedditClient, Story, find_story
from .state import State
from .text import prepare_for_speech
from .uploaders import get_uploader, platforms_from_config

log = logging.getLogger(__name__)

MAX_STORY_ATTEMPTS = 5


class StoryTooLong(Exception):
    pass


class PartialUploadError(RuntimeError):
    """Mindestens eine Plattform hat geklappt, mindestens eine nicht."""


def _publish(uploaders: dict, out: Path, duration: float, story: Story,
             ucfg: dict) -> tuple[dict, dict]:
    results, errors = {}, {}
    for name, uploader in uploaders.items():
        pcfg = ucfg.get(name, {})
        try:
            if name == "youtube":
                results[name] = uploader.upload(
                    out,
                    title=_fmt(pcfg.get("title_template", "{title} #shorts"), story),
                    description=_fmt(pcfg.get("description_template", ""), story),
                    tags=pcfg.get("tags", []),
                    privacy=pcfg.get("privacy", "public"),
                    category_id=str(pcfg.get("category_id", "24")),
                    made_for_kids=bool(pcfg.get("made_for_kids", False)),
                )
            elif name == "tiktok":
                results[name] = uploader.upload(
                    out,
                    caption=_fmt(pcfg.get("caption_template", "{title}"), story),
                    privacy=pcfg.get("privacy", "PUBLIC_TO_EVERYONE"),
                    duration=duration,
                    disable_comment=bool(pcfg.get("disable_comment", False)),
                    disable_duet=bool(pcfg.get("disable_duet", False)),
                    disable_stitch=bool(pcfg.get("disable_stitch", False)),
                )
            log.info("%s: %s", name, results[name])
        except Exception as exc:  # andere Plattformen trotzdem versuchen
            log.exception("Upload zu %s fehlgeschlagen", name)
            errors[name] = str(exc)
    return results, errors


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


def pick_voice(tcfg: dict, last: str | None = None) -> str:
    """Zufällige Stimme aus `tts.voices`; nie zweimal hintereinander dieselbe."""
    voices = tcfg.get("voices") or [tcfg["voice"]]
    choices = [v for v in voices if v != last] or voices
    return random.choice(choices)


def make_video(story: Story, cfg: dict, workdir: Path, voice: str | None = None) -> tuple[Path, float]:
    tcfg, vcfg = cfg["tts"], cfg["video"]
    voice = voice or pick_voice(tcfg)
    rate, pitch = tcfg.get("rate", "+0%"), tcfg.get("pitch", "+0Hz")
    max_gap = float(tcfg.get("max_pause", 0.14))
    log.info("Stimme: %s", voice)

    parts: list[Path] = []
    word_lists: list[list[tts.Word]] = []
    if tcfg.get("read_title", True):
        p = workdir / "title.mp3"
        words = tts.synthesize(prepare_for_speech(story.title), p, voice, rate, pitch)
        tight = p.with_name("title_tight.wav")
        word_lists.append(video.tighten_pauses(p, tight, words, max_gap))
        parts.append(tight)
    p = workdir / "body.mp3"
    words = tts.synthesize(prepare_for_speech(story.body), p, voice, rate, pitch)
    tight = p.with_name("body_tight.wav")
    word_lists.append(video.tighten_pauses(p, tight, words, max_gap))
    parts.append(tight)

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

    uploaders = {}
    if upload and not dry_run:
        # Zugangsdaten vor dem Rendern prüfen -> Fehler fallen sofort auf
        uploaders = {name: get_uploader(name) for name in platforms_from_config(ucfg)}
    client = RedditClient()

    skipped: set[str] = set()
    for _ in range(MAX_STORY_ATTEMPTS):
        story = find_story(cfg["reddit"], lambda pid: state.is_used(pid) or pid in skipped, client)
        if story is None:
            log.error("Keine passende Story gefunden")
            return None
        log.info("Story: r/%s – %s (%d Wörter, %d Upvotes)", story.subreddit, story.title,
                 story.words, story.score)

        voice = pick_voice(cfg["tts"], state.last_voice)
        try:
            with tempfile.TemporaryDirectory(prefix="rvb_") as tmp:
                out, duration = make_video(story, cfg, Path(tmp), voice)
        except StoryTooLong as exc:
            log.info("Story zu lang fürs Video (%s) – nächste", exc)
            skipped.add(story.id)
            if not dry_run:
                state.mark_used(story.id, skipped="too_long")
            continue

        log.info("Video fertig: %s", out)
        if not dry_run:
            state.set_last_voice(voice)
        if dry_run or not uploaders:
            if not dry_run:
                state.mark_used(story.id, subreddit=story.subreddit, title=story.title, video=str(out))
            return out

        results, errors = _publish(uploaders, out, duration, story, ucfg)
        if not results:
            raise RuntimeError(f"Upload auf allen Plattformen fehlgeschlagen: {errors}")
        state.mark_used(story.id, subreddit=story.subreddit, title=story.title, uploads=results)
        if ucfg.get("delete_after_upload", True):
            out.unlink(missing_ok=True)
        if errors:
            raise PartialUploadError(f"Teilweise fehlgeschlagen: {errors} (erfolgreich: {results})")
        return out
    log.error("Nach %d Versuchen keine passende Story", MAX_STORY_ATTEMPTS)
    return None


def post_file(cfg: dict, path: Path, caption: str, platforms: list[str] | None = None) -> dict:
    """Lädt eine fertige Videodatei hoch (ohne Reddit), z.B. für Tests oder das TikTok-Demo-Video."""
    ucfg = cfg.get("upload", {})
    names = platforms or platforms_from_config(ucfg)
    if not names:
        raise SystemExit("Keine Plattform angegeben (--platform tiktok|youtube)")
    duration = video.probe_duration(path)
    story = Story(id="file", subreddit="reddit", title=caption, body="", author="unknown",
                  url="", score=0)
    uploaders = {n: get_uploader(n) for n in names}
    results, errors = _publish(uploaders, path, duration, story, ucfg)
    if errors:
        log.error("Fehler: %s", errors)
    return results


def check_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise SystemExit(f"'{tool}' nicht gefunden – bitte ffmpeg installieren")
