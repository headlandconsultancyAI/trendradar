"""Shared helpers: the common item shape, safe getters and time handling."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

log = logging.getLogger("radar")

NOW = datetime.now(timezone.utc)

# What happened with Claude this run, shown on the dashboard so failures aren't silent
CLAUDE = {"key_set": False, "tagged": 0, "errors": []}


def claude_error(where: str, e: Exception) -> None:
    msg = f"{where}: {type(e).__name__}: {e}"
    log.error(msg)
    if msg[:200] not in [m[:200] for m in CLAUDE["errors"]]:
        CLAUDE["errors"].append(msg[:500])


def set_now(dt: datetime) -> None:
    """Lets offline tests pin 'now' so sample data always looks fresh."""
    global NOW
    NOW = dt


def get(d, *path, default=None):
    """Safe nested getter: get(item, 'authorMeta', 'name')."""
    cur = d
    for key in path:
        if cur is None:
            return default
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and isinstance(key, int):
            cur = cur[key] if -len(cur) <= key < len(cur) else None
        else:
            return default
    return default if cur is None else cur


def first(d, *keys, default=None):
    """Return the first non-empty value among several possible field names."""
    for k in keys:
        v = get(d, *k) if isinstance(k, tuple) else (d.get(k) if isinstance(d, dict) else None)
        if v not in (None, "", [], {}):
            return v
    return default


def to_int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def parse_time(v) -> datetime | None:
    """Accepts ISO strings, unix seconds or unix milliseconds."""
    if v in (None, ""):
        return None
    try:
        if isinstance(v, (int, float)) or re.fullmatch(r"\d+(\.\d+)?", str(v)):
            n = float(v)
            if n > 1e12:
                n /= 1000
            return datetime.fromtimestamp(n, tz=timezone.utc)
        s = str(v).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds") if dt else None


def hook_from(text: str | None, limit: int = 140) -> str:
    """The opening line of a caption or title is usually the hook."""
    if not text:
        return ""
    line = re.split(r"[\r\n]+", text.strip())[0]
    line = re.sub(r"(\s#[\wÀ-￿]+)+\s*$", "", line).strip()  # drop trailing hashtags
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def hashtags_from(text: str | None) -> list[str]:
    return sorted({h.lower() for h in re.findall(r"#([\wÀ-￿]+)", text or "")})


def make_item(**kw) -> dict:
    """The one shape every platform is normalised into."""
    item = {
        "id": None,
        "platform": None,      # youtube | tiktok | instagram
        "source": None,        # chart | creative_center | watchlist
        "list": None,          # culture | brands | trending
        "url": None,
        "title": "",
        "hook": "",
        "author": "",
        "author_followers": None,
        "thumbnail": None,
        "published": None,
        "duration_s": None,
        "is_short": None,
        "views": None,
        "likes": None,
        "comments": None,
        "shares": None,
        "rank": None,
        "hashtags": [],
        "sound": None,         # {id, name, artist, original, trending}
        "lang_hint": None,     # the platform's own language code, if it gives one
        "category": None,      # YouTube category id, e.g. "10" music
    }
    item.update({k: v for k, v in kw.items() if k in item})
    if not item["hook"]:
        item["hook"] = hook_from(item["title"])
    return item
