"""Weekly digest: Claude reads the week's hottest videos and sounds and picks formats worth borrowing."""
from __future__ import annotations

import json

from . import common
from .common import log
from .tag import parse_json

DIGEST_PROMPT = """You're a creative strategist at a UK comms agency. Most clients are corporate or B2B \
(engineering, finance, infrastructure, professional services, consumer brands with a corporate side). \
The team wants short-form video that feels current without being cringe.

Below are this week's fastest-moving videos (UK charts, TikTok Creative Center and a watchlist of \
culture accounts and brands) plus the sounds picking up. "heat" is 0-100. "vs_usual" is views compared \
with that account's typical video, so a high number means the FORMAT worked, not just a big account.

Pick the 5 formats or trends most worth borrowing this week. Favour things a corporate client could \
actually do. Skip anything that only works for a celebrity, needs a big budget, or would be risky \
for a brand. Spread across platforms where the data allows.

Write like a sharp colleague talking to a friend: plain words, contractions, no buzzwords, no hype, \
no em dashes or en dashes.

Return ONLY JSON:
{{
  "headline": "one sentence on the mood of the week",
  "picks": [
    {{
      "title": "short name for the format or trend",
      "shelf": "fast meme" or "durable format",
      "what_it_is": "one or two sentences",
      "why_its_working": "one or two sentences, grounded in the numbers where you can",
      "client_angle": "how a corporate or B2B client could make their own version, concretely",
      "watch_out": "the risk or how it could go wrong, one sentence",
      "example_ids": ["ids of 1 to 3 videos from the list"]
    }}
  ],
  "sounds_to_watch": [{{"name": "...", "note": "one line on how brands could use it"}}]
}}

Videos:
{videos}

Sounds:
{sounds}"""


def attach_examples(digest: dict, items: list[dict]) -> dict:
    """Swap the ids Claude picked for links the dashboard can show."""
    by_id = {i["id"]: i for i in items}
    for p in digest.get("picks", []):
        ids = p.pop("example_ids", None) or [e.get("id") for e in p.get("examples", [])]
        p["examples"] = [{"id": x, "url": by_id[x]["url"], "author": by_id[x]["author"],
                          "platform": by_id[x]["platform"], "hook": by_id[x]["hook"]}
                         for x in ids if x in by_id]
    return digest


def build(items: list[dict], sounds: list[dict], model: str) -> dict | None:
    import anthropic

    pool = sorted([i for i in items if i.get("heat")], key=lambda i: -i["heat"])[:80]
    vids = [json.dumps({
        "id": i["id"], "platform": i["platform"], "list": i["list"], "author": i["author"],
        "hook": i["hook"][:200], "format": i.get("format"), "shelf": i.get("shelf"),
        "heat": i["heat"], "vs_usual": i.get("vs_usual"), "views": i.get("views"),
        "hours_live": i.get("hours_live"), "sound": (i.get("sound") or {}).get("name"),
    }, ensure_ascii=False) for i in pool]
    snd = [json.dumps({k: s.get(k) for k in ("platform", "name", "artist", "rank", "uses", "trend",
                                              "trending")}, ensure_ascii=False) for s in sounds[:40]]
    prompt = DIGEST_PROMPT.format(videos="\n".join(vids), sounds="\n".join(snd))
    try:
        msg = anthropic.Anthropic().messages.create(
            model=model, max_tokens=4000, messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        digest = parse_json(text)
    except Exception as e:
        common.claude_error("Weekly digest", e)
        return None
    attach_examples(digest, items)
    digest["week_of"] = common.NOW.date().isoformat()
    digest["model"] = model
    return digest
