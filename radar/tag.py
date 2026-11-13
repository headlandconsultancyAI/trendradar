"""Format tagging. Claude does it properly; keyword rules are the fallback when there's no API key.

Each format carries a "shelf" so the dashboard can split fast memes from durable formats:
  fast meme       lives for a week or two, needs a quick turnaround
  durable format  a structure you can reuse for months, safe for slower sign-off
"""
from __future__ import annotations

import json
import os
import re

from . import common
from .common import log

FORMATS = {
    "POV":                    ("fast meme",      r"\bpov\b"),
    "Trend or meme template": ("fast meme",      r"\b(trend|meme|when you|me when|nobody:|tell me without)\b"),
    "Challenge or dance":     ("fast meme",      r"\b(challenge|dance)\b"),
    "Duet, stitch or remix":  ("fast meme",      r"\b(duet|stitch|remix)\b"),
    "Reaction":               ("fast meme",      r"\b(react|reaction|reacts)\b"),
    "Skit or sketch":         ("durable format", r"\b(skit|sketch|parody)\b"),
    "Street interview":       ("durable format", r"\b(asked|asking|street interview|vox pop|strangers|public)\b"),
    "Talking head explainer": ("durable format", r"\b(explained|explain|why|what is|the truth about|here's how)\b"),
    "Tutorial or how to":     ("durable format", r"\b(how to|tutorial|tips|hack|step by step|recipe)\b"),
    "Day in the life":        ("durable format", r"\b(day in the life|ditl|a day with|24 hours)\b"),
    "Behind the scenes":      ("durable format", r"\b(behind the scenes|bts|how we|inside)\b"),
    "Before and after":       ("durable format", r"\b(before and after|transformation|glow up|how it started)\b"),
    "Ranking or listicle":    ("durable format", r"\b(ranking|ranked|top \d+|tier list|\d+ things)\b"),
    "Challenge or test":      ("durable format", r"\b(taste test|blind test|we tried|i tried|trying|versus)\b"),
    "Long form show clip":    ("durable format", r"\b(episode|ep\.?\s?\d+|full video|podcast|clip)\b"),
    "Music video":            ("durable format", r"\b(official (music )?video|official audio|lyric video|ft\.|feat\.)\b"),
    "Trailer":                ("durable format", r"\b(trailer|teaser)\b"),
    "Gaming clip":            ("durable format", r"$^"),
    "Other":                  ("durable format", r"$^"),
}
FORMAT_NAMES = list(FORMATS)


YT_CATEGORY = {"10": "Music video", "1": "Trailer", "30": "Trailer", "44": "Trailer", "20": "Gaming clip"}
CHART = {"Music": "Music video", "Film trailers": "Trailer", "Gaming": "Gaming clip"}


def keyword_tag(item: dict) -> dict:
    fixed = CHART.get(item.get("chart")) or YT_CATEGORY.get(str(item.get("category") or ""))
    if item.get("platform") == "youtube" and fixed:
        return {"format": fixed, "shelf": FORMATS[fixed][0], "why": "", "tagged_by": "keywords"}
    text = f"{item.get('title', '')} {' '.join(item.get('hashtags') or [])}".lower()
    for name, (shelf, pattern) in FORMATS.items():
        if re.search(pattern, text):
            return {"format": name, "shelf": shelf, "why": "", "tagged_by": "keywords"}
    if item.get("platform") == "youtube" and not item.get("is_short"):
        return {"format": "Long form show clip", "shelf": "durable format", "why": "", "tagged_by": "keywords"}
    return {"format": "Other", "shelf": "durable format", "why": "", "tagged_by": "keywords"}


def parse_json(text: str):
    """Pull the first JSON object or array out of a model response."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start = min([i for i in (text.find("["), text.find("{")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON in response")
    return json.loads(text[start:])


TAG_PROMPT = """You label short-form and YouTube videos by creative FORMAT, for a comms agency \
looking for formats its corporate and B2B clients could borrow.

Allowed formats (use these names exactly): {formats}

For each video return:
- "format": the single best fit
- "shelf": "fast meme" if it rides a short-lived trend, sound or joke that will feel dated in two weeks; \
"durable format" if the structure is reusable for months
- "why": one plain sentence on what makes it work creatively (the hook, the structure, the twist). \
No hype words. Under 20 words.

Return ONLY a JSON array: [{{"id": "...", "format": "...", "shelf": "...", "why": "..."}}]

Videos:
{videos}"""


def claude_tag(items: list[dict], model: str, batch: int = 30) -> dict[str, dict]:
    import anthropic

    client = anthropic.Anthropic()
    out = {}
    for i in range(0, len(items), batch):
        chunk = items[i:i + batch]
        lines = [json.dumps({
            "id": it["id"], "platform": it["platform"], "author": it["author"],
            "text": (it.get("title") or "")[:400], "hashtags": (it.get("hashtags") or [])[:8],
            "sound": (it.get("sound") or {}).get("name"), "seconds": it.get("duration_s"),
        }, ensure_ascii=False) for it in chunk]
        prompt = TAG_PROMPT.format(formats=", ".join(FORMAT_NAMES), videos="\n".join(lines))
        try:
            msg = client.messages.create(model=model, max_tokens=4000,
                                         messages=[{"role": "user", "content": prompt}])
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            for row in parse_json(text):
                if row.get("format") not in FORMATS:
                    row["format"] = "Other"
                if row.get("shelf") not in ("fast meme", "durable format"):
                    row["shelf"] = FORMATS[row["format"]][0]
                out[row["id"]] = {"format": row["format"], "shelf": row["shelf"],
                                  "why": row.get("why", ""), "tagged_by": "claude"}
                common.CLAUDE["tagged"] += 1
        except Exception as e:  # keep going; untagged items fall back to keywords
            common.claude_error("Format tagging", e)
            if i == 0 and not out:  # first batch failed outright: same error will repeat, stop here
                break
    return out


def tag_all(items: list[dict], cache: dict, model: str) -> dict:
    """Tags new items only (cached by id), so each video is sent to Claude once."""
    todo = [it for it in items if cache.get(it["id"], {}).get("tagged_by") != "claude"]
    if todo and os.environ.get("ANTHROPIC_API_KEY"):
        log.info("Tagging %d new videos with %s", len(todo), model)
        cache.update(claude_tag(todo, model))
    for it in items:
        t = cache.get(it["id"]) or keyword_tag(it)
        cache.setdefault(it["id"], t)
        it.update(t)
    live = {it["id"] for it in items}
    return {k: v for k, v in cache.items() if k in live}
