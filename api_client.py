"""
EODData API v1 client.

Handles authentication, rate-limit back-off (HTTP 429), transparent retries,
and maps each API path to a typed Python method.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import Config

logger = logging.getLogger(__name__)

_RETRY_STRATEGY = Retry(
    total=5,
    backoff_factor=1.0,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET"],
    raise_on_status=False,
)


class RateLimitError(Exception):
    """Raised when the API returns HTTP 429 and retries are exhausted."""


class EODDataClient:
    """Thin wrapper around the EODData REST API (v1)."""

    def __init__(self, config: Config) -> None:
        self._api_key = config.API_KEY
        self._base_url = config.API_BASE_URL.rstrip("/")
        self._delay = config.REQUEST_DELAY

        session = requests.Session()
        adapter = HTTPAdapter(max_retries=_RETRY_STRATEGY)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        self._session = session

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        require_auth: bool = True,
        max_429_retries: int = 6,
    ) -> Any:
        """
        Perform a GET request, handling 429 with exponential back-off.

        Returns the parsed JSON body (list or dict).
        """
        url = f"{self._base_url}{path}"
        query: dict[str, Any] = params or {}
        if require_auth:
            query["ApiKey"] = self._api_key

        for attempt in range(max_429_retries + 1):
            time.sleep(self._delay)
            resp = self._session.get(url, params=query, timeout=Config.TIMEOUT)

            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning("Rate-limited (429) on %s – waiting %ds (attempt %d)", path, wait, attempt + 1)
                if attempt == max_429_retries:
                    raise RateLimitError(f"Rate limit not lifted after {max_429_retries} retries for {path}")
                time.sleep(wait)
                continue

            if resp.status_code == 404:
                logger.debug("404 Not Found: %s", url)
                return None

            if resp.status_code == 401:
                raise PermissionError(f"Unauthorised – check EODDATA_API_KEY. URL: {url}")

            resp.raise_for_status()
            return resp.json()

        return None  # unreachable, but satisfies type checker

    # ------------------------------------------------------------------
    # Metadata (no API key required)
    # ------------------------------------------------------------------

    def list_exchange_types(self) -> list[dict]:
        return self._get("/ExchangeType/List", require_auth=False) or []

    def list_symbol_types(self) -> list[dict]:
        return self._get("/SymbolType/List", require_auth=False) or []

    def list_countries(self) -> list[dict]:
        return self._get("/Country/List", require_auth=False) or []

    def list_currencies(self) -> list[dict]:
        return self._get("/Currency/List", require_auth=False) or []

    # ------------------------------------------------------------------
    # Exchanges
    # ------------------------------------------------------------------

    def list_exchanges(self) -> list[dict]:
        return self._get("/Exchange/List") or []

    def get_exchange(self, exchange_code: str) -> dict | None:
        return self._get(f"/Exchange/Get/{exchange_code}")

    # ------------------------------------------------------------------
    # Symbols
    # ------------------------------------------------------------------

    def list_symbols(self, exchange_code: str) -> list[dict]:
        return self._get(f"/Symbol/List/{exchange_code}") or []

    def get_symbol(self, exchange_code: str, symbol_code: str) -> dict | None:
        return self._get(f"/Symbol/Get/{exchange_code}/{symbol_code}")

    # ------------------------------------------------------------------
    # Profiles (Corporate)
    # ------------------------------------------------------------------

    def list_profiles(self, exchange_code: str) -> list[dict]:
        return self._get(f"/Profile/List/{exchange_code}") or []

    def get_profile(self, exchange_code: str, symbol_code: str) -> dict | None:
        return self._get(f"/Profile/Get/{exchange_code}/{symbol_code}")

    # ------------------------------------------------------------------
    # Quotes
    # ------------------------------------------------------------------

    def list_quotes_by_exchange(
        self, exchange_code: str, date_stamp: str | None = None
    ) -> list[dict]:
        params = {}
        if date_stamp:
            params["DateStamp"] = date_stamp
        return self._get(f"/Quote/List/{exchange_code}", params=params) or []

    def get_quote(
        self, exchange_code: str, symbol_code: str, date_stamp: str | None = None
    ) -> dict | None:
        params = {}
        if date_stamp:
            params["DateStamp"] = date_stamp
        return self._get(f"/Quote/Get/{exchange_code}/{symbol_code}", params=params)

    def list_quotes_by_symbol(
        self,
        exchange_code: str,
        symbol_code: str,
        interval: str = "d",
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {"Interval": interval}
        if from_date:
            params["FromDateStamp"] = from_date
        if to_date:
            params["ToDateStamp"] = to_date
        return self._get(f"/Quote/List/{exchange_code}/{symbol_code}", params=params) or []

    # ------------------------------------------------------------------
    # Fundamentals
    # ------------------------------------------------------------------

    def list_fundamentals(self, exchange_code: str) -> list[dict]:
        return self._get(f"/Fundamental/List/{exchange_code}") or []

    def get_fundamental(self, exchange_code: str, symbol_code: str) -> dict | None:
        return self._get(f"/Fundamental/Get/{exchange_code}/{symbol_code}")

    # ------------------------------------------------------------------
    # Technical Indicators
    # ------------------------------------------------------------------

    def list_technicals(self, exchange_code: str) -> list[dict]:
        return self._get(f"/Technical/List/{exchange_code}") or []

    def get_technical(self, exchange_code: str, symbol_code: str) -> dict | None:
        return self._get(f"/Technical/Get/{exchange_code}/{symbol_code}")

    # ------------------------------------------------------------------
    # Splits & Dividends
    # ------------------------------------------------------------------

    def list_splits_by_exchange(self, exchange_code: str) -> list[dict]:
        return self._get(f"/Splits/List/{exchange_code}") or []

    def list_splits_by_symbol(self, exchange_code: str, symbol_code: str) -> list[dict]:
        return self._get(f"/Splits/List/{exchange_code}/{symbol_code}") or []

    def list_dividends_by_exchange(self, exchange_code: str) -> list[dict]:
        return self._get(f"/Dividends/List/{exchange_code}") or []

    def list_dividends_by_symbol(self, exchange_code: str, symbol_code: str) -> list[dict]:
        return self._get(f"/Dividends/List/{exchange_code}/{symbol_code}") or []
