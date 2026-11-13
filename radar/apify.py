"""Minimal Apify client: run an actor synchronously and return its dataset items."""
from __future__ import annotations

import os

import requests

from .common import log

API = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"


def run_actor(actor: str, payload: dict, timeout_s: int = 290) -> list[dict]:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        log.warning("APIFY_TOKEN not set, skipping %s", actor)
        return []
    url = API.format(actor=actor.replace("/", "~"))
    try:
        r = requests.post(
            url,
            params={"timeout": timeout_s, "clean": "true"},
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=timeout_s + 30,
        )
    except requests.RequestException as e:
        log.error("Apify %s failed: %s", actor, e)
        return []
    if r.status_code >= 400:
        log.error("Apify %s returned %s: %s", actor, r.status_code, r.text[:300])
        return []
    try:
        data = r.json()
    except ValueError:
        log.error("Apify %s returned non-JSON", actor)
        return []
    items = data if isinstance(data, list) else data.get("items", [])
    log.info("Apify %s returned %d items", actor, len(items))
    return items
