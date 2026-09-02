#!/usr/bin/env python3
"""
FIT Event Aggregator
====================

Pulls upcoming FIT events from every public source we could find and merges them
into one deduplicated list, then writes:

    fit_events.json          normalized event data
    fit-events-dashboard.html  self-contained dashboard (data baked in)

Sources
-------
1. FIT Events Calendar   events.fitnyc.edu  (WordPress "The Events Calendar" REST API)
2. FIT Engage            fitnyc.campuslabs.com/engage/events.ics  (public iCal feed - clubs/orgs)
3. FIT Newsroom          news.fitnyc.edu/feed/  (RSS - articles, event announcements)
4. 25Live                25live.collegenet.com  (room/space bookings - OFF by default, very noisy)

Stdlib only. Run:  python3 fit_events.py
Options:           python3 fit_events.py --days 60 --include-25live --no-news
"""

import argparse
import html
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

UA = "FIT-Library-EventAggregator/1.0 (Gladys Marcus Library; internal tool)"
TIMEOUT = 30

TRIBE_API = "https://events.fitnyc.edu/wp-json/tribe/events/v1/events"
ENGAGE_ICS = "https://fitnyc.campuslabs.com/engage/events.ics"
NEWS_RSS = "https://news.fitnyc.edu/feed/"
LIVE25_JSON = ("https://25live.collegenet.com/25live/data/fitnyc/run/events.json"
               "?scope=extended&limit=500")

# 25Live is full of semester containers and room holds; drop anything matching these.
LIVE25_NOISE = re.compile(
    r"\b(semester|term|session|closed|closure|holiday|recess|no classes|"
    r"finals week|registration period|academic calendar|hold|setup|breakdown)\b", re.I)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def fetch(url, accept=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if accept:
        req.add_header("Accept", accept)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"</p>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def truncate(s, n=280):
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def norm_key(title, start):
    """Dedup key: squashed title + calendar day."""
    t = re.sub(r"[^a-z0-9]+", "", (title or "").lower())
    day = start[:10] if start else ""
    return f"{t}|{day}"


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat() if dt else None


# --------------------------------------------------------------------------- #
# source: events.fitnyc.edu (The Events Calendar REST API)
# --------------------------------------------------------------------------- #

def source_fit_calendar(start, end):
    events, page, seen_pages = [], 1, 0
    while page <= 20:
        url = (f"{TRIBE_API}?start_date={start:%Y-%m-%d}&end_date={end:%Y-%m-%d}"
               f"&per_page=50&page={page}")
        try:
            data = json.loads(fetch(url, "application/json"))
        except urllib.error.HTTPError as e:
            if e.code == 400 and page > 1:
                break                      # ran past the last page
            raise
        batch = data.get("events") or []
        if not batch:
            break
        for e in batch:
            venue = e.get("venue") or {}
            orgs = e.get("organizer") or []
            events.append({
                "title": strip_html(e.get("title")),
                "start": e.get("utc_start_date") or e.get("start_date"),
                "end": e.get("utc_end_date") or e.get("end_date"),
                "all_day": bool(e.get("all_day")),
                "location": strip_html(venue.get("venue")) or "",
                "organizer": strip_html(orgs[0].get("organizer")) if orgs else "",
                "url": e.get("url") or "",
                "description": truncate(strip_html(e.get("description"))),
                "categories": [c.get("name") for c in (e.get("categories") or []) if c.get("name")],
                "source": "FIT Events Calendar",
                "source_url": "https://events.fitnyc.edu/",
            })
        seen_pages += 1
        if page >= (data.get("total_pages") or 1):
            break
        page += 1
    return events


# --------------------------------------------------------------------------- #
# source: Engage .ics  (minimal iCalendar parser - no third-party deps)
# --------------------------------------------------------------------------- #

def _unfold_ics(text):
    out = []
    for line in text.splitlines():
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _ics_unescape(v):
    return (v.replace("\\n", " ").replace("\\N", " ")
             .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")).strip()


def _ics_dt(value, params):
    value = value.strip()
    try:
        if "VALUE=DATE" in params or (len(value) == 8 and value.isdigit()):
            return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc), True
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc), False
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc), False
    except ValueError:
        return None, False


