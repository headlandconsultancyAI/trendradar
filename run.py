"""Trend Radar daily run.

  python run.py              live run (needs YOUTUBE_API_KEY, APIFY_TOKEN, optional ANTHROPIC_API_KEY)
  python run.py --digest     also force the weekly digest (otherwise it runs on Mondays)
  python run.py --offline    run on the sample fixtures in tests/fixtures, no keys needed
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from radar import common, digest, language, reels, score, shortlist, tag, tiktok, youtube

ROOT = Path(__file__).parent
DATA = ROOT / "docs" / "data"
FIX = ROOT / "tests" / "fixtures"


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=list))


def fetch_live(cfg):
    yt, yt_missing = youtube.fetch(cfg)
    tt, cc_sounds, cc_tags, tt_missing = tiktok.fetch(cfg)
    ig, ig_missing = reels.fetch(cfg)
    return yt + tt + ig, cc_sounds, cc_tags, yt_missing + tt_missing + ig_missing


def fetch_offline(cfg):
    common.set_now(datetime.fromisoformat(load(FIX / "meta.json", {})["now"]))
    yt = [youtube.normalise(v, "chart", "trending") | {"rank": i + 1, "chart": "All"}
          for i, v in enumerate(load(FIX / "youtube_chart.json", []))]
    yt += [youtube.normalise(v, "watchlist", v.pop("_list"), v.pop("_subs"))
           for v in load(FIX / "youtube_watchlist.json", [])]
    tt = [tiktok.normalise_cc_video(r) for r in load(FIX / "tiktok_cc_videos.json", [])]
    tt += [tiktok.normalise_profile_video(r, r.pop("_list")) for r in load(FIX / "tiktok_profiles.json", [])]
    ig = [reels.normalise(r, r.pop("_list")) for r in load(FIX / "instagram_reels.json", [])]
    sounds = [tiktok.normalise_cc_sound(r) for r in load(FIX / "tiktok_cc_sounds.json", [])]
    tags = [tiktok.normalise_cc_hashtag(r) for r in load(FIX / "tiktok_cc_hashtags.json", [])]
    return yt + tt + ig, sounds, tags, ["instagram:example_typo_handle"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--digest", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = common.log

    cfg = yaml.safe_load((ROOT / "watchlist.yaml").read_text())
    # offline runs use a seeded history and never touch the real history or tag cache
    history = load(FIX / "history_seed.json", {}) if args.offline else load(DATA / "history.json", {})
    tag_cache = {} if args.offline else load(DATA / "tags.json", {})

    items, cc_sounds, cc_tags, missing = (fetch_offline if args.offline else fetch_live)(cfg)
    if not items:
        log.error("No videos fetched at all. Check your keys and the log above. Keeping old data.")
        raise SystemExit(1)

    dropped = []
    if cfg.get("english_only", True):
        items, dropped = language.filter_english(items)

    common.CLAUDE["key_set"] = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    if not common.CLAUDE["key_set"] and not args.offline:
        log.info("No ANTHROPIC_API_KEY: formats tagged by keyword rules; the dashboard uses the rules-based shortlist")

    items = score.score(items, history)
    tag_cache = tag.tag_all(items, tag_cache, cfg["claude"]["tagging_model"])
    sounds = score.aggregate_sounds(items, cc_sounds)
    items.sort(key=lambda i: -(i.get("heat") or 0))
    short = shortlist.build(items, sounds)

    # weekly digest: Mondays, on request, or the first time there's a key
    existing = load(DATA / "digest.json", None)
    want_digest = args.digest or common.NOW.weekday() == 0 or existing is None
    dg = existing
    if args.offline:
        dg = digest.attach_examples(load(FIX / "digest_sample.json", {}), items)
    elif want_digest and common.CLAUDE["key_set"]:
        log.info("Writing weekly digest")
        new = digest.build(items, sounds, cfg["claude"]["digest_model"])
        if new:
            dg = new
            save(DATA / "digests" / f"{new['week_of']}.json", new)

    out = {
        "generated_at": common.iso(common.NOW),
        "sample": args.offline,
        "region": cfg["region"],
        "cc_period": (cfg["tiktok"].get("creative_center") or {}).get("period_days", 7),
        "counts": {p: sum(1 for i in items if i["platform"] == p) for p in ("youtube", "tiktok", "instagram")},
        "missing_handles": missing,
        "items": items,
        "sounds": sounds,
        "hashtags": cc_tags,
        "digest": dg,
        "shortlist": short,
        "digest_page_url": cfg.get("digest_page_url") or None,
        "language_filter": {"enabled": cfg.get("english_only", True), "removed": len(dropped),
                            "examples": dropped[:40]},
        "claude": {**common.CLAUDE, "offline": args.offline,
                   "tagged_by_claude": sum(1 for i in items if i.get("tagged_by") == "claude")},
    }
    save(DATA / "radar.json", out)
    if not args.offline:
        from radar.apify import SAMPLES
        save(DATA / "debug_samples.json", SAMPLES)
        save(DATA / "history.json", score.update_history(items, history))
        save(DATA / "tags.json", tag_cache)
        if dg:
            save(DATA / "digest.json", dg)
    log.info("Done: %d videos, %d sounds. Missing handles: %s", len(items), len(sounds), missing or "none")


if __name__ == "__main__":
    main()
