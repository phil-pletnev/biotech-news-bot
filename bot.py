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
    "Endpoints": "https://endpoints.news/feed/",
    "BioPharma Dive": "https://www.biopharmadive.com/feeds/news/",
}

# Leave empty [] to post everything. Otherwise only items mentioning
# at least one keyword (in title or summary) are posted.
KEYWORDS = []

# Optional hashtags: if the text matches the pattern, the tag is added.
TAGS = {
    # Modalities
    "#SmallMolecule": r"\b(small[- ]molecules?|kinase inhibitors?|oral (drug|pill|therap\w*))",
    "#Degraders": r"\b(PROTACs?|degraders?|molecular glues?|protein degradation)",
    "#Antibody": r"\b(antibod\w*|mAbs?|nanobod\w*)",
    "#Bispecific": r"\b(bispecific\w*|trispecific\w*|T[- ]cell engagers?)",
    "#ADC": r"\b(ADCs?|antibody[- ]drug conjugates?)\b",
    "#Peptides": r"\b(peptides?|macrocycl\w*)\b",
    "#RNA": r"\b(siRNA|RNAi|antisense|ASOs?|oligonucleotides?|GalNAc|RNA[- ]edit\w*|exon[- ]skip\w*)",
    "#mRNA": r"\b(mRNA|saRNA|self-amplifying RNA|circular RNA|lipid nanoparticles?|LNPs?)\b",
    "#GeneTherapy": r"\b(gene therap\w*|AAV|capsids?|lentivir\w*)",
    "#GeneEditing": r"\b(CRISPR|gene[- ]edit\w*|base[- ]edit\w*|prime[- ]edit\w*|epigenetic edit\w*)",
    "#CellTherapy": r"\b(CAR[- ]?T|CAR[- ]NK|cell therap\w*|TCR|TILs?|Tregs?|NK cells?|iPSC|stem cells?)\b",
    "#Radiopharma": r"\b(radiopharm\w*|radioligand\w*|radiotherap\w*|actinium|lutetium)",
    "#Vaccines": r"\bvaccin\w*",
    "#OncolyticVirus": r"\boncolytic\w*",
    "#Microbiome": r"\b(microbiome|microbiota|live biotherapeutic\w*|bacteriophages?|phage therap\w*)",
    "#Cytokines": r"\b(cytokines?|interleukin\w*|IL-\d+\w*)",
    "#ERT": r"\b(enzyme replacement|ERT)\b",
    "#Psychedelics": r"\b(psychedelic\w*|psilocybin|MDMA|LSD|DMT|ibogaine|ketamine)\b",
    "#Biosimilars": r"\b(biosimilar\w*|generics?)\b",
    "#Diagnostics": r"\b(diagnostic\w*|liquid biops\w*|biomarker\w*|screening test\w*)",
    "#AI": r"\b(AI|artificial intelligence|machine learning|generative model\w*)\b",
    # Therapeutic areas
    "#Oncology": r"\b(cancer\w*|tumou?rs?|oncolog\w*|lymphoma|leuk(a)?emia|myeloma|carcinoma|sarcoma|glioblastoma)",
    "#Obesity": r"\b(obesity|weight loss|GLP-1|semaglutide|tirzepatide|incretin\w*|amylin)",
    "#Diabetes": r"\b(diabet\w*|insulin)",
    "#Cardio": r"\b(cardiovascular|cardio\w*|heart failure|Lp\(a\)|cholesterol|LDL|hypertension|atrial fibrillation)",
    "#Neuro": r"\b(Alzheimer\w*|Parkinson\w*|ALS|Huntington\w*|epilep\w*|multiple sclerosis|neurodegenerat\w*)",
    "#Neuromuscular": r"\b(Duchenne|DMD|SMA|spinal muscular atrophy|muscular dystroph\w*|myasthenia)",
    "#Psychiatry": r"\b(depress\w*|schizophreni\w*|bipolar|anxiety|PTSD|psychiatr\w*)",
    "#Pain": r"\b(pain|opioid\w*|analgesi\w*|migraine)\b",
    "#Immunology": r"\b(autoimmun\w*|lupus|psoria\w*|atopic dermatitis|eczema|IBD|Crohn\w*|colitis|inflammat\w*|rheumatoid)",
    "#Respiratory": r"\b(COPD|asthma|pulmonary|cystic fibrosis|IPF|lung disease\w*)",
    "#Hematology": r"\b(sickle cell|hemophilia|haemophilia|thalass(a)?emia|an(a)?emia)",
    "#Ophthalmology": r"\b(ophthalm\w*|retina\w*|macular|glaucoma|geographic atrophy|eye disease\w*)",
    "#Liver": r"\b(liver|MASH|NASH|hepat\w*)",
    "#Kidney": r"\b(kidney|renal|nephr\w*|IgAN|dialysis)\b",
    "#WomensHealth": r"\b(endometriosis|menopaus\w*|fertility|contracept\w*|pregnan\w*|preeclampsia)",
    "#RareDisease": r"\b(rare disease\w*|orphan drug\w*|ultra-rare)",
    "#Infectious": r"\b(antibiotic\w*|antiviral\w*|antimicrobial\w*|antifungal\w*|HIV|HBV|COVID\w*|influenza|flu\b|RSV)",
    # Business
    "#Deals": r"\b(acqui\w*|merger\w*|licens\w*|buyout|takeover|partnership|collaboration)",
    "#Financing": r"\b(raises|raised|Series [A-F]|financing|funding|private placement|venture)\b",
    "#IPO": r"\b(IPOs?|initial public offering|goes public|go public|SPAC)\b",
    "#Earnings": r"\b(earnings|quarterly results|Q[1-4] (results|sales|revenue)|guidance)\b",
    "#Layoffs": r"\b(layoffs?|lays off|job cuts|restructur\w*|workforce reduction)",
    "#Shutdown": r"\b(bankrupt\w*|shuts? down|shutter\w*|wind(s|ing)? down|ceases? operations|liquidat\w*)",
    "#Leadership": r"\b(new CEO|steps? down|resign\w*|ousted|appoint\w*|succession)",
    "#Manufacturing": r"\b(manufactur\w*|CDMO\w*|supply chain|drug shortage\w*)",
    "#Legal": r"\b(lawsuit\w*|litigation|patent\w*|settlement|antitrust)",
    # Clinical & regulatory
    "#Clinical": r"\b(Phase (1|2|3|I{1,3})\w*|trials?|readouts?|topline)\b",
    "#Safety": r"\b(clinical hold|boxed warning|black box|safety signal\w*|patient deaths?|adverse events?)",
    "#FDA": r"\b(FDA|PDUFA|CRL|complete response letter|BLA|NDA|advisory committee|adcomm?)\b",
    "#Approval": r"\b(approv\w*)",
    "#EMA": r"\b(EMA|CHMP|European Commission)\b",
    "#Policy": r"\b(tariffs?|Medicare|Medicaid|drug pricing|MFN|most[- ]favou?red[- ]nation|CMS|IRA|HHS)\b",
    "#China": r"\b(China|Chinese|BIOSECURE)\b",
}

MAX_POSTS_PER_RUN = 50      # safety cap so a glitch can't flood the channel
SEEN_FILE = Path("seen.json")
SEEN_LIMIT = 3000           # how many past links to remember
# -------------------------------------------

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


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