def source_engage(start, end):
    raw = fetch(ENGAGE_ICS, "text/calendar").decode("utf-8", "replace")
    events, cur = [], None
    for line in _unfold_ics(raw):
        if line.startswith("BEGIN:VEVENT"):
            cur = {}
            continue
        if line.startswith("END:VEVENT"):
            if cur and cur.get("_start"):
                s = cur["_start"]
                if start <= s <= end:
                    events.append({
                        "title": cur.get("SUMMARY", "(untitled)"),
                        "start": iso(s),
                        "end": iso(cur.get("_end")),
                        "all_day": cur.get("_allday", False),
                        "location": cur.get("LOCATION", ""),
                        "organizer": cur.get("_org", ""),
                        "url": cur.get("URL", ""),
                        "description": truncate(cur.get("DESCRIPTION", "")),
                        "categories": [c for c in cur.get("CATEGORIES", "").split(",") if c],
                        "source": "Engage (clubs & orgs)",
                        "source_url": "https://fitnyc.campuslabs.com/engage/events",
                    })
            cur = None
            continue
        if cur is None or ":" not in line:
            continue
        name, value = line.split(":", 1)
        params = name.upper()
        key = params.split(";")[0]
        value = _ics_unescape(value)
        if key == "DTSTART":
            cur["_start"], cur["_allday"] = _ics_dt(value, params)
        elif key == "DTEND":
            cur["_end"], _ = _ics_dt(value, params)
        elif key == "ORGANIZER":
            cur["_org"] = value.split("CN=")[-1] if "CN=" in name else value
        else:
            cur[key] = value
    return events


# --------------------------------------------------------------------------- #
# source: FIT Newsroom RSS
# --------------------------------------------------------------------------- #

def source_news(start, end):
    raw = fetch(NEWS_RSS, "application/rss+xml")
    root = ElementTree.fromstring(raw)
    items = []
    for item in root.iterfind(".//item"):
        def t(tag):
            el = item.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        pub = t("pubDate")
        try:
            dt = parsedate_to_datetime(pub).astimezone(timezone.utc)
        except Exception:
            continue
        # Newsroom is announcements, not a calendar: keep the recent window only.
        if dt < start - timedelta(days=45) or dt > end:
            continue
        cats = [c.text for c in item.iterfind("category") if c.text]
        items.append({
            "title": strip_html(t("title")),
            "start": iso(dt),
            "end": None,
            "all_day": True,
            "location": "",
            "organizer": "",
            "url": t("link"),
            "description": truncate(strip_html(t("description"))),
            "categories": cats,
            "source": "FIT Newsroom",
            "source_url": "https://news.fitnyc.edu/",
            "kind": "announcement",
        })
    return items


# --------------------------------------------------------------------------- #
# source: 25Live (opt-in - mostly space bookings)
# --------------------------------------------------------------------------- #

def source_25live(start, end):
    data = json.loads(fetch(LIVE25_JSON, "application/json"))
    node = data.get("events") or {}
    rows = node.get("event") or []
    if isinstance(rows, dict):
        rows = [rows]
    out = []
    for e in rows:
        name = (e.get("event_name") or e.get("event_title") or "").strip()
        if not name or LIVE25_NOISE.search(name):
            continue
        profile = e.get("profile") or {}
        if isinstance(profile, list):
            profile = profile[0] if profile else {}
        res = profile.get("reservation") or {}
        if isinstance(res, list):
            res = res[0] if res else {}
        s = res.get("event_start_dt") or e.get("start_date")
        if not s:
            continue
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            continue
        if not (start <= dt <= end):
            continue
        out.append({
            "title": name,
            "start": iso(dt),
            "end": None,
            "all_day": False,
            "location": "",
            "organizer": e.get("organization_name", "") or "",
            "url": "https://25live.collegenet.com/pro/fitnyc#!/home/calendar",
            "description": "",
            "categories": [e.get("event_type_name")] if e.get("event_type_name") else [],
            "source": "25Live",
            "source_url": "https://25live.collegenet.com/pro/fitnyc",
        })
    return out


# --------------------------------------------------------------------------- #
# merge
# --------------------------------------------------------------------------- #

