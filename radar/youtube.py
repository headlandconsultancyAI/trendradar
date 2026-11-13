"""YouTube: regional charts plus recent uploads from watchlist channels.

Quota: each call below costs 1 unit, so a daily run uses well under 100 of the free 10,000.
"""
from __future__ import annotations

import os
import re
from datetime import timedelta

import requests

from .common import first, get, log, make_item, parse_time, to_int
from . import common

API = "https://www.googleapis.com/youtube/v3/"


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
    is_short = dur is not None and dur <= 180
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
            pl = _call("playlistItems", part="contentDetails", playlistId=uploads,
                       maxResults=min(50, cfg.get("per_account", 12)))
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
    charts = fetch_charts(cfg)
    chans, missing = fetch_channels(cfg)
    return charts + chans, missing
