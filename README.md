# Trend Radar

A format and sound radar for short-form video. Every morning it pulls what's moving on YouTube, TikTok and Instagram Reels in the UK, works out which videos are picking up fastest, tags each one by creative format, and every Monday Claude writes up five formats worth borrowing for client work.

It runs on the same setup as the petition tracker: GitHub Actions on a schedule, Apify for scraping, a GitHub Pages dashboard.

## What's on the dashboard

- **Rising videos**: UK YouTube charts, TikTok's own trending list and your culture watchlist, ranked by heat
- **Formats to borrow this week**: the Monday digest, with what each format is, why it's working, how a corporate client could use it and what to watch out for
- **Sounds picking up**: TikTok's UK sound chart plus sounds spreading across several watchlist accounts
- **Brands doing it well**: brand watchlist posts, sorted by how far each one beat that brand's usual views
- **Swipe file**: star anything and add a note. Copy it all as brainstorm notes or download a CSV. Saved in your browser only

Every video is tagged **fast meme** (a week or two of life, needs quick sign-off) or **durable format** (reusable for months).

### How heat works

Heat is 0 to 100, worked out within each platform so TikTok's bigger numbers don't drown out the rest:

- 55% views per hour since posting
- 35% views compared with that account's typical video (a format that landed, not just a big account)
- 10% whether views per hour picked up since the previous run

TikTok trending-list videos that don't come with a post time are scored on their chart position.

## Setup (about 20 minutes)

1. **Create a repo** and upload everything in this folder. A public repo is fine since it only holds public post data, but don't put client names in `watchlist.yaml` if it's public.
2. **Add three secrets** under Settings → Secrets and variables → Actions:
   - `YOUTUBE_API_KEY`: Google Cloud console → enable YouTube Data API v3 → Credentials → API key. A daily run uses well under 100 of the free 10,000 units
   - `APIFY_TOKEN`: the same token as the petition tracker works
   - `ANTHROPIC_API_KEY`: optional. Without it, formats are tagged by keyword rules and there's no weekly digest
3. **Turn on Pages**: Settings → Pages → Deploy from a branch → `main`, folder `/docs`.
4. **Run it once**: Actions → Trend radar → Run workflow, tick "Write a fresh weekly digest now". After that it runs every day at 06:17 UTC and writes the digest on Mondays.
5. **Tune the watchlist** in `watchlist.yaml`. The dashboard footer lists any handle that returned nothing, so typos are easy to spot.

Until the first run the dashboard shows sample data with a yellow banner. Everything in it is invented.

## Files

| File | What it does |
|---|---|
| `watchlist.yaml` | Accounts, region, how much to pull, which Apify actors and Claude models to use |
| `run.py` | The daily run: fetch, score, tag, digest, write `docs/data/radar.json` |
| `radar/youtube.py` | UK charts plus recent uploads from watchlist channels |
| `radar/tiktok.py` | TikTok Creative Center trends plus watchlist profiles |
| `radar/reels.py` | Recent Reels from watchlist accounts |
| `radar/score.py` | Heat, momentum, "vs usual", sound grouping |
| `radar/tag.py` | Format tagging (Claude, with keyword fallback) |
| `radar/digest.py` | The Monday digest |
| `docs/index.html` | The dashboard |
| `tests/` | Invented sample data. `python run.py --offline` runs the whole pipeline on it |

## Costs

- **YouTube**: free within the default quota
- **Apify**: charged per result. Roughly (accounts × `per_account`) Reels and TikToks a day, plus about 130 Creative Center rows. Lower `per_account` in `watchlist.yaml` if it creeps up
- **Claude**: each video is tagged once and cached, so it's a few hundred short items a week plus one digest

## Things to know

- **Scrapers break.** If TikTok or Instagram change something, an Apify actor can stop returning data. The run logs which source failed and keeps the other platforms going. Swap the actor name in `watchlist.yaml` if one dies.
- **YouTube's charts are music heavy.** YouTube dropped its Trending page in July 2025 and the API's "mostPopular" now only covers music, film and gaming. The watchlist channels are what make the YouTube side useful.
- **TikTok Creative Center is 7 or 30 days**, so it shows what's been big this week. The watchlist and heat score catch things earlier.
- **Thumbnails from TikTok and Instagram expire** after a few days. Cards fall back to a coloured tile with the hook.
- **Check commercial rights before a brand uses a trending sound.** Plenty of trending sounds aren't cleared for business accounts.
