# Standing it up so it runs itself

The goal: a URL Eliza bookmarks, that refreshes every morning without either of
you touching it. GitHub does the fetching and the hosting, both free.

Total setup time is about ten minutes, once.

---

## 0. Create the workflow file

I couldn't write this one onto your disk — files under `.github/workflows/`
are blocked from remote writes, which is a sensible guard, since a workflow file
is code that runs on its own. So paste it in yourself. From the project folder:

```bash
cd ~/Desktop/Eliza:Jashil/fit-event-desk
mkdir -p .github/workflows
cat > .github/workflows/refresh.yml <<'YAML'
name: Refresh FIT events

on:
  schedule:
    # 10:00 UTC = 6am Eastern in summer, 5am in winter. Daily.
    - cron: "0 10 * * *"
  workflow_dispatch:
  push:
    branches: [main]

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Pull the feeds and build the page
        run: |
          mkdir -p public
          python3 fit_events.py \
            --days 180 \
            --min-events 5 \
            --html public/index.html \
            --out  public/fit_events.json
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: public

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
YAML
```

(The same file is attached in the chat if you'd rather drag it in — it just has
to end up at `.github/workflows/refresh.yml`.)

## 1. Make the repository

On github.com, create a new repository — call it `fit-event-desk`. **Public**
(free GitHub Pages requires it; everything here is already public FIT event data,
and no credentials are involved). Don't add a README, you already have one.

Then, from this folder on your Mac:

```bash
cd ~/Desktop/Eliza:Jashil/fit-event-desk
git init -b main
git add .
git commit -m "FIT event aggregator"
git remote add origin https://github.com/<your-username>/fit-event-desk.git
git push -u origin main
```

## 2. Turn on Pages

In the repo: **Settings → Pages → Build and deployment → Source**, choose
**GitHub Actions**. Not "Deploy from a branch" — the workflow publishes directly.

That's the only setting to change.

## 3. Run it once by hand

**Actions** tab → **Refresh FIT events** → **Run workflow**.

Give it a minute. When it goes green, the deploy step prints the live URL —
something like `https://<your-username>.github.io/fit-event-desk/`.

That link is what you send Eliza. It updates itself at 6am Eastern every day.

---

## What she gets

Two buttons in the left rail:

- **Monthly draft** — picks a month, produces the formatted listing ready to paste
  into Liblist. "Highlights only" strips the recurring gym classes and folds a
  repeating event into one entry; "Everything in the month" gives the full set.
  The text box is editable, so she can trim before copying.
- **Copy what's showing** — whatever her current filters have narrowed to.

## Things worth knowing

**It won't silently break.** If a feed goes down, the build aborts rather than
publishing an empty page, so the last good version stays up. You'll get an email
from GitHub about the failed run — that's your signal, not a broken page in front
of Eliza.

**Scheduled runs pause on quiet repos.** GitHub disables `schedule` triggers after
60 days with no commits. If you go two months without touching it, GitHub emails
you and one click re-enables it. Any commit resets the clock.

**Changing the look** means editing `dashboard_template.html` and pushing. The
`push` trigger rebuilds the site automatically.

**Changing the window** means editing `--days 180` in
`.github/workflows/refresh.yml`. Bear in mind Engage only publishes about a month
ahead, so past ~30 days you're only adding college-calendar entries.

**If you'd rather it not be public**, the same workflow runs on a FIT server via
cron instead:

```
0 6 * * *  cd /path/to/fit-event-desk && /usr/bin/python3 fit_events.py --days 180 --min-events 5 --html /var/www/html/events/index.html
```

Python 3.8+, no packages to install, needs outbound HTTPS.
