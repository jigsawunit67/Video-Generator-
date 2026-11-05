from __future__ import annotations

import json
import logging
import random
import subprocess
from pathlib import Path

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


def build_narration(parts: list[Path], out: Path, gap: float = 0.35) -> list[float]:
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
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music.resolve())]
        vol = cfg.get("music_volume", 0.08)
        filters.append(f"[2:a]volume={vol}[m];[1:a][m]amix=inputs=2:duration=first:normalize=0[a]")
        amap = "[a]"
    else:
        amap = "1:a"

    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "[v]", "-map", amap,
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", cfg.get("preset", "veryfast"), "-crf", str(cfg.get("crf", 23)),
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart",
        str(out.resolve()),
    ]
    # ffmpeg im Ordner der .ass-Datei starten -> keine Pfad-Escaping-Probleme
    _run(cmd, cwd=ass.parent)
