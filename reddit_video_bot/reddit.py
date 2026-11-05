from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass

import requests

from .text import clean_text, word_count

log = logging.getLogger(__name__)

PUBLIC_BASE = "https://www.reddit.com"
OAUTH_BASE = "https://oauth.reddit.com"


@dataclass
class Story:
    id: str
    subreddit: str
    title: str
    body: str
    author: str
    url: str
    score: int

    @property
    def words(self) -> int:
        return word_count(self.title) + word_count(self.body)


class RedditClient:
    """Holt Posts über die offizielle Reddit-API (OAuth, app-only) oder – ohne
    Zugangsdaten – über die öffentliche JSON-Schnittstelle."""

    def __init__(self, user_agent: str | None = None):
        self.user_agent = user_agent or os.getenv(
            "REDDIT_USER_AGENT", "reddit-story-bot/1.0"
        )
        self.session = requests.Session()
        self.session.headers["User-Agent"] = self.user_agent
        self.base = PUBLIC_BASE
        cid, secret = os.getenv("REDDIT_CLIENT_ID"), os.getenv("REDDIT_CLIENT_SECRET")
        if cid and secret:
            self._authenticate(cid, secret)

    def _authenticate(self, cid: str, secret: str) -> None:
        resp = self.session.post(
            f"{PUBLIC_BASE}/api/v1/access_token",
            auth=(cid, secret),
            data={"grant_type": "client_credentials"},
            timeout=30,
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        self.session.headers["Authorization"] = f"bearer {token}"
        self.base = OAUTH_BASE
        log.info("Reddit: per OAuth angemeldet")

    def listing(self, subreddit: str, sort: str = "top", time_filter: str = "day",
                limit: int = 50) -> list[dict]:
        params = {"limit": limit, "raw_json": 1}
        if sort == "top":
            params["t"] = time_filter
        suffix = "" if self.base == OAUTH_BASE else ".json"
        resp = self.session.get(f"{self.base}/r/{subreddit}/{sort}{suffix}",
                                params=params, timeout=30)
        resp.raise_for_status()
        return [c["data"] for c in resp.json()["data"]["children"]]


def is_suitable(post: dict, cfg: dict) -> bool:
    if post.get("stickied") or post.get("pinned"):
        return False
    if not post.get("is_self"):
        return False
    if post.get("over_18") and not cfg.get("allow_nsfw", False):
        return False
    if post.get("removed_by_category") or post.get("selftext") in ("[removed]", "[deleted]"):
        return False
    if post.get("score", 0) < cfg.get("min_score", 0):
        return False
    text = f"{post.get('title', '')} {post.get('selftext', '')}".lower()
    if any(w.lower() in text for w in cfg.get("blocked_words", [])):
        return False
    n = word_count(clean_text(post.get("selftext", "")))
    return cfg.get("min_words", 0) <= n <= cfg.get("max_words", 10_000)


def find_story(cfg: dict, is_used, client: RedditClient | None = None) -> Story | None:
    """Durchsucht die konfigurierten Subreddits und gibt die beste neue Story zurück."""
    client = client or RedditClient()
    subs = list(cfg["subreddits"])
    random.shuffle(subs)
    for sub in subs:
        try:
            posts = client.listing(sub, cfg.get("sort", "top"),
                                   cfg.get("time_filter", "day"), cfg.get("limit", 50))
        except requests.RequestException as exc:
            log.warning("r/%s konnte nicht geladen werden: %s", sub, exc)
            continue
        candidates = [p for p in posts if not is_used(p["id"]) and is_suitable(p, cfg)]
        if not candidates:
            log.info("r/%s: keine passende neue Story", sub)
            continue
        best = max(candidates, key=lambda p: p.get("score", 0))
        return Story(
            id=best["id"],
            subreddit=best.get("subreddit", sub),
            title=clean_text(best["title"]),
            body=clean_text(best["selftext"]),
            author=best.get("author", "[deleted]"),
            url=f"https://www.reddit.com{best.get('permalink', '')}",
            score=best.get("score", 0),
        )
    return None
