# Tankille API Contract (reverse-engineered, unofficial)

Verified 2026-07-08 from source of:
- `github.com/jeffeeeee/tankille` (TypeScript client, npm `@jeffe/tankille`)
- `github.com/aarooh/ha-tankille-deprecated` (Python/aiohttp Home Assistant client)

Unofficial API. It can change or be blocked at any time. Be polite: one request per
poll cycle, 3 h interval, no hammering. If it breaks, check those two repos and the
HA community first.

## Base URL

```
https://api.tankille.fi
```

## Auth flow

1. `POST /auth/login`
   Body: `{ "device": "<device string>", "email": "...", "password": "..." }`
   Returns: `{ "refreshToken": "..." }`
   Note: some device strings get "Device blacklisted" — reuse the HA client's:
   `"Android SDK built for x86_64 (03280ceb8a5367a6)"`
2. `POST /auth/refresh`
   Body: `{ "token": "<refreshToken>" }`
   Returns: `{ "accessToken": "..." }` — valid 12 h, cache and reuse for ~10 h
3. All data requests send header `x-access-token: <accessToken>`

Persist the refresh token (upstream Python client saves tokens to a file) so login
happens rarely, not every poll.

## Endpoints

### All stations in a radius (the poll request)

```
GET /stations?location=<lon>,<lat>&distance=<meters>
```

Note the order: **lon,lat**. Returns an array of station objects with current prices
for every fuel the station sells. This single request is the entire recurring poll.

### Per-station price history (backfill only)

```
GET /stations/<station_id>/prices?since=<date>
```

Upstream default window: 14 days. Used once on first run to seed history.

## Station object shape

```jsonc
{
  "_id": "57468337076757d9a7acf610",
  "name": "...",
  "chain": "...",
  "brand": "...",
  "address": { "street": "...", "city": "...", "zipcode": "...", "country": "..." },
  "location": { "type": "Point", "coordinates": [lon, lat] },
  "fuels": ["95", "98", "dsl", ...],
  "price": [
    {
      "tag": "95",          // fuel type
      "price": 1.899,
      "updated": "...",     // report timestamp — dedupe key component
      "delta": 0,
      "reporter": "...",    // DROP AT INGEST — never store or publish
      "_id": "..."
    }
  ],
  "updated": "..."
}
```

Fuel tags seen in upstream types: `95, 98, dsl, ngas, bgas, 98+, dsl+, 85, hvo`.
Ingest all of them; the display layer filters.

## Client implementation notes

- Sync `requests` is fine; no need for aiohttp at one request per 3 h
- Set a User-Agent that identifies this as a small personal poller — chill and honest
- On 401, refresh the access token; on refresh failure, full re-login
- Treat any non-200 as a failed poll: log and exit nonzero so the Actions run shows red,
  but never retry-loop aggressively against the API
