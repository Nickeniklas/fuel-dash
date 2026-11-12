# AUDIT — fuel-dash

Read-only audit at `20a8b2e`, 2026-11-11. Covers every tracked source file,
both workflows, the docs, the two SQLite files (opened read-only) and all 225
commits of history. No network requests were made. The 99 unit tests pass.

**Security summary:** nothing found. History holds no credentials, the
dashboard has no injection path, and there is no auth surface to get wrong.
Details are in section 3. The findings below are all reliability and
correctness.

## 1. Top 5 findings (impact vs effort)

### 1. One failed secondary request discards a whole poll's prices

- `coords.py:40-41`, called in the loop at `coords.py:64-70` with no
  `try`; `poll.py:44`; `.github/workflows/poll.yml:49-50` vs `:55`.
- **Why it matters.** Prices are written to `fuel.db` in the runner workspace,
  but the file only survives if every later step succeeds. Three things can
  fail after or around the scrape, and each one fails the job before the
  commit step:
  - a single station's map page erroring (verified: a `ConnectionError` in
    `fetch_coords` propagates out of `fetch_missing_coords`);
  - any one of the four listing pages erroring (`raise_for_status` in
    `fetch_page`, uncaught in `poll()`);
  - the EU bulletin download failing or timing out, which runs between the
    poll and the commit.

  The source shows only about 5 days, so a failure that persists (a station
  whose map page is permanently broken, an EC outage in a download week)
  becomes a permanent hole like the September one. A persistent map-page error
  blocks every poll until someone intervenes.
- **Fix.** Catch `requests.RequestException` per station in
  `fetch_missing_coords` and per page in `poll()` (log, continue, fail only if
  every page failed). Add `continue-on-error: true` to the "Update EU
  bulletin" step, or move it after the commit.

### 2. A scrape that parses zero rows exits 0 and the workflow stays green

- `poll.py:45-58`; `eu_bulletin.py:139-141` and `:198-204`.
- **Why it matters.** If polttoaine.net changes its markup, or serves the
  blank results page that `docs/SCRAPER.md:19-20` already documents as a
  silent failure mode, `parse_page` returns `[]` (verified), `poll()` logs
  "ingested 0 rows", and the job reports "No changes to commit" with a green
  tick. Nothing signals the breakage, and after 5 days the data is gone for
  good. The bulletin has the same shape: if a header code is renamed,
  `parse_workbook` returns no rows, `update()` returns 0, and because the gate
  never closes it re-downloads the 4.5 MB workbook every 12 hours
  indefinitely, which also breaks the politeness rule.
- **Fix.** Make `poll()` raise when any page yields zero rows (or when the
  total is zero), and make `update()` raise when a download parses to zero
  rows. A failed run sends GitHub's failure email, which is the only alerting
  this project has.

### 3. Year-less dates are resolved against the runner's UTC date, not Helsinki's

- `poll.py:39-40`, `parser.py:49-50`.
- **Why it matters.** Between Finnish midnight and UTC midnight (21:00 or
  22:00 to 24:00 UTC), a price reported "today" in Finland is tomorrow by the
  runner's clock. The rollover rule then treats it as a future date and
  subtracts a year. Verified: `resolve_date('12.11.', date(2026, 11, 11))`
  returns `2025-11-12`. The row is only warned about, then stored and
  committed. One such row would also make `build_medians` (`export.py:207`)
  pad about a year of null entries onto the front of `medians.json`,
  flattening the median chart and inflating the coverage line.
- **Exposure.** 5 poll commits in history landed at 21 or 22 UTC (delayed
  cron or manual dispatch). It has not happened yet: the earliest date in
  `fuel.db` is 2026-07-05.
- **Fix.** Use `datetime.now(ZoneInfo("Europe/Helsinki")).date()` as the
  reference in `poll()`. Also drop, not just warn about, rows that resolve
  more than 7 days old in `resolve_date`, since the source cannot legitimately
  produce them. (On Windows `zoneinfo` needs the `tzdata` package; the Ubuntu
  runner does not.)

### 4. The robots.txt re-check is documented but does not exist

- `docs/SCRAPER.md:195-196` says the poller "re-checks and aborts if crawling
  becomes disallowed"; `README.md:109` calls robots.txt compliance deliberate.
  No Python file references robots.txt.
- **Why it matters.** This is one of the project's stated hard rules, and the
  only check ever made was the manual one on 2026-07-09. If the site later
  disallows crawling, the poller keeps going twice a day while the docs claim
  otherwise.
- **Fix.** Add a `urllib.robotparser` check at the top of `poll()` (stdlib,
  one extra request per run) that aborts if any configured page or the map
  page path is disallowed for the project's User-Agent. If that is not
  wanted, correct the doc instead.

