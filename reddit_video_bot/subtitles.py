from __future__ import annotations

from pathlib import Path

from .tts import Word


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def group_words(words: list[Word], per_line: int) -> list[list[Word]]:
    """Wörter zu kurzen Zeilen gruppieren; an Satzzeichen/Pausen wird umgebrochen."""
    groups: list[list[Word]] = []
    cur: list[Word] = []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        pause = nxt is not None and nxt.start - w.end > 0.35
        if len(cur) >= per_line or w.text[-1:] in ".!?,;:" or pause or nxt is None:
            groups.append(cur)
            cur = []
    return groups


def build_ass(path: Path, title: str, subreddit: str, title_end: float,
              words: list[Word], cfg: dict, width: int, height: int,
              total_duration: float) -> None:
    font = cfg.get("font", "Arial Black")
    size = cfg.get("font_size", 92)
    primary = cfg.get("primary_color", "&H00FFFFFF")
    highlight = cfg.get("highlight_color", "&H0000F0FF")
    outline = cfg.get("outline", 6)
    margin_v = cfg.get("margin_v", 0)
    per_line = max(1, int(cfg.get("words_per_line", 3)))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{size},{primary},&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{outline},3,5,60,60,{margin_v},1
Style: Title,Arial,62,&H00111111,&H000000FF,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,28,0,5,110,110,0,1
Style: Sub,Arial,44,&H00787C7E,&H000000FF,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,28,0,5,110,110,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines: list[str] = []

    # Titelkarte im Reddit-Look (weiße Box) während der Titel vorgelesen wird
    if title_end > 0:
        pop = r"{\fscx80\fscy80\t(0,150,\fscx100\fscy100)}"
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(title_end)},Sub,,0,0,0,,"
                     f"{{\\pos({width // 2},{int(height * 0.40)})}}{pop}r/{_esc(subreddit)}")
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(title_end)},Title,,0,0,0,,"
                     f"{{\\an8\\pos({width // 2},{int(height * 0.43)})}}{pop}{_esc(title)}")

    # Wort-für-Wort-Untertitel, aktuelles Wort farbig hervorgehoben
    groups = group_words(words, per_line)
    for gi, group in enumerate(groups):
        group_end = groups[gi + 1][0].start if gi + 1 < len(groups) else total_duration
        for wi, w in enumerate(group):
            start = w.start
            end = group[wi + 1].start if wi + 1 < len(group) else group_end
            if end <= start:
                continue
            parts = []
            for wj, other in enumerate(group):
                txt = _esc(other.text).upper()
                parts.append(f"{{\\c{highlight}}}{txt}{{\\c{primary}}}" if wj == wi else txt)
            pop = r"{\fscx92\fscy92\t(0,80,\fscx100\fscy100)}" if wi == 0 else ""
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Caption,,0,0,0,,{pop}{' '.join(parts)}")

    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
