#!/usr/bin/env python3
"""Build fit_events.json + the dashboard from cached raw/*.json snapshots.

Used to produce a working demo when the machine running this has no direct
network route to the FIT domains. `fit_events.py` does the same thing live.
"""
import json
from datetime import datetime, timedelta, timezone

from fit_events import merge, truncate

GEN = datetime(2026, 8, 24, 13, 0, tzinfo=timezone.utc)
WINDOW_DAYS = 180


def load(name):
    with open(f"raw/{name}.json", encoding="utf-8") as f:
        return json.load(f)


def local_to_utc(s):
    """events.fitnyc.edu returns local (America/New_York) wall time; EDT = UTC-4."""
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=-4)))
    return dt.astimezone(timezone.utc).isoformat()


calendar = [{
    "title": e["title"],
    "start": local_to_utc(e["start_date"]),
    "end": local_to_utc(e["end_date"]),
    "all_day": e["all_day"],
    "location": e["venue"],
    "organizer": e["organizer"],
    "url": e["url"],
    "description": truncate(e["description"]),
    "categories": e["categories"],
    "source": "FIT Events Calendar",
    "source_url": "https://events.fitnyc.edu/",
} for e in load("calendar")]

engage = [{
    "title": e["title"],
    "start": e["start"],
    "end": e["end"],
    "all_day": False,
    "location": e["location"],
    "organizer": "",
    "url": e["url"],
    "description": truncate(e["description"]),
    "categories": [],
    "source": "Engage (clubs & orgs)",
    "source_url": "https://fitnyc.campuslabs.com/engage/events",
} for e in load("engage")]

news = [{
    "title": e["title"],
    "start": e["pubDate"],
    "end": None,
    "all_day": True,
    "location": "",
    "organizer": "",
    "url": e["link"],
    "description": truncate(e["description"]),
    "categories": e["categories"],
    "source": "FIT Newsroom",
    "source_url": "https://news.fitnyc.edu/",
    "kind": "announcement",
} for e in load("news")]

events = merge([calendar, engage, news])
payload = {
    "generated_at": GEN.isoformat(),
    "window": {"start": GEN.isoformat(),
               "end": (GEN + timedelta(days=WINDOW_DAYS)).isoformat(),
               "days": WINDOW_DAYS},
    "sources": [
        {"source": "FIT Events Calendar", "ok": True, "count": len(calendar),
         "url": "https://events.fitnyc.edu/", "method": "WordPress Events Calendar REST API"},
        {"source": "Engage (clubs & orgs)", "ok": True, "count": len(engage),
         "url": "https://fitnyc.campuslabs.com/engage/events",
         "method": "Public iCal feed (events.ics) — the feed itself only publishes about a month ahead"},
        {"source": "FIT Newsroom", "ok": True, "count": len(news),
         "url": "https://news.fitnyc.edu/", "method": "RSS feed"},
        {"source": "25Live", "ok": False, "count": 0,
         "url": "https://25live.collegenet.com/pro/fitnyc", "method": "Public JSON — off by default (space bookings, very noisy)"},
        {"source": "Instagram / Facebook", "ok": False, "count": 0,
         "url": "", "method": "Login-walled — not scraped"},
    ],
    "count": len(events),
    "events": events,
}

with open("fit_events.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, ensure_ascii=False)

with open("dashboard_template.html", encoding="utf-8") as f:
    tpl = f.read()
blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
with open("fit-events-dashboard.html", "w", encoding="utf-8") as f:
    f.write(tpl.replace("/*__FIT_EVENT_DATA__*/null", blob))

print(f"{len(events)} merged events -> fit_events.json + fit-events-dashboard.html")