### 5. Station names are frozen at first sight

- `db.py:93-100`.
- **Why it matters.** `INSERT OR IGNORE` never updates `name`, so a station
  that is rebranded or renamed on the source keeps its original name in the
  table, map popup, search and picker forever. The docstring says the name is
  "handled by `set_station_coords()`", which only writes `lat`/`lon`, so
  nothing handles it. `tests/test_db.py:41` pins the current behaviour.
- **Guess:** whether any of the 137 stations is currently mislabelled. That
  needs a comparison against the live site, which this audit did not do.
- **Fix.** Change the insert to an upsert that updates `name` and leaves
  `first_seen`, `lat` and `lon` alone, and update the pinned test.

### Smaller items, not ranked

- `.github/workflows/pages.yml:20-22`: `cancel-in-progress: true` in the
  shared `pages` group. By GitHub's documented semantics a site push can
  cancel a poll run that is mid-flight, possibly before its commit. Not
  tested here.
- `coords.py:62-70`: a station whose coordinates are missing or rejected by
  the bbox is refetched on every poll forever. Zero such stations today.
- `site/app.js:215-217`, `:238-240`: `localStorage` reads are wrapped in
  `try`, writes are not, so with storage blocked a favourite toggle throws
  before the table re-renders.
- Workflows pin actions by major tag (`@v5`, `@v6`) in a job with
  `contents: write`; `site/index.html:138-139` loads Leaflet and Chart.js
  without `integrity` attributes. Both are ordinary supply-chain exposure for
  a personal project.

## 2. Tests that would catch real breakage

Existing tests cover the parser, DB layer and export shapes well. What is
missing is everything `poll()` and `update()` do around those pieces: no test
calls `poll()` at all.

1. **`poll()` survives a partial failure.** Mock `fetch_page` to raise for one
   of several pages and `coords.requests.get` to raise for one station; assert
   the other pages' prices are in the DB afterwards. Covers finding 1.
2. **`poll()` fails loudly on an empty scrape.** Feed it the blank results
   page (worth saving as a fixture, since SCRAPER.md describes it) and assert
   it raises. Covers finding 2.
3. **A date one day ahead of the reference never lands in the previous year.**
   `resolve_date` with the cell dated reference + 1 day must not return a date
   about 365 days back, and `poll()` must take its reference from Helsinki
   time. Covers finding 3.
4. **`update()` fails loudly when the workbook header changes.** Build a
   workbook from the existing fixture generator with one row-1 code renamed,
   pass it through a mocked download, and assert it raises instead of
   returning 0. Covers the bulletin half of finding 2.
5. **Dashboard null handling (optional).** `site/app.js` has 1045 lines and no
   tests. The functions that carry the documented null-median contract
   (`computeReferenceDate`, `computeEuGap`, `computeStationPointCount`) are
   pure and could run under `node --test` with no new dependency, but the file
   would first need them reachable without the DOM bootstrap. Guess: I did not
   check that Node is installed here or how much restructuring this takes.

## 3. Verified, and not verified

**Verified**

- Git history, all 225 commits: the only credential-related file ever tracked
  is `.env.example` with empty `TANKILLE_EMAIL=` / `TANKILLE_PASSWORD=`
  values. No `.env`, token file or key was ever committed. The removed
  `tankille.db` held two empty tables. The removed Tankille client read
  credentials from the environment only.
- The contact email in the User-Agent (`parser.py:18`) is in a public repo.
  That is consistent with the honest-User-Agent rule, so it is noted, not
  flagged.
- No injection path in the dashboard: station names reach the DOM through
  `textContent` everywhere except the map popup, which uses `escapeHtml`
  (`app.js:474`). All SQL is parameterised.
- `fuel.db` and `eu.db` are internally consistent: no orphan price rows, no
  malformed dates, all 137 stations geocoded, all prices inside bounds, every
  bulletin date a Monday.

**Not verified**

- Anything about the live sites: current markup, the map page format, the
  bulletin layout, robots.txt contents. No requests were made.
- GitHub-side state: whether the old `TANKILLE_EMAIL` / `TANKILLE_PASSWORD`
  repository secrets still exist (worth deleting if so), branch protection,
  Pages settings, Actions run logs, and any commits on GitHub that are not in
  this clone.
- Whether any of the 5 runs at 21 to 22 UTC actually met a post-midnight
  report. The DB shows no damage, which is all that can be said.
- The `cancel-in-progress` interaction between the two workflows. It is
  reasoned from GitHub's documentation, not observed.
- Dashboard behaviour in a browser. `app.js` was read, not run.
- The weekly commentary routine that lives outside this repo.
