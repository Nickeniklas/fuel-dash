PROJECT CONTEXT — helsinki-fuel-dash
Paste-ready summary for the Claude project. Condensed from docs/PLAN.md (replanned
2026-07-08); if the plan changes, update both.

Status (2026-07-09): parser, coordinate resolution, SQLite schema/upsert, and the
poller (poll.py) are built and unit-tested, and the first live poll against the
real site succeeded — fuel.db has 76 stations (all geocoded) and 224 price rows
across the full 5-day visibility window. Next: JSON export, the GH Actions
workflow, then the dashboard.
The project
Niklas (GitHub: Nickeniklas) is building a personal fuel price tracker for the
Helsinki area. No service provides long-term price trends or a sorted area-wide
list, so this project collects its own history and visualizes it.
History: the original plan used the unofficial Tankille API. It blocked us on day
one (2026-07-08) and was dropped completely, clean DB, no workarounds. Don't
suggest returning to it.
How it works

Source: scraping polttoaine.net, an independent crowdsourced price site
(~395 active stations, reports visible 5 days, plain HTML, no auth). Parsing
spec derived from Pumperly (GPL-3.0), spec only, no code copied, and
documented in docs/SCRAPER.md.
Poller: Python + requests + SQLite, GH Actions cron every 12 h, commits the
DB and exported JSON back to the repo. Crawls a config list of pages (starting:
Helsinki, PK-Seutu, Kehä I, Kehä III), dedupes stations across pages by the
cmd=map&id= station ID. No backfill exists in this source, so history
accumulates from the first poll.
Dashboard: static HTML + Chart.js in site/, served by GH Pages, reading
only site/data/*.json. v1 views: current prices sorted with color vs each
station's 7-day average, per-station trend chart with picker, area median lines
for 95/98/dsl. v2 (deferred until weeks of data exist): day-of-week heatmap,
"fill now or wait" signal.

Key decisions and rules

Ingest every row from every configured page; the 15 km Helsinki radius is a
display-time filter in the dashboard (config), never an ingest filter
Dedupe on UNIQUE(station_id, fuel, date); source has date-only resolution
(DD.MM., no year: rollover rule resolves it), latest price wins within a day
Coordinates are static: cached in a stations table, fetched once per new station.
The hoped-for ajax.php?act=map bulk endpoint turned out dead (always returns an
empty body, tested 2026-07-09) — coords come from one request per new station's
map page instead, cached forever
Parse rows by 5-td count, not class (regional pages omit the E10 class); strip
the V-Power */E99 marker from 98E; skip the ~5-8 % of rows without map links
Sanity bounds: price 0.80–4.00 EUR, Finland bbox lat 59.7–70.1, lon 20.5–31.6
Politeness is hard policy: 12 h cadence, 100 ms between requests, honest
User-Agent, respect robots.txt (someone else's crowdsourced site)
GH Pages serves site/, never docs/ (plan docs live there)
No LLM in the poller (deterministic script; Claude Code Routine rejected)

Niklas's working context
Builds with Claude Code on Windows. Comfortable with Python, SQLite, Git, GH
Actions, Chart.js (used in his tech-digest and news-summarizer projects). Prefers
minimal direct answers, no em dashes, English responses. Global rule: Claude Code
never commits or pushes autonomously.