from __future__ import annotations

import asyncio
import logging
import os
import ssl
from dataclasses import dataclass
from pathlib import Path

import edge_tts

log = logging.getLogger(__name__)

# Wer hinter einem Firmen-Proxy mit eigenem Zertifikat sitzt, kann SSL_CERT_FILE setzen.
if os.getenv("SSL_CERT_FILE"):
    try:
        import edge_tts.communicate as _comm

        _comm._SSL_CTX = ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])
    except (AttributeError, OSError):  # pragma: no cover
        pass

TICKS_PER_SECOND = 10_000_000  # edge-tts liefert Offsets in 100-ns-Einheiten


@dataclass
class Word:
    text: str
    start: float  # Sekunden
    end: float


async def _synthesize(text: str, out: Path, voice: str, rate: str, pitch: str) -> list[Word]:
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    words: list[Word] = []
    with open(out, "wb") as fh:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / TICKS_PER_SECOND
                words.append(Word(chunk["text"], start, start + chunk["duration"] / TICKS_PER_SECOND))
    if not words:
        raise RuntimeError("TTS hat keine Wort-Zeitstempel geliefert")
    return words


def synthesize(text: str, out: Path, voice: str, rate: str = "+0%", pitch: str = "+0Hz",
               retries: int = 3) -> list[Word]:
    """Text -> MP3. Gibt die Wörter mit Zeitstempeln (für Untertitel) zurück."""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return asyncio.run(_synthesize(text, out, voice, rate, pitch))
        except Exception as exc:  # Netzwerkfehler o.ä. -> nochmal versuchen
            last_exc = exc
            log.warning("TTS-Versuch %d/%d fehlgeschlagen: %s", attempt, retries, exc)
    raise RuntimeError(f"TTS fehlgeschlagen: {last_exc}") from last_exc
