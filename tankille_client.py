"""Minimal sync client for the unofficial Tankille API.

Contract: docs/API.md. The API is tolerated, not blessed — one location request
per poll, no retry storms, honest User-Agent.
"""

import json
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "https://api.tankille.fi"

# Some device strings get "Device blacklisted" — this one is known good (docs/API.md).
DEVICE = "Android SDK built for x86_64 (03280ceb8a5367a6)"

USER_AGENT = "helsinki-fuel-dash/0.1 (personal fuel price poller; 1 location request / 3 h)"

# Access tokens live 12 h; reuse for 10 before refreshing.
ACCESS_TOKEN_TTL_S = 10 * 3600


class TankilleError(RuntimeError):
    """Any non-recoverable API failure. Callers should log and exit nonzero."""


class TankilleClient:
    def __init__(self, email: str, password: str, token_file: Path):
        self._email = email
        self._password = password
        self._token_file = Path(token_file)
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT
        self._tokens = self._load_tokens()

    # -- token handling --------------------------------------------------

    def _load_tokens(self) -> dict:
        try:
            return json.loads(self._token_file.read_text())
        except (OSError, ValueError):
            return {}

    def _save_tokens(self) -> None:
        self._token_file.write_text(json.dumps(self._tokens))

    def _login(self) -> None:
        resp = self._session.post(
            f"{BASE_URL}/auth/login",
            json={"device": DEVICE, "email": self._email, "password": self._password},
            timeout=30,
        )
        if resp.status_code != 200:
            raise TankilleError(f"login failed: HTTP {resp.status_code}")
        self._tokens = {"refresh_token": resp.json()["refreshToken"]}
        self._save_tokens()

    def _refresh(self) -> None:
        """Get a fresh access token; falls back to a full login once."""
        if not self._tokens.get("refresh_token"):
            self._login()
        resp = self._session.post(
            f"{BASE_URL}/auth/refresh",
            json={"token": self._tokens["refresh_token"]},
            timeout=30,
        )
        if resp.status_code != 200:
            # Refresh token expired or revoked — re-login and try once more.
            self._login()
            resp = self._session.post(
                f"{BASE_URL}/auth/refresh",
                json={"token": self._tokens["refresh_token"]},
                timeout=30,
            )
            if resp.status_code != 200:
                raise TankilleError(f"token refresh failed: HTTP {resp.status_code}")
        self._tokens["access_token"] = resp.json()["accessToken"]
        self._tokens["access_token_at"] = time.time()
        self._save_tokens()

    def _access_token(self) -> str:
        age = time.time() - self._tokens.get("access_token_at", 0)
        if not self._tokens.get("access_token") or age > ACCESS_TOKEN_TTL_S:
            self._refresh()
        return self._tokens["access_token"]

    # -- data endpoints ---------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> list | dict:
        resp = self._session.get(
            f"{BASE_URL}{path}",
            params=params,
            headers={"x-access-token": self._access_token()},
            timeout=30,
        )
        if resp.status_code == 401:
            # Stale token despite the TTL margin — refresh once, no retry loops.
            self._refresh()
            resp = self._session.get(
                f"{BASE_URL}{path}",
                params=params,
                headers={"x-access-token": self._tokens["access_token"]},
                timeout=30,
            )
        if resp.status_code != 200:
            raise TankilleError(f"GET {path} failed: HTTP {resp.status_code}")
        return resp.json()

    def get_stations_by_location(self, lat: float, lon: float, distance: int) -> list[dict]:
        # API expects lon,lat — not lat,lon.
        return self._get("/stations", {"location": f"{lon},{lat}", "distance": distance})

    def get_station_prices(self, station_id: str, since: datetime) -> list[dict]:
        since_str = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        return self._get(f"/stations/{station_id}/prices", {"since": since_str})
