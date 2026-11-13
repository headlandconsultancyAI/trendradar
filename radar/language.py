"""English-only filter.

Decides in this order, stopping at the first clear answer:
  1. The platform's own language field (YouTube audio language, TikTok caption language)
  2. Script: mostly non-Latin letters (Cyrillic, Devanagari, Hangul, Arabic...) means not English
  3. Too little text to judge (emoji, hashtags only): keep it
  4. A small offline language model, with a guard so an English caption with one foreign
     phrase ("the birthday girl is muy bonita") isn't thrown out

Romanised Hindi and Urdu ("Tu Mil Jaaye") are hard to spot from text alone. On YouTube the audio
language field usually catches them; elsewhere a few may slip through.
"""
from __future__ import annotations

import re
import unicodedata

from .common import log

UNKNOWN = {"", "un", "und", "zxx", "mul", "none", None}

# common English words; if a caption is mostly these, it's English whatever the model says
EN_WORDS = set("""
a about after all also am an and any are as at be because been before being but by can can't come could
day did do does don't down even every for from get go going good got had has have he her here him his how
i i'm if in into is it it's its just know like look make me more most my new no not now of off on one only
or our out over people really right say see she should so some still take than that the their them then
there these they thing think this time to too up us very want was way we well were what when where which
who why will with would year you your you're yours we're they're isn't wasn't won't didn't doesn't
""".split())

_URL = re.compile(r"https?://\S+|www\.\S+")
_TAG = re.compile(r"[#@][\wÀ-￿.]+")


def _clean(text: str) -> str:
    text = _URL.sub(" ", text or "")
    text = _TAG.sub(" ", text)
    # keep letters, apostrophes and spaces only
    text = "".join(c if (c.isalpha() or c in "'’ ") else " " for c in text)
    return re.sub(r"\s+", " ", text).strip()


def _latin_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 1.0
    latin = sum(1 for c in letters if "LATIN" in unicodedata.name(c, ""))
    return latin / len(letters)


_detector = None


def _detect(text: str) -> list[dict]:
    global _detector
    if _detector is None:
        try:
            from fast_langdetect import detect  # bundled ~1MB model, works offline
            _detector = detect
        except Exception as e:  # if the library is missing, fall back to the rules above
            log.warning("Language detector unavailable (%s); using script and hint checks only", e)
            _detector = False
    if not _detector:
        return []
    try:
        return _detector(text.lower(), model="lite", k=3)
    except Exception:
        return []


def classify(item: dict) -> tuple[bool, str]:
    """Returns (is_english, reason)."""
    hint = (item.get("lang_hint") or "").strip().lower().replace("_", "-")
    raw = f"{item.get('title') or ''}"
    text = _clean(raw)

    # 1. platform hint. YouTube's audio language is the strongest signal we get.
    if hint not in UNKNOWN:
        if hint.startswith("en"):
            return True, f"platform says {hint}"
        if item.get("platform") == "youtube":
            return False, f"audio language {hint}"

    # 2. script
    if text and _latin_share(text) < 0.5:
        return False, "non-Latin script"

    words = text.lower().split()
    if len(words) < 3:
        if hint not in UNKNOWN:  # TikTok hint with nothing else to go on
            return hint.startswith("en"), f"caption language {hint}"
        return True, "too little text to tell"

    # 4. model, with the English-words guard
    res = _detect(text)
    if not res:
        return True, "no detector"
    top = res[0]
    en_score = next((r["score"] for r in res if r["lang"] == "en"), 0.0)
    en_share = sum(1 for w in words if w.replace("’", "'") in EN_WORDS) / len(words)
    if top["lang"] == "en" or en_share >= 0.3:
        return True, f"detected {top['lang']} {top['score']:.2f}, {en_share:.0%} common English words"
    if top["score"] >= 0.8 and en_score < 0.1:
        return False, f"detected {top['lang']} {top['score']:.2f}"
    if hint not in UNKNOWN and not hint.startswith("en"):
        return False, f"caption language {hint}, detector unsure"
    return True, f"unsure ({top['lang']} {top['score']:.2f}), kept"


def filter_english(items: list[dict]) -> tuple[list[dict], list[dict]]:
    kept, dropped = [], []
    for it in items:
        ok, why = classify(it)
        if ok:
            kept.append(it)
        else:
            dropped.append({"id": it["id"], "platform": it["platform"], "author": it["author"],
                            "text": (it.get("title") or "")[:120], "reason": why, "url": it["url"]})
    log.info("English filter: kept %d, removed %d", len(kept), len(dropped))
    return kept, dropped
