"""Builds invented sample data in the raw shapes each source returns, so the whole pipeline
can be tested offline. Every account, caption and link here is made up."""
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(7)
NOW = datetime(2026, 11, 13, 6, 17, tzinfo=timezone.utc)
OUT = Path(__file__).parent / "fixtures"
OUT.mkdir(exist_ok=True)
URL = "https://example.com/sample/{}"


def ts(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False))


# ---------------- TikTok watchlist profiles (clockworks/tiktok-scraper shape) ----------------
SOUNDS = [("7431", "Speed up, slow down", "nightbus"), ("7432", "Tea break (sped up)", "kettle.wav"),
          ("7433", "Original sound", None), ("7434", "Monday again", "deskchair")]
tt_accounts = {
    "culture": {"thecommutecrew": 820_000, "lunchqueue": 1_400_000, "northernnoise": 310_000, "deskside": 95_000},
    "brands": {"sample_airline": 2_100_000, "sample_bank": 450_000, "sample_supermarket": 900_000},
}
tt_hooks = [
    "POV: you said 'quick question' in a meeting and it's now 4pm",
    "Asking strangers on the Tube what their job actually is",
    "Day in the life of a bridge inspector (it's higher than you think)",
    "Ranking every meal deal combo so you don't have to",
    "We tried explaining interest rates using only biscuits",
    "Behind the scenes of how a 6am delivery actually happens",
    "Me when the office heating comes on in November",
    "Things that make no sense about British trains, explained",
    "Nobody: absolutely nobody: our CEO on the group chat",
    "How to write an out of office that people actually read",
    "Duet this with your worst work commute",
    "Before and after: we let the intern redesign the canteen",
    "Blind taste test: own brand vs the expensive one",
    "The truth about why your parcel says 'out for delivery' at 7am",
]
tt_rows = []
k = 0
for lst, accs in tt_accounts.items():
    for handle, fans in accs.items():
        base = fans * random.uniform(0.04, 0.12)
        for j in range(5):
            k += 1
            hrs = random.uniform(3, 200)
            breakout = random.random() < 0.18
            plays = int(base * random.uniform(0.4, 1.6) * (random.uniform(4, 9) if breakout else 1))
            sid, sname, sauth = random.choice(SOUNDS)
            hook = tt_hooks[k % len(tt_hooks)]
            tt_rows.append({
                "_list": lst, "id": f"9100{k:03d}", "text": hook + " #fyp #uk",
                "createTimeISO": ts(hrs), "webVideoUrl": URL.format(f"tiktok-{k}"),
                "playCount": plays, "diggCount": int(plays * 0.07), "commentCount": int(plays * 0.004),
                "shareCount": int(plays * 0.01),
                "authorMeta": {"name": handle, "fans": fans},
                "videoMeta": {"duration": random.randint(9, 75)},
                "musicMeta": {"musicId": sid, "musicName": sname, "musicAuthor": sauth,
                              "musicOriginal": sname == "Original sound"},
            })
dump("tiktok_profiles.json", tt_rows)

# ---------------- TikTok Creative Center (automation-lab/tiktok-trends-scraper shape) ----------------
cc_hooks = ["Tell me you grew up in the UK without telling me", "This dog has a better commute than me",
            "POV: your mum finds the receipt", "The only Christmas advert I'll watch this year",
            "Rating London's most overpriced coffee", "When the self checkout needs approval again",
            "Explaining my job to my nan", "Speed up, slow down transition but make it a bin lorry"]
dump("tiktok_cc_videos.json", [{
    "rank": r + 1, "type": "video", "videoId": f"9200{r:03d}", "videoUrl": URL.format(f"cc-{r}"),
    "videoDesc": h, "playCount": int(9e6 / (r + 1)), "likeCountVideo": int(7e5 / (r + 1)),
    "commentCount": int(2e4 / (r + 1)), "shareCount": int(5e4 / (r + 1)),
    "authorHandle": f"@creator_{r + 1}", "trend": random.choice(["rising", "rising", "stable", "falling"]),
    "soundName": random.choice([s[1] for s in SOUNDS]), "hashtags": ["#fyp", "#uk"],
} for r, h in enumerate(cc_hooks)])
dump("tiktok_cc_sounds.json", [{
    "rank": r + 1, "type": "sound", "musicId": f"88{r}", "name": nme, "author": art,
    "publishedVideoCount": int(4e5 / (r + 1)), "videoViews": 0, "trend": tr,
    "linkedVideoUrl": URL.format(f"sound-{r}"),
} for r, (nme, art, tr) in enumerate([
    ("Speed up, slow down", "nightbus", "rising"), ("Winter lights (instrumental)", "glasshouse", "rising"),
    ("Tea break (sped up)", "kettle.wav", "stable"), ("Office party anthem", "the temps", "rising"),
    ("Quiet hours", "loft", "falling"), ("Big Monday energy", "deskchair", "stable")])])
dump("tiktok_cc_hashtags.json", [{
    "rank": r + 1, "name": t, "publishedVideoCount": int(2e5 / (r + 1)), "videoViews": int(9e8 / (r + 1)),
    "trend": random.choice(["rising", "stable"])} for r, t in enumerate(
    ["christmasadvert", "commutecheck", "mealdeal", "officelife", "budgetday", "winterarc"])])

