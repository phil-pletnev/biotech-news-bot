"""
Biotech news -> Telegram channel.
Runs once, posts new items from RSS feeds, remembers what it posted, exits.
GitHub Actions runs it on a schedule.
"""
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import feedparser
import requests

# ---------- SETTINGS (edit these) ----------
FEEDS = {
    "STAT": "https://www.statnews.com/feed/",
    "Fierce Biotech": "https://www.fiercebiotech.com/rss/xml",
    "Endpoints": "https://news.google.com/rss/search?q=site:endpoints.news&hl=en-US&gl=US&ceid=US:en",
}

# Leave empty [] to post everything. Otherwise only items mentioning
# at least one keyword (in title or summary) are posted.
KEYWORDS = []

# Optional hashtags: if the text matches the pattern, the tag is added.
TAGS = {
    "#RNA": r"\b(siRNA|RNAi|antisense|ASO|oligonucleotide|mRNA)\b",
    "#GeneTherapy": r"\b(gene therapy|AAV|gene editing|CRISPR|base edit)",
    "#Deals": r"\b(acquir|acquisition|merger|licens|buyout|takeover)",
    "#Financing": r"\b(raises|Series [A-D]|IPO|financing|funding round)",
    "#Clinical": r"\b(Phase [123I]+|trial|readout|topline)",
    "#FDA": r"\b(FDA|approval|approves|CRL|PDUFA)\b",
}

MAX_POSTS_PER_RUN = 15      # safety cap so a glitch can't flood the channel
SEEN_FILE = Path("seen.json")
SEEN_LIMIT = 3000           # how many past links to remember
# -------------------------------------------

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
HEADERS = {"User-Agent": "Mozilla/5.0 (biotech-news-bot)"}


def load_seen():
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text())
    return None  # first run


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(seen[-SEEN_LIMIT:], indent=0))


def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def fetch_items():
    items = []
    for source, url in FEEDS.items():
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
        except Exception as e:
            print(f"[{source}] failed: {e}")
            continue
        print(f"[{source}] {len(feed.entries)} items")
        for e in feed.entries:
            link = e.get("link")
            if not link:
                continue
            items.append({
                "source": source,
                "title": clean(e.get("title", "")),
                "summary": clean(e.get("summary", "")),
                "link": link,
                "time": time.mktime(e.published_parsed) if e.get("published_parsed") else 0,
            })
    items.sort(key=lambda x: x["time"])  # oldest first, so channel reads in order
    return items


def matches_keywords(item):
    if not KEYWORDS:
        return True
    text = f"{item['title']} {item['summary']}".lower()
    return any(k.lower() in text for k in KEYWORDS)


def build_message(item):
    text = f"{item['title']} {item['summary']}"
    tags = [t for t, pat in TAGS.items() if re.search(pat, text, re.IGNORECASE)]
    lines = [f"<b>{html.escape(item['title'])}</b>"]
    lines.append(html.escape(item["source"]) + (" · " + " ".join(tags) if tags else ""))
    lines.append(item["link"])
    return "\n".join(lines)


def send(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for _ in range(3):
        r = requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=30)
        if r.status_code == 429:  # Telegram rate limit: wait as told
            wait = r.json().get("parameters", {}).get("retry_after", 30)
            time.sleep(wait + 1)
            continue
        if not r.ok:
            print(f"Telegram error {r.status_code}: {r.text}")
        return r.ok
    return False


def main():
    seen = load_seen()
    items = fetch_items()

    if seen is None:
        # First run: remember everything currently in the feeds, post nothing.
        # Otherwise the channel would get dozens of old articles at once.
        save_seen([i["link"] for i in items])
        print(f"First run: marked {len(items)} existing items as seen.")
        return

    seen_set = set(seen)
    posted = 0
    for item in items:
        if item["link"] in seen_set:
            continue
        seen.append(item["link"])
        seen_set.add(item["link"])
        if not matches_keywords(item):
            continue
        if posted >= MAX_POSTS_PER_RUN:
            print("Hit per-run cap; remaining items marked seen.")
            continue
        if send(build_message(item)):
            posted += 1
            time.sleep(3)  # stay well under Telegram's channel limits

    save_seen(seen)
    print(f"Posted {posted} new items.")


if __name__ == "__main__":
    sys.exit(main())
