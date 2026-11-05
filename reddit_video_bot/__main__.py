"""Kommandozeile:

    python -m reddit_video_bot run              # 1 Video erstellen + hochladen
    python -m reddit_video_bot run --dry-run    # nur erstellen, nicht hochladen
    python -m reddit_video_bot schedule         # Dauerbetrieb, Uhrzeiten aus --times
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time

from .config import load_config
from .pipeline import check_tools, post_file, run_once


def _schedule(cfg: dict, times: list[str], upload: bool) -> None:
    targets = sorted(dt.time.fromisoformat(t) for t in times)
    logging.info("Scheduler aktiv – Uploads täglich um %s", ", ".join(t.strftime("%H:%M") for t in targets))
    while True:
        now = dt.datetime.now()
        upcoming = [dt.datetime.combine(now.date(), t) for t in targets]
        upcoming += [dt.datetime.combine(now.date() + dt.timedelta(days=1), t) for t in targets]
        nxt = min(u for u in upcoming if u > now)
        logging.info("Nächster Lauf: %s", nxt.strftime("%Y-%m-%d %H:%M"))
        time.sleep(max(1.0, (nxt - now).total_seconds()))
        try:
            run_once(cfg, upload=upload)
        except Exception:  # Scheduler soll bei einem Fehler weiterlaufen
            logging.exception("Lauf fehlgeschlagen")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="reddit_video_bot", description="Reddit-Story-Videos automatisch erstellen")
    ap.add_argument("-c", "--config", help="Pfad zur config.yaml")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="ein Video erstellen (und hochladen)")
    r.add_argument("--dry-run", action="store_true", help="nicht hochladen, Story nicht als benutzt markieren")
    r.add_argument("--no-upload", action="store_true", help="erstellen und als benutzt markieren, nicht hochladen")

    f = sub.add_parser("post-file", help="eine fertige Videodatei hochladen (ohne Reddit)")
    f.add_argument("file")
    f.add_argument("--caption", default="Reddit story")
    f.add_argument("--platform", action="append", choices=["tiktok", "youtube"],
                   help="Zielplattform (mehrfach möglich, Standard: aus config.yaml)")

    s = sub.add_parser("schedule", help="dauerhaft laufen und zu festen Zeiten posten")
    s.add_argument("--times", nargs="+", default=["12:00", "19:00"], help="Uhrzeiten HH:MM (Standard: 12:00 19:00)")
    s.add_argument("--no-upload", action="store_true")

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    check_tools()
    cfg = load_config(args.config)

    if args.cmd == "post-file":
        from pathlib import Path

        res = post_file(cfg, Path(args.file), args.caption, args.platform)
        print(res)
        return 0 if res else 1
    if args.cmd == "run":
        out = run_once(cfg, upload=not args.no_upload, dry_run=args.dry_run)
        return 0 if out else 1
    _schedule(cfg, args.times, upload=not args.no_upload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
