"""Scoring: views per hour, how a video compares with the account's usual, momentum between runs.

"heat" (0-100) is what the dashboard sorts by. It blends:
  - speed:     views per hour since posting, ranked within the platform
  - surprise:  views vs the same account's typical video (a format that worked, not just a big account)
  - momentum:  whether views per hour picked up since the last run
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from statistics import median

from . import common
from .common import parse_time


def _pct_ranks(values: list[float]) -> list[float]:
    """Percentile rank 0-100 for each value (ties share a rank)."""
    if not values:
        return []
    order = sorted(values)
    n = len(order)
    out = []
    for v in values:
        below = sum(1 for x in order if x < v)
        equal = sum(1 for x in order if x == v)
        out.append(100.0 * (below + 0.5 * equal) / n)
    return out


def merge_duplicates(items: list[dict]) -> list[dict]:
    """The same TikTok can come from Creative Center and a watchlist. Keep one, richer copy."""
    by_id: dict[str, dict] = {}
    for it in items:
        cur = by_id.get(it["id"])
        if cur is None:
            by_id[it["id"]] = it
            continue
        keep, other = (it, cur) if it["source"] == "watchlist" else (cur, it)
        for k, v in other.items():
            if keep.get(k) in (None, "", []) and v not in (None, "", []):
                keep[k] = v
        keep["views"] = max(filter(None, [keep.get("views"), other.get("views")]), default=None)
        keep["also_trending"] = True
        by_id[it["id"]] = keep
    return list(by_id.values())


def score(items: list[dict], history: dict) -> list[dict]:
    now = common.NOW
    items = merge_duplicates(items)

    # baseline views per account, from watchlist pulls
    per_author = defaultdict(list)
    for it in items:
        if it["source"] == "watchlist" and it.get("views") is not None:
            per_author[(it["platform"], it["author"].lower())].append(it["views"])

    for it in items:
        pub = parse_time(it.get("published"))
        hrs = max(1.0, (now - pub).total_seconds() / 3600) if pub else None
        it["hours_live"] = round(hrs, 1) if hrs else None
        it["velocity"] = round(it["views"] / hrs, 1) if hrs and it.get("views") is not None else None

        base = per_author.get((it["platform"], it["author"].lower()), [])
        if len(base) >= 3 and it.get("views") is not None and median(base) > 0:
            it["vs_usual"] = round(it["views"] / median(base), 2)
        else:
            it["vs_usual"] = None

        eng = sum(x or 0 for x in (it.get("likes"), it.get("comments"), it.get("shares")))
        it["engagement_rate"] = round(100 * eng / it["views"], 2) if it.get("views") else None

        # momentum: views per hour since last run vs lifetime views per hour
        h = history.get(it["id"])
        it["momentum"] = None
        if h and it.get("views") is not None and it.get("velocity"):
            last_t = parse_time(h.get("t"))
            dt = (now - last_t).total_seconds() / 3600 if last_t else 0
            if dt >= 2 and h.get("views") is not None:
                recent = max(0, it["views"] - h["views"]) / dt
                it["momentum"] = round(recent / it["velocity"], 2)
        it["first_seen"] = (h or {}).get("first_seen") or common.iso(now)

    # heat, calculated per platform so TikTok's bigger numbers don't drown out the rest
    for plat in {it["platform"] for it in items}:
        group = [it for it in items if it["platform"] == plat]
        timed = [it for it in group if it["velocity"] is not None]
        speed = dict(zip((id(x) for x in timed), _pct_ranks([x["velocity"] for x in timed])))
        surp_items = [it for it in group if it["vs_usual"] is not None]
        surprise = dict(zip((id(x) for x in surp_items), _pct_ranks([x["vs_usual"] for x in surp_items])))
        for it in group:
            if id(it) in speed:
                parts = [(speed[id(it)], 0.55)]
                if id(it) in surprise:
                    parts.append((surprise[id(it)], 0.35))
                if it["momentum"] is not None:
                    parts.append((min(100, 50 * it["momentum"]), 0.10))
                total_w = sum(w for _, w in parts)
                it["heat"] = round(sum(v * w for v, w in parts) / total_w)
            elif it.get("rank"):  # Creative Center items with no post time: use chart rank
                it["heat"] = max(5, 90 - 2 * (it["rank"] - 1))
            else:
                it["heat"] = 0

    for it in items:
        young = it["hours_live"] is not None and it["hours_live"] <= 72
        it["rising"] = bool(
            (it["momentum"] is not None and it["momentum"] >= 0.9 and (it["hours_live"] or 0) <= 24 * 7)
            or (young and it["heat"] >= 70)
            or (it.get("cc_trend") == "rising")
        )
        fs = parse_time(it["first_seen"])
        # on the very first run everything is "new", so only flag it once there's history
        it["new_today"] = bool(history and fs and now - fs <= timedelta(hours=26))
    return items


def update_history(items: list[dict], history: dict, keep_days: int = 21) -> dict:
    now = common.NOW
    for it in items:
        prev = history.get(it["id"], {})
        history[it["id"]] = {"views": it.get("views"), "t": common.iso(now),
                             "first_seen": prev.get("first_seen") or it["first_seen"]}
    cutoff = now - timedelta(days=keep_days)
    return {k: v for k, v in history.items() if (parse_time(v.get("t")) or now) >= cutoff}


def aggregate_sounds(items: list[dict], cc_sounds: list[dict]) -> list[dict]:
    """Group videos by the sound they use. Original audio is skipped unless it has an id
    (a reused original sound is often how a meme spreads)."""
    groups: dict[tuple, dict] = {}
    for it in items:
        s = it.get("sound") or {}
        if not s.get("name") and not s.get("id"):
            continue
        if s.get("original") and not s.get("id"):
            continue
        name = (s.get("name") or "").lower()
        is_orig = s.get("original") or name.startswith("original")
        key = (it["platform"], (s.get("id") or name) if is_orig else (name or s.get("id")))
        g = groups.setdefault(key, {
            "platform": it["platform"], "source": "radar", "id": s.get("id"),
            "name": s.get("name") or "Untitled sound", "artist": s.get("artist") or "",
            "uses": 0, "views": 0, "accounts": set(), "examples": [], "trending": False,
            "original": bool(s.get("original")), "heat_sum": 0,
        })
        g["uses"] += 1
        g["views"] += it.get("views") or 0
        g["accounts"].add(it["author"])
        g["heat_sum"] += it.get("heat") or 0
        g["trending"] = g["trending"] or bool(s.get("trending"))
        g["examples"].append({"url": it["url"], "author": it["author"], "heat": it.get("heat")})

    radar = []
    for g in groups.values():
        g["accounts"] = sorted(g["accounts"])
        g["examples"] = sorted(g["examples"], key=lambda e: -(e["heat"] or 0))[:3]
        g["avg_heat"] = round(g.pop("heat_sum") / g["uses"])
        # only interesting if several accounts use it, or Instagram flags it as trending
        if len(g["accounts"]) >= 2 or g["trending"]:
            radar.append(g)
    radar.sort(key=lambda g: (-len(g["accounts"]), -g["avg_heat"]))

    names_in_radar = {g["name"].lower() for g in radar}
    for s in cc_sounds:
        s["also_in_watchlist"] = s["name"].lower() in names_in_radar
    return cc_sounds + radar
