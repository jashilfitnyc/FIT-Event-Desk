# FIT Event Desk

One dashboard that merges everything FIT posts publicly about upcoming events.

## Files

| File | What it is |
|---|---|
| `fit-events-dashboard.html` | The dashboard. Open it in a browser — no server, no dependencies. Data is baked in. |
| `fit_events.py` | Fetches all sources live and regenerates the dashboard + JSON. Stdlib only. |
| `dashboard_template.html` | The page template `fit_events.py` fills in. Edit this to change the design. |
| `fit_events.json` | The merged, normalized event data. |
| `seed_build.py` + `raw/` | Builds the dashboard from cached snapshots (used to make the current copy). |
| `.github/workflows/refresh.yml` | Rebuilds and republishes the page daily on GitHub Actions. |
| `SETUP-GITHUB.md` | Ten-minute setup for the self-updating hosted version. **Start here.** |

## Refreshing

```
python3 fit_events.py                  # next 45 days
python3 fit_events.py --days 60        # wider window
python3 fit_events.py --include-25live # add 25Live space bookings
python3 fit_events.py --no-news        # skip the Newsroom feed
```

It writes `fit_events.json` and `fit-events-dashboard.html` in the same folder.
Needs Python 3.8+ and outbound network access to the FIT domains — run it from
a machine on the FIT network or with normal internet, not from a locked-down box.

## Sources

| Source | How it's read | Status |
|---|---|---|
| events.fitnyc.edu | WordPress "The Events Calendar" REST API (`/wp-json/tribe/events/v1/events`) | Working — the official college calendar, richest metadata |
| Engage (fitnyc.campuslabs.com) | Public iCal feed at `/engage/events.ics` | Working — this is where the clubs and orgs post |
| news.fitnyc.edu | RSS (`/feed/`) | Working — announcements, not dated events, so they render in their own section |
| 25Live | Public JSON at `25live.collegenet.com/25live/data/fitnyc/run/events.json` | Off by default. Reachable, but it returns room bookings and semester containers, not curated events. Turn it on with `--include-25live` and expect noise. |
| Instagram / Facebook | — | Not collected. Both require a login and automated scraping violates their terms. If club social posts matter, the sustainable fix is asking clubs to also post to Engage, which already feeds this list. |

Note on Engage: the site's own internal API (`/engage/api/…`) is blocked by
`robots.txt`. The `.ics` feed used here is a public, sanctioned export of the
same data, so nothing is being scraped around a restriction.

## What the dashboard does

- Merges and deduplicates across sources; an event in two feeds shows an "also in" tag
- Filter by source, search across title / place / organizer / description
- Window presets: 7 days, 2 weeks, 30 days, everything
- "Hide drop-in fitness classes" — Engage carries dozens of recurring Spin/Yoga/Pilates
  sessions that would otherwise bury everything else. On by default.
- Repeating events are labelled with their series length
- **Monthly draft** builds the formatted Liblist listing for a chosen month —
  "highlights only" drops the recurring gym classes and folds a repeating event
  into a single entry with its other dates noted
- **Copy what's showing** exports whatever the current filters have narrowed to
- Light and dark, and it works on a phone

## Known limits

- Times are rendered in America/New_York. The Engage feed publishes in UTC; the
  college calendar publishes local wall time and is converted on the way in.
- Deduplication matches on squashed title + calendar day. Two genuinely different
  events with the same name on the same day would collapse into one.
- The dashboard is a snapshot. It does not fetch live in the browser — cross-origin
  requests to these hosts would be blocked. Re-run `fit_events.py` to refresh.
