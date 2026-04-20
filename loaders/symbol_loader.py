"""
Symbol loader – fetches and stores data for all symbols within an exchange.

Covers:
  - symbol            ← /Symbol/List/{exchangeCode}
  - symbol_profile    ← /Profile/List/{exchangeCode}
  - symbol_fundamental← /Fundamental/List/{exchangeCode}
  - symbol_technical  ← /Technical/List/{exchangeCode}
  - symbol_quote      ← /Quote/List/{exchangeCode}
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import psycopg2

from api_client import EODDataClient
from database import upsert_rows

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Field mapping helpers
# ---------------------------------------------------------------------------

def _safe_decimal(value: Any) -> Any:
    """Return the value if it's a valid number, else None."""
    if value is None:
        return None
    try:
        f = float(value)
        # Postgres numeric(10,4) max: 999999.9999
        if abs(f) > 999999.9999:
            return None
        return f
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Any:
    """Return an integer or None."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_date(value: Any) -> Any:
    """Return a date string (yyyy-MM-dd) or None.  Handles datetime strings."""
    if not value:
        return None
    # API returns ISO-8601; we only need the date part
    return str(value)[:10]


# ---------------------------------------------------------------------------
# Per-table transform functions
# ---------------------------------------------------------------------------

def _transform_symbol(r: dict, exchange_code: str) -> dict:
    return {
        "exchange_code": exchange_code,
        "symbol_code": r.get("code", ""),
        "name": r.get("name", ""),
        "type": r.get("type"),
        "currency": (r.get("currency") or "")[:3] or None,
        "figi": r.get("figi"),
        "as_of_date": _safe_date(r.get("dateStamp")) or str(date.today()),
        "open_price": _safe_decimal(r.get("open")),
        "high_price": _safe_decimal(r.get("high")),
        "low_price": _safe_decimal(r.get("low")),
        "close_price": _safe_decimal(r.get("close")),
        "volume": _safe_int(r.get("volume")),
        "open_interest": _safe_int(r.get("openInterest")),
        "previous_price": _safe_decimal(r.get("previous")),
        "change_amount": _safe_decimal(r.get("change")),
        "bid_price": _safe_decimal(r.get("bid")),
        "ask_price": _safe_decimal(r.get("ask")),
    }


def _transform_profile(r: dict) -> dict:
    return {
        "exchange_code": r.get("exchangeCode", ""),
        "symbol_code": r.get("symbolCode", ""),
        "name": r.get("name", ""),
        "description": r.get("description"),
        "type": r.get("type"),
        "currency": (r.get("currency") or "")[:3] or None,
        "country": r.get("country"),
        "figi": r.get("figi"),
        "isin": r.get("isin"),
        "cusip": r.get("cusip"),
        "cik": r.get("cik"),
        "lei": r.get("lei"),
        "sector": r.get("sector"),
        "industry": r.get("industry"),
        "about": r.get("about"),
        "address": r.get("address"),
        "phone": r.get("phone"),
        "website": r.get("website"),
    }


def _transform_fundamental(r: dict) -> dict:
    return {
        "exchange_code": r.get("exchangeCode", ""),
        "symbol_code": r.get("symbolCode", ""),
        "market_capitalization": _safe_decimal(r.get("marketCapitalization")),
        "ebitda": _safe_decimal(r.get("ebitda")),
        "peg": _safe_decimal(r.get("peg")),
        "book_value": _safe_decimal(r.get("bookValue")),
        "dividend_per_share": _safe_decimal(r.get("dividendPerShare")),
        "dividend_yield": _safe_decimal(r.get("dividendYield")),
        "earnings_per_share": _safe_decimal(r.get("earningsPerShare")),
        "revenue_per_share": _safe_decimal(r.get("revenuePerShare")),
        "price_to_sales": _safe_decimal(r.get("priceToSales")),
        "price_to_book": _safe_decimal(r.get("priceToBook")),
        "beta": _safe_decimal(r.get("beta")),
        "shares_outstanding": _safe_int(r.get("sharesOutstanding")),
        "dividend_date": _safe_date(r.get("dividendDate")),
        "gross_margin": _safe_decimal(r.get("grossMargin")),
        "profit_margin": _safe_decimal(r.get("profitMargin")),
        "operating_margin": _safe_decimal(r.get("operatingMargin")),
        "return_on_assets": _safe_decimal(r.get("returnOnAssets")),
        "return_on_equity": _safe_decimal(r.get("returnOnEquity")),
        "revenue": _safe_decimal(r.get("revenue")),
        "gross_profit": _safe_decimal(r.get("grossProfit")),
        "trailing_pe": _safe_decimal(r.get("trailingPE")),
        "forward_pe": _safe_decimal(r.get("forwardPE")),
        "total_cash": _safe_decimal(r.get("totalCash")),
        "total_cash_per_share": _safe_decimal(r.get("totalCashPerShare")),
        "total_debt": _safe_decimal(r.get("totalDebt")),
        "total_debt_to_equity": _safe_decimal(r.get("totalDebtToEquity")),
        "book_value_per_share": _safe_decimal(r.get("bookValuePerShare")),
    }


def _transform_technical(r: dict) -> dict:
    return {
        "exchange_code": r.get("exchangeCode", ""),
        "symbol_code": r.get("symbolCode", ""),
        "as_of_date": _safe_date(r.get("dateStamp")) or str(date.today()),
        "quarter_change": _safe_decimal(r.get("quarterChange")),
        "biannual_change": _safe_decimal(r.get("biannualChange")),
        "ytd_change": _safe_decimal(r.get("ytdChange")),
        "week_low": _safe_decimal(r.get("weekLow")),
        "week_high": _safe_decimal(r.get("weekHigh")),
        "week_change": _safe_decimal(r.get("weekChange")),
        "week_volume": _safe_int(r.get("weekVolume")),
        "week_avg_volume": _safe_int(r.get("weekAvgVolume")),
        "week_avg_change": _safe_decimal(r.get("weekAvgChange")),
        "week_yield": _safe_decimal(r.get("weekYield")),
        "month_low": _safe_decimal(r.get("monthLow")),
        "month_high": _safe_decimal(r.get("monthHigh")),
        "month_change": _safe_decimal(r.get("monthChange")),
        "month_volume": _safe_int(r.get("monthVolume")),
        "month_avg_volume": _safe_int(r.get("monthAvgVolume")),
        "month_avg_change": _safe_decimal(r.get("monthAvgChange")),
        "month_yield": _safe_decimal(r.get("monthYield")),
        "year_low": _safe_decimal(r.get("yearLow")),
        "year_high": _safe_decimal(r.get("yearHigh")),
        "year_change": _safe_decimal(r.get("yearChange")),
        "year_volume": _safe_int(r.get("yearVolume")),
        "year_avg_volume": _safe_int(r.get("yearAvgVolume")),
        "year_avg_change": _safe_decimal(r.get("yearAvgChange")),
        "year_yield": _safe_decimal(r.get("yearYield")),
        "ma5": _safe_decimal(r.get("mA5")),
        "ma10": _safe_decimal(r.get("mA10")),
        "ma20": _safe_decimal(r.get("mA20")),
        "ma50": _safe_decimal(r.get("mA50")),
        "ma100": _safe_decimal(r.get("mA100")),
        "ma200": _safe_decimal(r.get("mA200")),
        "wma5": _safe_decimal(r.get("wMA5")),
        "wma10": _safe_decimal(r.get("wMA10")),
        "wma20": _safe_decimal(r.get("wMA20")),
        "wma50": _safe_decimal(r.get("wMA50")),
        "wma100": _safe_decimal(r.get("wMA100")),
        "wma200": _safe_decimal(r.get("wMA200")),
        "ema5": _safe_decimal(r.get("eMA5")),
        "ema10": _safe_decimal(r.get("eMA10")),
        "ema20": _safe_decimal(r.get("eMA20")),
        "ema50": _safe_decimal(r.get("eMA50")),
        "ema100": _safe_decimal(r.get("eMA100")),
        "ema200": _safe_decimal(r.get("eMA200")),
        "macd": _safe_decimal(r.get("macd")),
        "sto9_fast": _safe_decimal(r.get("sto9Fast")),
        "sto9_slow": _safe_decimal(r.get("sto9Slow")),
        "sto9_full": _safe_decimal(r.get("sto9Full")),
        "sto14_fast": _safe_decimal(r.get("sto14Fast")),
        "sto14_slow": _safe_decimal(r.get("sto14Slow")),
        "sto14_full": _safe_decimal(r.get("sto14Full")),
        "rsi9": _safe_decimal(r.get("rsi9")),
        "rsi14": _safe_decimal(r.get("rsi14")),
        "wpr14": _safe_decimal(r.get("wpr14")),
        "mtm14": _safe_decimal(r.get("mtm14")),
        "roc14": _safe_decimal(r.get("roc14")),
        "upper_bb20": _safe_decimal(r.get("upperBB20")),
        "lower_bb20": _safe_decimal(r.get("lowerBB20")),
        "bandwidth_bb20": _safe_decimal(r.get("bandwidthBB20")),
        "obv20": _safe_int(r.get("oBV20")),
        "ad20": _safe_decimal(r.get("aD20")),
        "aroon20": _safe_decimal(r.get("aroon20")),
        "dmi_positive": _safe_decimal(r.get("dmiPositive")),
        "dmi_negative": _safe_decimal(r.get("dmiNegative")),
        "dmi_average": _safe_decimal(r.get("dmiAverage")),
        "atr": _safe_decimal(r.get("atr")),
        "cci": _safe_decimal(r.get("cci")),
        "sar": _safe_decimal(r.get("sar")),
        "volatility": _safe_decimal(r.get("volatility")),
        "liquidity": _safe_decimal(r.get("liquidity")),
    }


def _transform_quote(r: dict, interval: str) -> dict:
    return {
        "exchange_code": r.get("exchangeCode", ""),
        "symbol_code": r.get("symbolCode", ""),
        "interval_code": r.get("interval") or interval,
        "as_of_date": _safe_date(r.get("dateStamp")) or str(date.today()),
        "name": r.get("name"),
        "open_price": _safe_decimal(r.get("open")),
        "high_price": _safe_decimal(r.get("high")),
        "low_price": _safe_decimal(r.get("low")),
        "close_price": _safe_decimal(r.get("close")),
        "adjusted_close": _safe_decimal(r.get("adjustedClose")),
        "volume": _safe_int(r.get("volume")) or 0,
        "open_interest": _safe_int(r.get("openInterest")),
        "bid_price": _safe_decimal(r.get("bid")),
        "ask_price": _safe_decimal(r.get("ask")),
        "previous_price": _safe_decimal(r.get("previous")),
        "change_amount": _safe_decimal(r.get("change")),
        "currency": (r.get("currency") or "")[:3] or None,
    }


# ---------------------------------------------------------------------------
# Public loader functions
# ---------------------------------------------------------------------------

def load_symbols(
    client: EODDataClient,
    conn: psycopg2.extensions.connection,
    exchange_code: str,
) -> list[str]:
    """
    Fetch /Symbol/List/{exchangeCode} and upsert into public.symbol.
    Returns the list of symbol codes loaded.
    """
    raw = client.list_symbols(exchange_code)
    if not raw:
        logger.info("[%s] No symbols returned", exchange_code)
        return []

    rows = [_transform_symbol(r, exchange_code) for r in raw if r.get("code")]
    upsert_rows(
        conn,
        table="symbol",
        rows=rows,
        conflict_columns=["exchange_code", "symbol_code"],
        update_columns=[
            c for c in rows[0].keys() if c not in ("exchange_code", "symbol_code")
        ] if rows else [],
    )
    logger.info("[%s] Symbols: upserted %d rows", exchange_code, len(rows))
    return [r["symbol_code"] for r in rows]


def load_profiles(
    client: EODDataClient,
    conn: psycopg2.extensions.connection,
    exchange_code: str,
) -> int:
    """Fetch /Profile/List/{exchangeCode} and upsert into public.symbol_profile."""
    raw = client.list_profiles(exchange_code)
    if not raw:
        logger.info("[%s] No profiles returned", exchange_code)
        return 0

    rows = [
        _transform_profile(r)
        for r in raw
        if r.get("exchangeCode") and r.get("symbolCode") and r.get("name")
    ]
    if not rows:
        return 0

    upsert_rows(
        conn,
        table="symbol_profile",
        rows=rows,
        conflict_columns=["exchange_code", "symbol_code"],
        update_columns=[c for c in rows[0].keys() if c not in ("exchange_code", "symbol_code")],
    )
    logger.info("[%s] Profiles: upserted %d rows", exchange_code, len(rows))
    return len(rows)


def load_fundamentals(
    client: EODDataClient,
    conn: psycopg2.extensions.connection,
    exchange_code: str,
) -> int:
    """Fetch /Fundamental/List/{exchangeCode} and upsert into public.symbol_fundamental."""
    raw = client.list_fundamentals(exchange_code)
    if not raw:
        logger.info("[%s] No fundamentals returned", exchange_code)
        return 0

    rows = [
        _transform_fundamental(r)
        for r in raw
        if r.get("exchangeCode") and r.get("symbolCode")
    ]
    if not rows:
        return 0

    upsert_rows(
        conn,
        table="symbol_fundamental",
        rows=rows,
        conflict_columns=["exchange_code", "symbol_code"],
        update_columns=[c for c in rows[0].keys() if c not in ("exchange_code", "symbol_code")],
    )
    logger.info("[%s] Fundamentals: upserted %d rows", exchange_code, len(rows))
    return len(rows)


def load_technicals(
    client: EODDataClient,
    conn: psycopg2.extensions.connection,
    exchange_code: str,
) -> int:
    """Fetch /Technical/List/{exchangeCode} and upsert into public.symbol_technical."""
    raw = client.list_technicals(exchange_code)
    if not raw:
        logger.info("[%s] No technicals returned", exchange_code)
        return 0

    rows = [
        _transform_technical(r)
        for r in raw
        if r.get("exchangeCode") and r.get("symbolCode")
    ]
    if not rows:
        return 0

    upsert_rows(
        conn,
        table="symbol_technical",
        rows=rows,
        conflict_columns=["exchange_code", "symbol_code", "as_of_date"],
        update_columns=[
            c for c in rows[0].keys()
            if c not in ("exchange_code", "symbol_code", "as_of_date")
        ],
    )
    logger.info("[%s] Technicals: upserted %d rows", exchange_code, len(rows))
    return len(rows)


def load_quotes_by_exchange(
    client: EODDataClient,
    conn: psycopg2.extensions.connection,
    exchange_code: str,
    interval: str = "d",
    date_stamp: str | None = None,
) -> int:
    """
    Fetch /Quote/List/{exchangeCode} and upsert all returned quotes into
    public.symbol_quote.

    Parameters
    ----------
    interval   : Fallback interval code stored when the API field is absent.
    date_stamp : Optional date in yyyy-MM-dd format.  Defaults to today.
    """
    raw = client.list_quotes_by_exchange(exchange_code, date_stamp=date_stamp)
    if not raw:
        logger.info("[%s] No quotes returned", exchange_code)
        return 0

    rows = [_transform_quote(r, interval) for r in raw]
    # Drop rows missing any part of the composite PK
    rows = [
        r for r in rows
        if r["exchange_code"] and r["symbol_code"] and r["interval_code"] and r["as_of_date"]
    ]
    if not rows:
        return 0

    upsert_rows(
        conn,
        table="symbol_quote",
        rows=rows,
        conflict_columns=["exchange_code", "symbol_code", "interval_code", "as_of_date"],
        update_columns=[
            c for c in rows[0].keys()
            if c not in ("exchange_code", "symbol_code", "interval_code", "as_of_date")
        ],
    )
    logger.info("[%s] Quotes: upserted %d rows", exchange_code, len(rows))
    return len(rows)
