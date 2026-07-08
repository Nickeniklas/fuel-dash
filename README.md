# helsinki-fuel-dash

Fuel price tracker for the Helsinki area. Polls the unofficial Tankille API every
3 hours via GitHub Actions, accumulates price history in SQLite, and publishes a
static Chart.js dashboard on GitHub Pages: current prices sorted cheapest-first,
per-station price history, and area median trends for 95E10 / 98E5 / diesel.

Full design: [docs/PLAN.md](docs/PLAN.md) · API contract: [docs/API.md](docs/API.md)

## Local setup

```
pip install -r requirements.txt
cp .env.example .env      # fill in your Tankille account credentials
python poller.py          # first run backfills 14 days of history
python export.py
```

Then open `site/index.html` via any static file server, e.g.
`python -m http.server -d site` → http://localhost:8000

## CI setup

1. Configure repo secrets **TANKILLE_EMAIL** and **TANKILLE_PASSWORD**.
2. Repo Settings → Pages → Source: **GitHub Actions**.
3. Workflows: `poll.yml` (3 h cron: poll → export → `[bot] poll` commit → Pages
   deploy) and `pages.yml` (Pages deploy on manual pushes touching `site/`).

Be polite to the API — it's unofficial. One location request per poll, honest
User-Agent, no retry storms. Don't shorten the cron interval.
