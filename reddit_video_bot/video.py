from __future__ import annotations

import json
import logging
import random
import subprocess
from pathlib import Path

from .tts import Word

log = logging.getLogger(__name__)

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac"}


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    log.debug("ffmpeg: %s", " ".join(map(str, cmd)))
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg fehlgeschlagen:\n{proc.stderr[-3000:]}")


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def tighten_pauses(src: Path, dst: Path, words: list[Word], max_gap: float,
                   tail: float = 0.12) -> list[Word]:
    """Schneidet zu lange Pausen zwischen den Wörtern aus dem Ton heraus.

    Jede Lücke, die länger als `max_gap` Sekunden ist, wird auf `max_gap` gekürzt
    (in der Mitte der Stille geschnitten, also ohne Knacken). Die Wort-Zeitstempel
    werden entsprechend verschoben, damit die Untertitel synchron bleiben.
    """
    cuts: list[tuple[float, float]] = []
    for prev, nxt in zip(words, words[1:]):
        excess = (nxt.start - prev.end) - max_gap
        if excess > 0.02:
            mid = (prev.end + nxt.start) / 2
            cuts.append((mid - excess / 2, mid + excess / 2))
    end = min(probe_duration(src), words[-1].end + tail)

    # Abschnitte, die behalten werden
    bounds = [0.0]
    for a, b in cuts:
        bounds += [a, b]
    bounds.append(end)
    keep = list(zip(bounds[0::2], bounds[1::2]))

    filters = [f"[0:a]atrim=start={a:.4f}:end={b:.4f},asetpts=PTS-STARTPTS[s{i}]"
               for i, (a, b) in enumerate(keep)]
    filters.append("".join(f"[s{i}]" for i in range(len(keep))) +
                   f"concat=n={len(keep)}:v=0:a=1[out]")
    script = dst.with_suffix(".filter.txt")
    script.write_text(";\n".join(filters), encoding="utf-8")
    _run(["ffmpeg", "-y", "-i", str(src), "-filter_complex_script", str(script),
          "-map", "[out]", "-c:a", "pcm_s16le", str(dst)])

    def shift(t: float) -> float:
        return t - sum(b - a for a, b in cuts if b <= t)

    return [Word(w.text, shift(w.start), shift(w.end)) for w in words]


def build_narration(parts: list[Path], out: Path, gap: float = 0.2) -> list[float]:
    """Mehrere MP3s mit kurzer Pause verbinden. Gibt die Startzeit jedes Teils zurück."""
    starts, t = [], 0.0
    inputs, filters = [], []
    for i, p in enumerate(parts):
        starts.append(t)
        t += probe_duration(p) + gap
        inputs += ["-i", str(p)]
        filters.append(f"[{i}:a]aresample=44100,apad=pad_dur={gap}[a{i}]")
    concat = "".join(f"[a{i}]" for i in range(len(parts)))
    filters.append(f"{concat}concat=n={len(parts)}:v=0:a=1[out]")
    _run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
          "-map", "[out]", "-c:a", "pcm_s16le", str(out)])
    return starts


def pick_file(directory: Path, extensions: set[str]) -> Path | None:
    if not directory.exists():
        return None
    files = [p for p in directory.rglob("*") if p.suffix.lower() in extensions]
    return random.choice(files) if files else None


def render(*, narration: Path, ass: Path, out: Path, duration: float, cfg: dict,
           background: Path | None, music: Path | None) -> None:
    w, h, fps = cfg.get("width", 1080), cfg.get("height", 1920), cfg.get("fps", 30)
    cmd = ["ffmpeg", "-y", "-hide_banner"]

    if background:
        bg_len = probe_duration(background)
        if bg_len > duration + 1:
            # zufälliger Ausschnitt -> jedes Video sieht anders aus
            cmd += ["-ss", f"{random.uniform(0, bg_len - duration - 1):.2f}", "-i", str(background.resolve())]
        else:
            cmd += ["-stream_loop", "-1", "-i", str(background.resolve())]
        vsrc = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},setsar=1,fps={fps}")
    else:
        # generierter, langsam fließender Farbverlauf als Platzhalter
        cmd += ["-f", "lavfi", "-i",
                f"gradients=s={w}x{h}:r={fps}:speed=0.015:n=5:type=spiral:seed={random.randint(0, 99999)}"]
        vsrc = "[0:v]eq=saturation=1.2:brightness=-0.08,setsar=1"

    cmd += ["-i", str(narration.resolve())]
    filters = [f"{vsrc},ass={ass.name}[v]"]
    # Stimme auf Social-Media-Lautstärke (-14 LUFS) bringen und in Stereo ausgeben –
    # Mono-Ton wird von manchen Handys/Playern nur auf einer Seite oder gar nicht abgespielt.
    lufs = cfg.get("loudness_lufs", -14)
    voice = f"[1:a]loudnorm=I={lufs}:TP=-1.5:LRA=11,aresample=44100,aformat=channel_layouts=stereo"
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music.resolve())]
        vol = cfg.get("music_volume", 0.08)
        filters.append(f"{voice}[n];[2:a]aformat=channel_layouts=stereo,volume={vol}[m];"
                       f"[n][m]amix=inputs=2:duration=first:normalize=0,apad[a]")
    else:
        filters.append(f"{voice},apad[a]")
    amap = "[a]"

    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "[v]", "-map", amap,
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", cfg.get("preset", "veryfast"), "-crf", str(cfg.get("crf", 23)),
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        str(out.resolve()),
    ]
    # ffmpeg im Ordner der .ass-Datei starten -> keine Pfad-Escaping-Probleme
    _run(cmd, cwd=ass.parent)
