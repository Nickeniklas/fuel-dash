# fuel-dash

Personal fuel price tracker for the Helsinki area, published as a static dashboard.

A 12 h GitHub Actions cron scrapes the crowdsourced site polttoaine.net,
accumulates per-station price history in SQLite, and deploys a Chart.js +
Leaflet page to GitHub Pages. The interesting constraint is that the source
exposes only about five days of history and there is no backfill anywhere, so
the dataset is strictly what the poller has personally witnessed — an outage
costs those days permanently. That shapes the whole design: two independent
sources, one deep and official, one shallow and local, deliberately never
joined.

Live: https://nickeniklas.github.io/fuel-dash/
Design notes: [docs/PLAN.md](docs/PLAN.md) · Source contracts: [docs/SCRAPER.md](docs/SCRAPER.md)

## What it does

1. `poll.py` fetches the configured polttoaine.net pages, parses the price
   rows, resolves coordinates for stations it hasn't seen before, and upserts
   everything into `fuel.db`.
2. `eu_bulletin.py` downloads the EU Weekly Oil Bulletin workbook and upserts
   official national weekly prices into `eu.db`.
3. `export.py` reads both databases and writes the JSON the dashboard fetches.
4. The workflow commits the two databases back to `main` and deploys `site/`
   to GitHub Pages in the same run.

The page shows a cheapest-first price table, a map, an area median chart with
the Finnish national average overlaid, a 2005-onwards long-term context chart,
and a per-station trend lookup.

## Requirements

- Python 3.12 (the CI workflows pin this)
- `requests`, `beautifulsoup4`, `openpyxl` — see `requirements.txt`

No credentials, API keys or environment variables are needed. Nothing in this
project reads `os.environ`.

## Install

```
git clone https://github.com/Nickeniklas/fuel-dash.git
cd fuel-dash
python -m venv .venv && .venv/Scripts/activate    # Windows
pip install -r requirements.txt
```

## Usage

```
python -m unittest discover -s tests -t .   # full suite, no network
python poll.py                              # scrape prices into fuel.db
python eu_bulletin.py                       # ingest the EU bulletin into eu.db
python export.py                            # write site/data/*.json from both DBs
python probe_coords.py [station_id]         # re-check the coordinate endpoints
```

`eu_bulletin.py --file <path>` parses a local copy of the workbook instead of
downloading it, which also bypasses the self-gate.

To view the dashboard locally, serve `site/` over HTTP — `fetch` will not load
the JSON from a `file://` URL:

```
cd site && python -m http.server
```

## How it works

Two sources, kept in separate SQLite files and never joined. `fuel.db` holds
the polttoaine.net scrape: per-station Helsinki-area prices, history starting
at the first poll. `eu.db` holds the EU Weekly Oil Bulletin (European
Commission, DG Energy): one official national figure per country per week,
back to 2005. `db.py` exposes both (`connect()` and `connect_eu()`).

`parser.py` turns a fetched page into price rows; `coords.py` resolves and
caches per-station coordinates, one request per new station. `export.py`
writes `stations.json`, `history.json` and `medians.json` from `fuel.db` plus
`eu_weekly.json` from `eu.db`; the shapes are documented in
[site/data/README.md](site/data/README.md). A missing or empty `eu.db` is not
an error — the other three files are written and the dashboard degrades to
showing no national context.

`eu_bulletin.py` is self-gated: if the newest week already stored is recent
enough it exits without downloading, so the 12 h cron fetches the workbook
once per publication rather than on every run.

The dashboard in `site/` is `index.html`, `style.css` and `app.js` — no
framework and no build step, with Chart.js and Leaflet from pinned CDN URLs.
It reads only the exported JSON.

`.github/workflows/poll.yml` runs the cron end to end in a single job, and
`pages.yml` covers manual pushes that touch `site/`. The exported JSON is
gitignored and regenerated on every run, so both workflows export before
uploading the Pages artifact.

## Limitations

- **No backfill is possible.** History starts at the first poll and the source
  shows about five days at a time, so any polling gap is permanent.
- **Per-station history is much thinner than the row total suggests.** Most
  rows are each station's initial batch from the poll that first found it;
  ongoing re-reports are rare. Per-station trend is therefore a secondary
  lookup, not the headline, and the area median carries the page.
- **The EU bulletin has no 98E series.** When 98E is selected the national
  overlay is hidden with a note rather than substituting the 95 series.
- The 12 h cadence, 100 ms spacing between requests, honest User-Agent and
  robots.txt compliance are deliberate and not tunable. This is someone
  else's crowdsourced site. See [docs/SCRAPER.md](docs/SCRAPER.md).

## Attribution

Station prices are crowdsourced from [polttoaine.net](https://polttoaine.net).

National weekly prices come from the
[EU Weekly Oil Bulletin](https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en),
European Commission, Directorate-General for Energy. Reproduction is authorised
provided the source is acknowledged — the dashboard footer carries this credit,
and it must stay there.
