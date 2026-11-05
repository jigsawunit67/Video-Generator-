from __future__ import annotations

import html
import re

# Reddit-Abkürzungen ausschreiben, damit die TTS-Stimme sie natürlich vorliest
ABBREVIATIONS = {
    r"\bAITA\b": "Am I the asshole",
    r"\bWIBTA\b": "Would I be the asshole",
    r"\bAITAH\b": "Am I the asshole",
    r"\bNTA\b": "not the asshole",
    r"\bYTA\b": "you're the asshole",
    r"\bESH\b": "everyone sucks here",
    r"\bTIFU\b": "Today I fucked up",
    r"\bTL;?DR\b": "Too long, didn't read",
    r"\bIIRC\b": "if I remember correctly",
    r"\bIMO\b": "in my opinion",
    r"\bIMHO\b": "in my honest opinion",
    r"\bTBH\b": "to be honest",
    r"\bSO\b": "significant other",
    r"\bBF\b": "boyfriend",
    r"\bGF\b": "girlfriend",
    r"\bMIL\b": "mother in law",
    r"\bFIL\b": "father in law",
    r"\bSIL\b": "sister in law",
    r"\bBIL\b": "brother in law",
    r"\bDH\b": "my husband",
    r"\bOP\b": "O P",
    r"\bETA\b": "Edit",
    r"\bw/o\b": "without",
    r"\bw/(?=\s)": "with",
    r"\bppl\b": "people",
    r"\bidk\b": "I don't know",
    r"\bomg\b": "oh my god",
}

# (23F), [25 M] usw. -> "23 year old female"
_AGE_GENDER = re.compile(r"[\(\[](\d{1,2})\s?([MFmf])[\)\]]")


def _age_gender(match: re.Match) -> str:
    age, g = match.group(1), match.group(2).lower()
    return f"{age} year old {'male' if g == 'm' else 'female'}"


def clean_text(text: str) -> str:
    """Markdown, Links und Reddit-Eigenheiten entfernen."""
    if not text:
        return ""
    t = html.unescape(text)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)            # Bilder
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)          # [text](url) -> text
    t = re.sub(r"https?://\S+", "", t)                      # nackte URLs
    t = re.sub(r"&#x200B;|​", "", t)                   # zero-width
    t = re.sub(r"^\s*>+\s?", "", t, flags=re.M)             # Zitate
    t = re.sub(r"^\s*#+\s*", "", t, flags=re.M)             # Überschriften
    t = re.sub(r"[*_~`^]+", "", t)                          # Formatierung
    t = re.sub(r"^\s*[-+]\s+", "", t, flags=re.M)           # Listen
    t = re.sub(r"\br/(\w+)", r"r slash \1", t)
    t = re.sub(r"\bu/(\w+)", r"u slash \1", t)
    t = re.sub(r"\n{2,}", "\n", t)
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def prepare_for_speech(text: str) -> str:
    t = _AGE_GENDER.sub(_age_gender, text)
    for pattern, repl in ABBREVIATIONS.items():
        # Großgeschriebene Kürzel (SO, OP, BF ...) nur exakt ersetzen,
        # sonst würde z.B. jedes "so" ersetzt werden.
        flags = re.I if any(c.islower() for c in pattern.replace("\\b", "")) else 0
        t = re.sub(pattern, repl, t, flags=flags)
    t = t.replace("&", " and ")
    t = re.sub(r"([^.!?:;,\s])[ \t]*\n\s*", r"\1. ", t)  # Zeilenende = Satzende
    t = re.sub(r"\s*\n\s*", " ", t)
    t = re.sub(r"\.{2,}", ".", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def word_count(text: str) -> int:
    return len(text.split())


def truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    cut = " ".join(words[:max_words])
    # am letzten Satzende abschneiden, damit es nicht mitten im Satz endet
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > len(cut) * 0.6 else cut + "..."
