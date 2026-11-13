"""Rules-based shortlist: no AI, rebuilt every run from the numbers.

Ranks formats by how widely they're being used and how well they're landing, then pulls the best
examples, the sounds on the rise and the brand posts that beat their usual numbers.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from math import log1p
from statistics import median

from . import common

import re

NOT_BORROWABLE = {"Other", "Music video", "Trailer", "Long form show clip", "Gaming clip"}
GENERIC_SOUND = re.compile(r"^(original sound|original audio|som original|sonido original|son original|"
                           r"suono originale|originalton|оригинальный звук)", re.I)


def _fmt_x(v: float | None) -> str:
    return f"{v:.1f}×" if v is not None else ""


def build(items: list[dict], sounds: list[dict], limit: int = 5) -> dict:
    groups = defaultdict(list)
    for it in items:
        if it.get("format") and it["format"] not in NOT_BORROWABLE:
            groups[it["format"]].append(it)

    formats = []
    for fmt, vids in groups.items():
        accounts = {v["author"].lower() for v in vids}
        if len(vids) < 2 or len(accounts) < 2:
            continue
        heats = [v.get("heat") or 0 for v in vids]
        surprises = [v["vs_usual"] for v in vids if v.get("vs_usual") is not None]
        rising = sum(1 for v in vids if v.get("rising"))
        best_x = max(surprises, default=None)
        score = median(heats) * log1p(len(accounts)) * (1 + 0.15 * min(rising, 5))
        shelf = Counter(v.get("shelf") for v in vids).most_common(1)[0][0]
        platforms = sorted({v["platform"] for v in vids})
        bits = [f"{len(vids)} videos from {len(accounts)} accounts"]
        if best_x and best_x >= 1.5:
            bits.append(f"the best did {_fmt_x(best_x)} its account's usual views")
        if rising:
            bits.append(f"{rising} still rising")
        examples = sorted(vids, key=lambda v: -(v.get("heat") or 0))[:3]
        formats.append({
            "format": fmt, "shelf": shelf, "score": round(score, 1), "videos": len(vids),
            "accounts": len(accounts), "rising": rising, "best_vs_usual": best_x,
            "median_heat": round(median(heats)), "platforms": platforms,
            "summary": "; ".join(bits).capitalize() + ".",
            "examples": [{"id": e["id"], "url": e["url"], "author": e["author"], "platform": e["platform"],
                          "hook": e["hook"], "heat": e.get("heat"), "vs_usual": e.get("vs_usual")}
                         for e in examples],
        })
    formats.sort(key=lambda f: -f["score"])

    cc = sorted([s for s in sounds if s.get("source") == "creative_center"], key=lambda s: s.get("rank") or 999)
    rising_sounds = [s for s in cc if s.get("trend") == "rising"][:5]
    if not rising_sounds and not any(s.get("trend") for s in cc):  # no direction data: show the top of the chart
        rising_sounds = cc[:5]
    spreading = [s for s in sounds if s.get("source") == "radar" and not s.get("original")
                 and not GENERIC_SOUND.match(s.get("name") or "")][:3]

    brands = [i for i in items if i.get("list") == "brands" and (i.get("vs_usual") or 0) >= 1.5]
    brands.sort(key=lambda i: -(i["vs_usual"]))

    return {
        "kind": "rules",
        "built_at": common.iso(common.NOW),
        "formats": formats[:limit],
        "sounds": [{"name": s["name"], "artist": s.get("artist"), "platform": s["platform"],
                    "note": (f"#{s['rank']} on TikTok's UK sound chart"
                             + (", rising" if s.get("trend") == "rising" else "")
                             + (f", {s['uses']:,} videos" if s.get("uses") else "")
                             if s.get("source") == "creative_center"
                             else f"Used by {len(s['accounts'])} watchlist accounts"),
                    "url": s.get("url") or (s.get("examples") or [{}])[0].get("url")}
                   for s in rising_sounds + spreading],
        "brand_standouts": [{"url": b["url"], "author": b["author"], "platform": b["platform"],
                             "hook": b["hook"], "format": b.get("format"), "vs_usual": b["vs_usual"]}
                            for b in brands[:4]],
    }
