from __future__ import annotations

import json
import time
from pathlib import Path


class State:
    """Merkt sich, welche Reddit-Posts schon verarbeitet wurden (keine Duplikate)."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {"used": {}}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        self.data.setdefault("used", {})

    def is_used(self, post_id: str) -> bool:
        return post_id in self.data["used"]

    def mark_used(self, post_id: str, **info) -> None:
        self.data["used"][post_id] = {"ts": int(time.time()), **info}
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
