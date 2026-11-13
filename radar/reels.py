"""Instagram Reels: there's no public trending feed, so we build one from watchlist accounts."""
from __future__ import annotations

from datetime import timedelta

from . import common
from .apify import run_actor
from .common import first, hashtags_from, log, make_item, parse_time, to_int


def normalise(r: dict, list_name: str) -> dict:
    code = first(r, "shortCode", "code", default="")
    caption = r.get("caption") or ""
    music = r.get("musicInfo") or r.get("music") or {}
    original = first(music, "uses_original_audio", "usesOriginalAudio")
    return make_item(
        id=f"ig:{first(r, 'id', 'pk', default=code)}",
        platform="instagram",
        source="watchlist",
        list=list_name,
        url=first(r, "url", default=f"https://www.instagram.com/reel/{code}/"),
        title=caption,
        author="@" + str(first(r, "ownerUsername", ("owner", "username"), default="")),
        author_followers=to_int(first(r, "ownerFollowersCount", ("owner", "followersCount"))),
        thumbnail=first(r, "displayUrl", "thumbnailUrl", "imageUrl"),
        published=common.iso(parse_time(first(r, "timestamp", "takenAt", "taken_at"))),
        duration_s=to_int(first(r, "videoDuration", "duration")),
        is_short=True,
        views=to_int(first(r, "videoPlayCount", "playCount", "videoViewCount", "viewCount")),
        likes=to_int(first(r, "likesCount", "likeCount")),
        comments=to_int(first(r, "commentsCount", "commentCount")),
        hashtags=[h.lower() for h in (r.get("hashtags") or [])] or hashtags_from(caption),
        sound={
            "id": str(first(music, "audio_id", "audioId", "audio_canonical_id", default="")) or None,
            "name": "Original audio" if original else first(music, "song_name", "songName", "title"),
            "artist": first(music, "artist_name", "artistName"),
            "original": bool(original) if original is not None else None,
            "trending": first(r, "audio_is_trending", ("musicInfo", "is_trending")),
        } if music else None,
    )


def fetch(cfg: dict) -> tuple[list[dict], list[str]]:
    out, missing = [], []
    cutoff = common.NOW - timedelta(days=cfg.get("lookback_days", 10))
    actor = cfg["actors"]["instagram_reels"]
    for list_name in ("culture", "brands"):
        handles = cfg["instagram"].get(list_name) or []
        if not handles:
            continue
        rows = run_actor(actor, {"username": handles, "resultsLimit": cfg.get("per_account", 12)})
        seen = set()
        for r in rows:
            if r.get("error"):
                continue
            it = normalise(r, list_name)
            seen.add(it["author"].lstrip("@").lower())
            pub = parse_time(it["published"])
            if pub is None or pub >= cutoff:
                out.append(it)
        missing += [f"instagram:{h}" for h in handles if h.lower() not in seen]
    log.info("Instagram: %d reels", len(out))
    return out, missing
