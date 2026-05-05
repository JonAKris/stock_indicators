"""
load_eoddata_history.py
=======================

Bulk-load 5 years of end-of-day quote history into ``public.symbol_quote``
from the eoddata.com REST API.

The script reads connection settings from the same ``.env`` file used by
the Dash app and writes rows that are strictly normalized to the
schema in ``schema.sql``:

    public.symbol_quote (
        exchange_code   text         NOT NULL,
        symbol_code     text         NOT NULL,
        interval_code   text         NOT NULL,   -- d/w/m/q/y/1/5/10/15/30/h
        as_of_date      date         NOT NULL,
        name            text,
        open_price      numeric(12,4),
        high_price      numeric(12,4),           -- >= low_price
        low_price       numeric(12,4),
        close_price     numeric(12,4),
        adjusted_close  numeric(12,4),
        volume          bigint       NOT NULL,
        open_interest   bigint,
        bid_price       numeric(12,4),
        ask_price       numeric(12,4),
        previous_price  numeric(12,4),
        change_amount   numeric(12,4),
        currency        char(3)
    );
    PRIMARY KEY (exchange_code, symbol_code, interval_code, as_of_date)

Authentication & endpoint
-------------------------
The eoddata.com REST API authenticates with an ``ApiKey`` query
parameter. The historical quote endpoint is path-based:

    GET https://api.eoddata.com/Quote/List/{Exchange}/{Symbol}
        ?ApiKey=...&Interval=d
        &FromDateStamp=MM/DD/YYYY&ToDateStamp=MM/DD/YYYY

The base URL and path prefix are both env-configurable
(``EOD_REST_BASE_URL`` and ``EOD_REST_HISTORY_PATH``) in case eoddata
moves things around.

Usage
-----
    # Load every (exchange, symbol) pair listed in public.symbol:
    python load_eoddata_history.py

    # Specific exchanges / symbols (repeatable flags):
    python load_eoddata_history.py --exchange NASDAQ --symbol AAPL --symbol MSFT

    # Custom window (default = 5 years back to today):
    python load_eoddata_history.py --years 10
    python load_eoddata_history.py --start 2020-01-01 --end 2024-12-31

    # Dry-run (fetch + normalize, no DB writes):
    python load_eoddata_history.py --dry-run --exchange NASDAQ --symbol AAPL
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("eoddata-loader")


REST_BASE_URL = os.getenv("EOD_REST_BASE_URL", "https://api.eoddata.com").rstrip("/")
REST_HISTORY_PATH = os.getenv("EOD_REST_HISTORY_PATH", "/Quote/List")
API_KEY = os.getenv("EOD_API_KEY", "").strip()

REQUEST_TIMEOUT = float(os.getenv("EOD_TIMEOUT", "180"))
REQUEST_DELAY = float(os.getenv("EOD_REQUEST_DELAY", "0.25"))    # seconds between calls
MAX_RETRIES = int(os.getenv("EOD_MAX_RETRIES", "3"))
INTERVAL_CODE = os.getenv("EOD_INTERVAL_CODE", "d")
BATCH_SIZE = int(os.getenv("EOD_BATCH_SIZE", "1000"))

DB_CONFIG = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "stockman"),
    user=os.getenv("DB_USER", "stockman"),
    password=os.getenv("DB_PASS", ""),
)


# ---------------------------------------------------------------------------
# Schema-defined constraints — single source of truth for normalization
# ---------------------------------------------------------------------------
ALLOWED_INTERVALS = {"d", "w", "m", "q", "y", "1", "5", "10", "15", "30", "h"}

# numeric(12, 4) -> 8 digits left of decimal, 4 right => |value| < 10^8
NUMERIC_MAX = Decimal("99999999.9999")
NUMERIC_QUANT = Decimal("0.0001")

# bigint range
BIGINT_MIN = -(2 ** 63)
BIGINT_MAX = (2 ** 63) - 1


# ---------------------------------------------------------------------------
# Quote row mapped 1:1 to public.symbol_quote
# ---------------------------------------------------------------------------
@dataclass
class Quote:
    exchange_code: str
    symbol_code: str
    interval_code: str
    as_of_date: date
    name: Optional[str] = None
    open_price: Optional[Decimal] = None
    high_price: Optional[Decimal] = None
    low_price: Optional[Decimal] = None
    close_price: Optional[Decimal] = None
    adjusted_close: Optional[Decimal] = None
    volume: int = 0
    open_interest: Optional[int] = None
    bid_price: Optional[Decimal] = None
    ask_price: Optional[Decimal] = None
    previous_price: Optional[Decimal] = None
    change_amount: Optional[Decimal] = None
    currency: Optional[str] = None

    # Column order matches the INSERT below.
    def as_tuple(self) -> tuple:
        return (
            self.exchange_code, self.symbol_code, self.interval_code, self.as_of_date,
            self.name, self.open_price, self.high_price, self.low_price, self.close_price,
            self.adjusted_close, self.volume, self.open_interest, self.bid_price,
            self.ask_price, self.previous_price, self.change_amount, self.currency,
        )


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------
class NormalizationError(ValueError):
    """Raised when a raw row cannot be coerced into a valid Quote."""


def norm_text(v, max_len: Optional[int] = None) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if max_len and len(s) > max_len:
        s = s[:max_len]
    return s


def norm_currency(v) -> Optional[str]:
    """char(3): exactly three uppercase letters or NULL."""
    s = norm_text(v)
    if s is None:
        return None
    s = s.upper()
    if len(s) != 3 or not s.isalpha():
        return None
    return s


def norm_interval(v) -> str:
    s = norm_text(v) or INTERVAL_CODE
    s = s.lower()
    if s not in ALLOWED_INTERVALS:
        raise NormalizationError(f"interval_code '{s}' not in {sorted(ALLOWED_INTERVALS)}")
    return s


def norm_price(v) -> Optional[Decimal]:
    """numeric(12,4): four decimal places, |value| <= 10^8 - 1e-4."""
    if v is None or v == "":
        return None
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite():
        return None
    # Ignore obviously bogus zeros from APIs that pad missing fields with 0.
    # We *keep* zero — it can be legitimate — but cap absurd magnitudes.
    if abs(d) > NUMERIC_MAX:
        raise NormalizationError(f"price {d} exceeds numeric(12,4) range")
    return d.quantize(NUMERIC_QUANT, rounding=ROUND_HALF_UP)


def norm_bigint(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        # Tolerate "1,234,567" and "1234567.0".
        if isinstance(v, str):
            v = v.replace(",", "").strip()
        i = int(Decimal(str(v)))
    except (InvalidOperation, ValueError):
        return None
    if i < BIGINT_MIN or i > BIGINT_MAX:
        raise NormalizationError(f"integer {i} outside bigint range")
    return i


_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%Y%m%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
)


def norm_date(v) -> date:
    if v is None or v == "":
        raise NormalizationError("missing date")
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    # Strip trailing Z and any sub-second/timezone tail beyond microseconds.
    s = re.sub(r"Z$", "", s)
    s = re.sub(r"([+-]\d{2}:?\d{2})$", "", s)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s[: max(len(fmt), 26)], fmt).date()
        except ValueError:
            continue
    # Last-ditch ISO parse.
    try:
        return datetime.fromisoformat(s).date()
    except ValueError as exc:
        raise NormalizationError(f"unparseable date {v!r}") from exc


def normalize_row(
    raw: dict,
    exchange_code: str,
    symbol_code: str,
    interval_code: str,
    default_currency: Optional[str] = None,
) -> Quote:
    """Convert a single raw API row into a schema-conformant Quote.

    Raises NormalizationError if the row cannot be salvaged.
    """
    def pick(*keys):
        for k in keys:
            if k in raw and raw[k] not in (None, ""):
                return raw[k]
        return None

    as_of = norm_date(pick(
        # eoddata.com /Quote/List uses 'dateStamp' (camelCase)
        "dateStamp",
        # Other casings / vendors
        "DateTime", "Date", "QuoteDate", "AsOfDate", "DATE", "DATETIME", "TradeDate",
    ))

    o = norm_price(pick("open", "Open", "OPEN"))
    h = norm_price(pick("high", "High", "HIGH"))
    low = norm_price(pick("low", "Low", "LOW"))
    c = norm_price(pick("close", "Close", "CLOSE"))

    # Schema constraint: high_price >= low_price. If both present and inverted,
    # try to recover by swapping; if only one side is implausible, drop both.
    if h is not None and low is not None and h < low:
        # Some feeds occasionally swap these. Swap rather than discard.
        h, low = low, h

    vol_raw = pick("volume", "Volume", "VOLUME")
    volume = norm_bigint(vol_raw)
    if volume is None:
        volume = 0  # column is NOT NULL
    if volume < 0:
        volume = 0

    quote = Quote(
        exchange_code=exchange_code,
        symbol_code=symbol_code,
        interval_code=interval_code,
        as_of_date=as_of,
        name=norm_text(pick("name", "Name", "Description", "NAME", "DESCRIPTION")),
        open_price=o,
        high_price=h,
        low_price=low,
        close_price=c,
        adjusted_close=norm_price(pick(
            "adjustedClose", "AdjustedClose", "Adjusted_Close", "AdjClose", "Adj_Close",
        )),
        volume=volume,
        open_interest=norm_bigint(pick(
            "openInterest", "OpenInterest", "OPENINTEREST", "Open_Interest",
        )),
        bid_price=norm_price(pick("bid", "Bid", "BID")),
        ask_price=norm_price(pick("ask", "Ask", "ASK")),
        previous_price=norm_price(pick(
            "previous", "Previous", "PreviousClose", "previousClose", "PREVIOUS", "PreviousPrice",
        )),
        change_amount=norm_price(pick(
            "change", "Change", "CHANGE", "ChangeAmount", "changeAmount",
        )),
        currency=norm_currency(pick("currency", "Currency", "CURRENCY")) or default_currency,
    )
    return quote


# ---------------------------------------------------------------------------
# REST client
# ---------------------------------------------------------------------------
class EodDataClient:
    """Thin wrapper around the eoddata.com REST API."""

    def __init__(self):
        if not API_KEY:
            raise RuntimeError(
                "EOD_API_KEY is not set. Add it to your .env (see .env.example)."
            )
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json,text/xml;q=0.9",
            "User-Agent": "stock-charting-loader/1.0",
        })

    def symbol_history(
        self,
        exchange: str,
        symbol: str,
        start_date: date,
        end_date: date,
        interval: str = INTERVAL_CODE,
    ) -> list[dict]:
        """Return a list of raw quote dicts for [start_date, end_date] inclusive.

        Endpoint shape (verified against eoddata.com):
            GET https://api.eoddata.com/Quote/List/{Exchange}/{Symbol}
                ?ApiKey=...&Interval=d&FromDateStamp=MM/DD/YYYY&ToDateStamp=MM/DD/YYYY
        """
        url = f"{REST_BASE_URL}{REST_HISTORY_PATH}/{exchange}/{symbol}"
        params = {
            "ApiKey": API_KEY,
            "Interval": interval,
            "FromDateStamp": start_date.strftime("%m/%d/%Y"),
            "ToDateStamp": end_date.strftime("%m/%d/%Y"),
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            except requests.RequestException as exc:
                log.warning("Network error %s:%s attempt %d/%d: %s",
                            exchange, symbol, attempt, MAX_RETRIES, exc)
                time.sleep(min(2 ** attempt, 10))
                continue

            if resp.status_code == 401 or resp.status_code == 403:
                log.error("Auth rejected (%d). Check EOD_API_KEY.", resp.status_code)
                return []
            if resp.status_code == 404:
                return []
            if resp.status_code == 429:
                wait = min(2 ** attempt, 30)
                log.warning("Rate limited; sleeping %ds", wait)
                time.sleep(wait)
                continue
            if not resp.ok:
                log.warning("HTTP %d for %s:%s — %s",
                            resp.status_code, exchange, symbol, resp.text[:200])
                time.sleep(min(2 ** attempt, 10))
                continue

            return self._parse_response(resp)

        return []

    @staticmethod
    def _parse_response(resp: requests.Response) -> list[dict]:
        ctype = resp.headers.get("Content-Type", "").lower()
        text = resp.text or ""
        # Try JSON first regardless of declared content-type.
        if "json" in ctype or text.lstrip().startswith(("[", "{")):
            try:
                payload = resp.json()
            except ValueError:
                payload = None
            if payload is not None:
                return _coerce_to_list(payload)
        # Otherwise treat as XML.
        return _xml_to_dicts(text)


def _coerce_to_list(payload) -> list[dict]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("Quotes", "QUOTES", "Data", "data", "Results", "results", "History", "Items"):
            v = payload.get(key)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
        # Sometimes the JSON itself is a single quote dict.
        if any(k in payload for k in ("Open", "Close", "High", "Low", "DateTime", "Date")):
            return [payload]
    return []


def _xml_to_dicts(text: str) -> list[dict]:
    if not text.strip():
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    rows: list[dict] = []
    # Match both <QUOTE .../> attribute-style and <Quote><Open>...</Open></Quote> child-style.
    for el in root.iter():
        tag = el.tag.split("}", 1)[-1]  # strip namespace
        if tag.upper() not in {"QUOTE", "HISTORY", "ITEM"}:
            continue
        if el.attrib:
            rows.append(dict(el.attrib))
        else:
            row = {child.tag.split("}", 1)[-1]: (child.text or "").strip() for child in el}
            if row:
                rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------
UPSERT_SQL = """
INSERT INTO public.symbol_quote (
    exchange_code, symbol_code, interval_code, as_of_date,
    name, open_price, high_price, low_price, close_price,
    adjusted_close, volume, open_interest, bid_price, ask_price,
    previous_price, change_amount, currency
) VALUES %s
ON CONFLICT (exchange_code, symbol_code, interval_code, as_of_date)
DO UPDATE SET
    name           = EXCLUDED.name,
    open_price     = EXCLUDED.open_price,
    high_price     = EXCLUDED.high_price,
    low_price      = EXCLUDED.low_price,
    close_price    = EXCLUDED.close_price,
    adjusted_close = EXCLUDED.adjusted_close,
    volume         = EXCLUDED.volume,
    open_interest  = EXCLUDED.open_interest,
    bid_price      = EXCLUDED.bid_price,
    ask_price      = EXCLUDED.ask_price,
    previous_price = EXCLUDED.previous_price,
    change_amount  = EXCLUDED.change_amount,
    currency       = EXCLUDED.currency;