# ---------------- Instagram Reels (apify/instagram-reel-scraper shape) ----------------
ig_accounts = {
    "culture": {"sample_culture_mag": 600_000, "everyday_britain": 1_100_000},
    "brands": {"sample_bakery_chain": 800_000, "sample_retailer": 350_000, "sample_fintech": 210_000},
}
ig_hooks = ["Things only people who work in an office understand", "We asked the night shift what keeps them going",
            "POV: it's 4:59 on a Friday", "Explaining pensions in 30 seconds with a sausage roll",
            "Behind the scenes at 4am in the bakery", "Rating your out of office messages",
            "A day in the life of our youngest engineer", "How it started vs how it's going"]
ig_rows = []
k = 0
for lst, accs in ig_accounts.items():
    for handle, fol in accs.items():
        base = fol * random.uniform(0.05, 0.15)
        for j in range(5):
            k += 1
            breakout = random.random() < 0.2
            plays = int(base * random.uniform(0.5, 1.5) * (random.uniform(4, 8) if breakout else 1))
            song = random.choice([("5511", "Winter lights (instrumental)", "glasshouse", True),
                                  ("5512", "Speed up, slow down", "nightbus", True),
                                  ("5513", None, None, False)])
            ig_rows.append({
                "_list": lst, "id": f"3300{k:03d}", "shortCode": f"S{k:03d}", "url": URL.format(f"reel-{k}"),
                "caption": ig_hooks[k % len(ig_hooks)] + " #reels", "timestamp": ts(random.uniform(5, 220)),
                "videoPlayCount": plays, "likesCount": int(plays * 0.05), "commentsCount": int(plays * 0.003),
                "ownerUsername": handle, "videoDuration": random.randint(8, 60),
                "musicInfo": {"audio_id": song[0], "song_name": song[1], "artist_name": song[2],
                              "uses_original_audio": song[1] is None},
                "audio_is_trending": song[3],
            })
dump("instagram_reels.json", ig_rows)

# ---------------- YouTube (Data API videos resource shape) ----------------
def yt_video(vid, title, channel, hrs, views, dur):
    return {"id": vid, "snippet": {"title": title, "channelTitle": channel, "publishedAt": ts(hrs),
                                   "thumbnails": {}, "tags": []},
            "statistics": {"viewCount": str(views), "likeCount": str(views // 30), "commentCount": str(views // 400)},
            "contentDetails": {"duration": dur}}

dump("youtube_chart.json", [
    yt_video("c1", "Sample Artist: Northern Lights (Official Music Video)", "SampleArtistVEVO", 40, 2_400_000, "PT3M41S"),
    yt_video("c2", "Winter Heist: Official Trailer", "Sample Pictures UK", 30, 1_800_000, "PT2M12S"),
    yt_video("c3", "We tried to survive 24 hours in a lighthouse", "The Sample Five", 60, 3_100_000, "PT28M3S"),
    yt_video("c4", "Ranking every UK service station", "Road Snacks", 20, 900_000, "PT19M40S"),
])
yt = []
for i, (title, ch, subs, hrs, views, dur, lst) in enumerate([
    ("Asking London commuters the weirdest thing they've seen on a train", "Platform 9", 410_000, 30, 520_000, "PT58S", "culture"),
    ("Episode 12: the office Christmas party debrief", "Desk Talk", 230_000, 70, 140_000, "PT41M2S", "culture"),
    ("Desk Talk clip: the Secret Santa disaster", "Desk Talk", 230_000, 20, 260_000, "PT49S", "culture"),
    ("Desk Talk: why nobody answers the phone anymore", "Desk Talk", 230_000, 150, 60_000, "PT12M2S", "culture"),
    ("Platform 9: rating station sandwiches", "Platform 9", 410_000, 180, 90_000, "PT14M2S", "culture"),
    ("Platform 9: the last train home", "Platform 9", 410_000, 220, 70_000, "PT10M2S", "culture"),
    ("How we build a wind turbine blade, step by step", "Sample Engineering Co", 85_000, 90, 300_000, "PT2M40S", "brands"),
    ("Sample Engineering Co: apprentice open day", "Sample Engineering Co", 85_000, 200, 12_000, "PT3M2S", "brands"),
    ("Sample Engineering Co: safety week", "Sample Engineering Co", 85_000, 210, 9_000, "PT1M10S", "brands"),
]):
    v = yt_video(f"w{i}", title, ch, hrs, views, dur)
    v["_list"], v["_subs"] = lst, subs
    yt.append(v)
dump("youtube_watchlist.json", yt)

# ---------------- History seed (so 'momentum' has something to compare with) ----------------
hist = {}
for r in tt_rows[::3]:
    hist[f"tt:{r['id']}"] = {"views": int(r["playCount"] * random.uniform(0.55, 0.95)),
                             "t": (NOW - timedelta(hours=24)).isoformat(), "first_seen": (NOW - timedelta(hours=48)).isoformat()}
dump("history_seed.json", hist)
dump("meta.json", {"now": NOW.isoformat()})
print("fixtures written to", OUT)