SOURCE_PRIORITY = {
    "FIT Events Calendar": 0,     # richest metadata wins on a dedup collision
    "Engage (clubs & orgs)": 1,
    "25Live": 2,
    "FIT Newsroom": 3,
}


FITNESS = re.compile(
    r"\b(spin|yoga|pilates|barre|zumba|hiit|hard core|open gym|"
    r"bootcamp|kickboxing|stretch|meditation|sculpt|cycling)\b", re.I)


def classify(events):
    """Tag repeats and drop-in fitness classes so the dashboard can fold them away."""
    counts = {}
    for e in events:
        counts[e["title"].strip().lower()] = counts.get(e["title"].strip().lower(), 0) + 1
    for e in events:
        title = e["title"].strip().lower()
        e["kind"] = e.get("kind", "event")
        e["recurring"] = counts[title] >= 3
        e["routine"] = bool(FITNESS.search(title)) and counts[title] >= 2
        e["series_count"] = counts[title]
    return events


def merge(groups):
    best = {}
    for ev in [e for g in groups for e in g]:
        if not ev.get("start"):
            continue
        k = norm_key(ev["title"], ev["start"])
        prev = best.get(k)
        if prev is None:
            ev["also_in"] = []
            best[k] = ev
        else:
            keep, drop = (prev, ev) if SOURCE_PRIORITY.get(prev["source"], 9) <= \
                SOURCE_PRIORITY.get(ev["source"], 9) else (ev, prev)
            keep.setdefault("also_in", [])
            for s in [drop["source"]] + drop.get("also_in", []):
                if s != keep["source"] and s not in keep["also_in"]:
                    keep["also_in"].append(s)
            best[k] = keep
    return classify(sorted(best.values(), key=lambda e: (e["start"], e["title"].lower())))


# --------------------------------------------------------------------------- #

def main():
    p = argparse.ArgumentParser(description="Aggregate FIT events into one list.")
    p.add_argument("--days", type=int, default=180, help="days ahead to include (default 180)")
    p.add_argument("--include-25live", action="store_true", help="add 25Live space bookings")
    p.add_argument("--no-news", action="store_true", help="skip the Newsroom RSS feed")
    p.add_argument("--min-events", type=int, default=0,
                   help="exit non-zero if fewer events than this were merged; "
                        "use in CI so a broken feed can't quietly publish an empty page")
    p.add_argument("--out", default="fit_events.json")
    p.add_argument("--html", default="fit-events-dashboard.html")
    p.add_argument("--template", default="dashboard_template.html")
    args = p.parse_args()

    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=args.days)

    plan = [("FIT Events Calendar", source_fit_calendar),
            ("Engage (clubs & orgs)", source_engage)]
    if not args.no_news:
        plan.append(("FIT Newsroom", source_news))
    if args.include_25live:
        plan.append(("25Live", source_25live))

    groups, report = [], []
    for label, fn in plan:
        try:
            got = fn(start, end)
            groups.append(got)
            report.append({"source": label, "ok": True, "count": len(got)})
            print(f"  ok    {label:<24} {len(got):>4} items", file=sys.stderr)
        except Exception as exc:
            groups.append([])
            report.append({"source": label, "ok": False, "count": 0, "error": str(exc)})
            print(f"  FAIL  {label:<24} {exc}", file=sys.stderr)

    events = merge(groups)
    payload = {
        "generated_at": now.isoformat(),
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": args.days},
        "sources": report,
        "count": len(events),
        "events": events,
    }

    if args.min_events and len(events) < args.min_events:
        print(f"\n  ABORT: only {len(events)} events merged, expected at least "
              f"{args.min_events}. A feed is probably broken - nothing written.", file=sys.stderr)
        sys.exit(1)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\n  wrote {args.out}  ({len(events)} merged events)", file=sys.stderr)

    try:
        with open(args.template, encoding="utf-8") as f:
            tpl = f.read()
        blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(tpl.replace("/*__FIT_EVENT_DATA__*/null", blob))
        print(f"  wrote {args.html}", file=sys.stderr)
    except FileNotFoundError:
        print(f"  (no {args.template} found - skipped HTML)", file=sys.stderr)


if __name__ == "__main__":
    main()
