"""YouTube: regional charts plus recent uploads from watchlist channels.

Quota: each call below costs 1 unit, so a daily run uses well under 100 of the free 10,000.

Shorts are filtered out when youtube.exclude_shorts is on. The API has no "is this a Short" field,
and duration alone can't tell (Shorts run up to 3 minutes, and so do plenty of trailers), so:
  - watchlist channels are read from YouTube's long-form uploads list where one exists
  - every video of 3 minutes or less is checked against youtube.com/shorts/<id>, which answers
    directly for a Short and redirects to /watch for anything else
  - if that check can't get an answer, a video is treated as a Short when it's 60 seconds or
    less or tagged #shorts
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import requests

from .common import first, get, log, make_item, parse_time, to_int
from . import common

API = "https://www.googleapis.com/youtube/v3/"

# What the Shorts filter did this run, shown in the dashboard footer
SHORTS = {"enabled": False, "removed": 0, "guessed": 0, "examples": []}


def _call(endpoint: str, **params) -> dict:
    key = os.environ.get("YOUTUBE_API_KEY")
    params["key"] = key
    try:
        r = requests.get(API + endpoint, params=params, timeout=30)
    except requests.RequestException as e:
        log.error("YouTube %s failed: %s", endpoint, e)
        return {}
    if r.status_code >= 400:
        log.warning("YouTube %s %s: %s", endpoint, r.status_code, r.text[:200])
        return {}
    return r.json()


def _duration_s(iso: str | None) -> int | None:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def normalise(v: dict, source: str, list_name: str, followers: int | None = None) -> dict:
    sn, st = v.get("snippet", {}), v.get("statistics", {})
    dur = _duration_s(get(v, "contentDetails", "duration"))
    vid = v.get("id") if isinstance(v.get("id"), str) else get(v, "id", "videoId")
    thumbs = sn.get("thumbnails", {})
    thumb = first(thumbs, ("maxres", "url"), ("high", "url"), ("medium", "url"), ("default", "url"))
    is_short = dur is not None and dur <= 180  # "could be a Short"; settled by check_shorts()
    return make_item(
        id=f"yt:{vid}",
        platform="youtube",
        source=source,
        list=list_name,
        url=f"https://www.youtube.com/{'shorts/' if is_short else 'watch?v='}{vid}",
        title=sn.get("title", ""),
        author=sn.get("channelTitle", ""),
        author_followers=followers,
        thumbnail=thumb,
        published=common.iso(parse_time(sn.get("publishedAt"))),
        duration_s=dur,
        is_short=is_short,
        views=to_int(st.get("viewCount")),
        likes=to_int(st.get("likeCount")),
        comments=to_int(st.get("commentCount")),
        hashtags=[t.lower() for t in sn.get("tags", [])[:8]],
        lang_hint=sn.get("defaultAudioLanguage") or sn.get("defaultLanguage"),
        category=sn.get("categoryId"),
    )


def _shorts_page(vid: str) -> bool | None:
    """True if YouTube serves this id as a Short, False if it redirects to /watch, None if unsure."""
    try:
        r = requests.head(f"https://www.youtube.com/shorts/{vid}", allow_redirects=False, timeout=15,
                          headers={"User-Agent": "Mozilla/5.0 (trend-radar)"})
    except requests.RequestException:
        return None
    if r.status_code == 200:
        return True
    if r.status_code in (301, 302, 303, 307, 308):
        loc = r.headers.get("location", "")
        if "consent." in loc or "accounts." in loc:  # cookie or sign-in wall: no answer
            return None
        return False
    return None


def _looks_short(it: dict) -> bool:
    text = f"{it.get('title', '')} {' '.join(it.get('hashtags') or [])}".lower()
    return (it.get("duration_s") or 999) <= 60 or "#shorts" in text or "shorts" in (it.get("hashtags") or [])


def check_shorts(items: list[dict]) -> list[dict]:
    """Settles is_short for every YouTube video and fixes its link."""
    maybe = [it for it in items if it.get("duration_s") is not None and it["duration_s"] <= 180]
    ids = [it["id"].split(":", 1)[1] for it in maybe]
    with ThreadPoolExecutor(max_workers=8) as pool:
        answers = list(pool.map(_shorts_page, ids))
    guessed = 0
    for it, vid, ans in zip(maybe, ids, answers):
        if ans is None:
            ans, guessed = _looks_short(it), guessed + 1
        it["is_short"] = ans
    for it in items:
        if it.get("duration_s") is None or it["duration_s"] > 180:
            it["is_short"] = False
        vid = it["id"].split(":", 1)[1]
        it["url"] = f"https://www.youtube.com/{'shorts/' if it['is_short'] else 'watch?v='}{vid}"
    SHORTS["guessed"] += guessed
    if maybe and guessed == len(maybe):
        log.warning("Couldn't reach youtube.com/shorts for any video; Shorts judged on length and #shorts only")
    return items


def fetch_charts(cfg: dict) -> list[dict]:
    out = []
    for cat_id, label in (cfg["youtube"].get("chart_categories") or {}).items():
        params = dict(part="snippet,statistics,contentDetails", chart="mostPopular",
                      regionCode=cfg["region"], maxResults=50)
        if str(cat_id) != "0":
            params["videoCategoryId"] = str(cat_id)
        data = _call("videos", **params)
        for rank, v in enumerate(data.get("items", []), 1):
            it = normalise(v, "chart", "trending")
            it["rank"] = rank
            it["chart"] = label
            out.append(it)
        log.info("YouTube chart %s: %d", label, len(data.get("items", [])))
    return out


def fetch_channels(cfg: dict) -> tuple[list[dict], list[str]]:
    out, missing = [], []
    cutoff = common.NOW - timedelta(days=cfg.get("lookback_days", 10))
    for list_name in ("culture", "brands"):
        for handle in cfg["youtube"].get(list_name) or []:
            ch = _call("channels", part="contentDetails,statistics", forHandle=handle)
            items = ch.get("items") or []
            if not items:
                missing.append(f"youtube:{handle}")
                continue
            uploads = get(items[0], "contentDetails", "relatedPlaylists", "uploads")
            subs = to_int(get(items[0], "statistics", "subscriberCount"))
            n = min(50, cfg.get("per_account", 12))
            pl = {}
            if SHORTS["enabled"] and uploads and uploads.startswith("UU"):
                # "UULF..." is the channel's long-form uploads, with Shorts and live streams left out
                pl = _call("playlistItems", part="contentDetails", playlistId="UULF" + uploads[2:], maxResults=n)
            if not pl.get("items"):
                pl = _call("playlistItems", part="contentDetails", playlistId=uploads, maxResults=n)
            ids = [get(p, "contentDetails", "videoId") for p in pl.get("items", [])]
            ids = [i for i in ids if i]
            if not ids:
                continue
            vids = _call("videos", part="snippet,statistics,contentDetails", id=",".join(ids))
            for v in vids.get("items", []):
                it = normalise(v, "watchlist", list_name, subs)
                pub = parse_time(it["published"])
                if pub and pub >= cutoff:
                    out.append(it)
    return out, missing


def fetch(cfg: dict) -> tuple[list[dict], list[str]]:
    if not os.environ.get("YOUTUBE_API_KEY"):
        log.warning("YOUTUBE_API_KEY not set, skipping YouTube")
        return [], []
    SHORTS["enabled"] = bool(cfg["youtube"].get("exclude_shorts", True))
    charts = fetch_charts(cfg)
    chans, missing = fetch_channels(cfg)
    items = charts + chans
    if SHORTS["enabled"]:
        items = drop_shorts(check_shorts(items))
    return items, missing


def drop_shorts(items: list[dict]) -> list[dict]:
    kept = [it for it in items if not it.get("is_short")]
    gone = [it for it in items if it.get("is_short")]
    SHORTS["removed"] += len(gone)
    SHORTS["examples"] += [{"url": it["url"], "author": it["author"], "text": it["title"][:120],
                            "seconds": it.get("duration_s")} for it in gone[:40 - len(SHORTS["examples"])]]
    log.info("YouTube Shorts filter: kept %d, removed %d (%d judged without YouTube's answer)",
             len(kept), len(gone), SHORTS["guessed"])
    return kept