"""


@dataclass
class LoadStats:
    fetched: int = 0
    normalized: int = 0
    rejected: int = 0
    written: int = 0
    failures: list[str] = field(default_factory=list)


def fetch_targets(
    conn,
    exchanges_filter: Optional[list[str]],
    symbols_filter: Optional[list[str]],
) -> list[tuple[str, str, Optional[str]]]:
    """Return a list of (exchange_code, symbol_code, currency) to load.

    Currency is pulled from public.symbol so it can serve as a fallback when
    the API response doesn't include it.
    """
    sql = "SELECT exchange_code, symbol_code, currency FROM public.symbol"
    params: list = []
    where: list[str] = []
    if exchanges_filter:
        where.append("exchange_code = ANY(%s)")
        params.append(exchanges_filter)
    if symbols_filter:
        where.append("symbol_code = ANY(%s)")
        params.append(symbols_filter)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY exchange_code, symbol_code"

    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [(r[0], r[1], r[2]) for r in cur.fetchall()]


def write_quotes(conn, quotes: list[Quote], dry_run: bool = False) -> int:
    if not quotes:
        return 0
    if dry_run:
        return len(quotes)

    rows = [q.as_tuple() for q in quotes]
    written = 0
    with conn.cursor() as cur:
        for i in range(0, len(rows), BATCH_SIZE):
            chunk = rows[i:i + BATCH_SIZE]
            psycopg2.extras.execute_values(cur, UPSERT_SQL, chunk, page_size=len(chunk))
            written += len(chunk)
    conn.commit()
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--exchange", action="append", help="Filter to specific exchange(s); repeatable.")
    p.add_argument("--symbol", action="append", help="Filter to specific symbol(s); repeatable.")
    p.add_argument("--years", type=int, default=5, help="Years of history to load (default 5).")
    p.add_argument("--start", type=str, help="Start date YYYY-MM-DD (overrides --years).")
    p.add_argument("--end", type=str, help="End date YYYY-MM-DD (default today).")
    p.add_argument("--interval", default=INTERVAL_CODE,
                   help=f"Interval code (default {INTERVAL_CODE}). Allowed: {sorted(ALLOWED_INTERVALS)}.")
    p.add_argument("--dry-run", action="store_true", help="Fetch and normalize but don't write to DB.")
    p.add_argument("--limit", type=int, help="Only process the first N (exchange, symbol) pairs.")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    # Validate interval against schema-allowed set.
    try:
        interval = norm_interval(args.interval)
    except NormalizationError as exc:
        log.error(str(exc))
        return 2

    # Resolve date window.
    end_date = norm_date(args.end) if args.end else date.today()
    if args.start:
        start_date = norm_date(args.start)
    else:
        # Approximate years -> days; leap years handled near enough for a backfill.
        start_date = end_date - timedelta(days=int(round(args.years * 365.25)))
    if start_date > end_date:
        log.error("Start date %s is after end date %s.", start_date, end_date)
        return 2

    log.info("Loading %s history from %s to %s", interval, start_date, end_date)

    try:
        client = EodDataClient()
    except RuntimeError as exc:
        log.error(str(exc))
        return 2

    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except psycopg2.OperationalError as exc:
        log.error("Cannot connect to PostgreSQL: %s", exc)
        return 2

    stats = LoadStats()

    try:
        targets = fetch_targets(conn, args.exchange, args.symbol)
        if args.limit:
            targets = targets[: args.limit]
        if not targets:
            log.warning("No (exchange, symbol) pairs matched. Is public.symbol populated?")
            return 1

        log.info("Will load %d symbol(s)", len(targets))

        for i, (exchange, symbol, default_currency) in enumerate(targets, 1):
            try:
                raw_rows = client.symbol_history(exchange, symbol, start_date, end_date, interval)
                stats.fetched += len(raw_rows)

                quotes: list[Quote] = []
                reject_reasons: dict[str, int] = {}
                for r in raw_rows:
                    try:
                        q = normalize_row(r, exchange, symbol, interval, default_currency)
                    except NormalizationError as exc:
                        stats.rejected += 1
                        reason = str(exc).split(":", 1)[0][:60]
                        reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
                        continue
                    if not (start_date <= q.as_of_date <= end_date):
                        stats.rejected += 1
                        reject_reasons["out-of-window"] = reject_reasons.get("out-of-window", 0) + 1
                        continue
                    quotes.append(q)

                # If everything got rejected, surface why and show a sample row
                # so we can fix the field-name mapping.
                if raw_rows and not quotes:
                    log.warning(
                        "%s:%s — all %d rows rejected. Reasons: %s",
                        exchange, symbol, len(raw_rows),
                        ", ".join(f"{k}={v}" for k, v in reject_reasons.items()) or "(none captured)",
                    )
                    log.warning("%s:%s — sample raw row: %r",
                                exchange, symbol, raw_rows[0])

                # Final defensive de-dup on PK in case the API returns repeats.
                deduped: dict[date, Quote] = {}
                for q in quotes:
                    deduped[q.as_of_date] = q
                quotes = list(deduped.values())

                stats.normalized += len(quotes)
                written = write_quotes(conn, quotes, dry_run=args.dry_run)
                stats.written += written

                log.info(
                    "[%d/%d] %s:%s  fetched=%d  kept=%d  written=%d%s",
                    i, len(targets), exchange, symbol,
                    len(raw_rows), len(quotes), written,
                    " (dry-run)" if args.dry_run else "",
                )
            except Exception as exc:
                stats.failures.append(f"{exchange}:{symbol} — {exc}")
                log.exception("Failed loading %s:%s", exchange, symbol)
            finally:
                if REQUEST_DELAY:
                    time.sleep(REQUEST_DELAY)

        log.info(
            "Done. fetched=%d  normalized=%d  rejected=%d  %s=%d  failures=%d",
            stats.fetched, stats.normalized, stats.rejected,
            "would-write" if args.dry_run else "written", stats.written,
            len(stats.failures),
        )
        if stats.failures:
            for f in stats.failures[:10]:
                log.warning("  failure: %s", f)
            if len(stats.failures) > 10:
                log.warning("  ... and %d more", len(stats.failures) - 10)
        return 0 if not stats.failures else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
