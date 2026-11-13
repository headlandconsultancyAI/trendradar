"""TikTok: Creative Center trends for the region, plus recent videos from watchlist accounts."""
from __future__ import annotations

from datetime import timedelta

from . import common
from .apify import run_actor
from .common import first, get, hashtags_from, log, make_item, parse_time, to_int


# ---------- Creative Center (TikTok's own trend data) ----------

def normalise_cc_video(r: dict) -> dict:
    vid = str(first(r, "videoId", "id", default=""))
    desc = first(r, "videoDesc", "name", "title", default="")
    handle = str(first(r, "authorHandle", ("author", "uniqueId"), default="")).lstrip("@")
    return make_item(
        id=f"tt:{vid}",
        platform="tiktok",
        source="creative_center",
        list="trending",
        url=first(r, "videoUrl", "url", default=f"https://www.tiktok.com/@{handle}/video/{vid}"),
        title=desc,
        author=f"@{handle}" if handle else "",
        thumbnail=first(r, "videoCoverUrl", "coverUrl", "cover"),
        published=common.iso(parse_time(first(r, "createTime", "createTimeISO", "publishedAt"))),
        views=to_int(first(r, "playCount", "videoViews", "views")),
        likes=to_int(first(r, "likeCountVideo", "likeCount", "diggCount")),
        comments=to_int(first(r, "commentCount")),
        shares=to_int(first(r, "shareCount")),
        rank=to_int(r.get("rank")),
        hashtags=[h.lstrip("#").lower() for h in (r.get("hashtags") or [])] or hashtags_from(desc),
        sound={"id": None, "name": r.get("soundName"), "artist": None, "original": None,
               "trending": None} if r.get("soundName") else None,
        lang_hint=first(r, "textLanguage", "language"),
    ) | {"cc_trend": r.get("trend")}


def normalise_cc_sound(r: dict) -> dict:
    return {
        "platform": "tiktok",
        "source": "creative_center",
        "id": str(first(r, "musicId", "soundId", "id", default=r.get("name", ""))),
        "name": first(r, "name", "title", "soundName", default=""),
        "artist": first(r, "author", "artist", "authorName", default=""),
        "rank": to_int(r.get("rank")),
        "uses": to_int(first(r, "publishedVideoCount", "videoCount", "uses")),
        "views": to_int(first(r, "videoViews", "views")),
        "trend": r.get("trend"),
        "url": first(r, "linkedVideoUrl", "url", "playUrl"),
        "cover": first(r, "coverUrl", "cover"),
        "commercial": r.get("isCommercial") if "isCommercial" in r else r.get("commercialUse"),
    }


def normalise_cc_hashtag(r: dict) -> dict:
    return {
        "platform": "tiktok",
        "name": str(first(r, "name", "hashtag", default="")).lstrip("#"),
        "rank": to_int(r.get("rank")),
        "posts": to_int(first(r, "publishedVideoCount", "videoCount")),
        "views": to_int(first(r, "videoViews", "views")),
        "trend": r.get("trend"),
    }


def fetch_creative_center(cfg: dict) -> tuple[list, list, list]:
    cc = cfg["tiktok"].get("creative_center") or {}
    actor = cfg["actors"]["tiktok_trends"]
    period = cc.get("period_days", 7)

    def run(kind, n):
        if not n:
            return []
        return run_actor(actor, {"trendType": kind, "countryCode": cfg["region"],
                                 "period": period, "maxResults": n})

    videos = [normalise_cc_video(r) for r in run("video", cc.get("videos", 50))]
    sounds = [normalise_cc_sound(r) for r in run("sound", cc.get("sounds", 50))]
    tags = [normalise_cc_hashtag(r) for r in run("hashtag", cc.get("hashtags", 30))]
    return videos, sounds, tags


# ---------- Watchlist profiles ----------

def normalise_profile_video(r: dict, list_name: str) -> dict:
    vid = str(first(r, "id", "videoId", default=""))
    handle = str(first(r, ("authorMeta", "name"), ("author", "uniqueId"), default="")).lstrip("@")
    text = r.get("text") or r.get("desc") or ""
    music = r.get("musicMeta") or r.get("music") or {}
    return make_item(
        id=f"tt:{vid}",
        platform="tiktok",
        source="watchlist",
        list=list_name,
        url=first(r, "webVideoUrl", "url", default=f"https://www.tiktok.com/@{handle}/video/{vid}"),
        title=text,
        author=f"@{handle}",
        author_followers=to_int(first(r, ("authorMeta", "fans"), ("authorStats", "followerCount"))),
        thumbnail=first(r, ("videoMeta", "coverUrl"), ("video", "cover"), "coverUrl"),
        published=common.iso(parse_time(first(r, "createTimeISO", "createTime"))),
        duration_s=to_int(first(r, ("videoMeta", "duration"), ("video", "duration"))),
        is_short=True,
        views=to_int(first(r, "playCount", ("stats", "playCount"))),
        likes=to_int(first(r, "diggCount", ("stats", "diggCount"))),
        comments=to_int(first(r, "commentCount", ("stats", "commentCount"))),
        shares=to_int(first(r, "shareCount", ("stats", "shareCount"))),
        hashtags=[get(h, "name", default=h) if isinstance(h, dict) else h
                  for h in (r.get("hashtags") or [])] or hashtags_from(text),
        sound={
            "id": str(first(music, "musicId", "id", default="")) or None,
            "name": first(music, "musicName", "title"),
            "artist": first(music, "musicAuthor", "authorName"),
            "original": first(music, "musicOriginal", "original"),
            "trending": None,
        } if music else None,
        lang_hint=first(r, "textLanguage", "language"),
    )


def fetch_profiles(cfg: dict) -> tuple[list[dict], list[str]]:
    out, missing = [], []
    cutoff = common.NOW - timedelta(days=cfg.get("lookback_days", 10))
    actor = cfg["actors"]["tiktok_profiles"]
    for list_name in ("culture", "brands"):
        handles = cfg["tiktok"].get(list_name) or []
        if not handles:
            continue
        rows = run_actor(actor, {
            "profiles": handles,
            "resultsPerPage": cfg.get("per_account", 12),
            "profileScrapeSections": ["videos"],
            "profileSorting": "latest",
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": False,
        })
        seen = set()
        for r in rows:
            it = normalise_profile_video(r, list_name)
            seen.add(it["author"].lstrip("@").lower())
            pub = parse_time(it["published"])
            if pub is None or pub >= cutoff:
                out.append(it)
        missing += [f"tiktok:{h}" for h in handles if h.lower() not in seen]
    return out, missing


def fetch(cfg: dict):
    videos, sounds, tags = fetch_creative_center(cfg)
    prof, missing = fetch_profiles(cfg)
    log.info("TikTok: %d trending, %d watchlist, %d sounds, %d hashtags",
             len(videos), len(prof), len(sounds), len(tags))
    return videos + prof, sounds, tags, missing
