"""
Exchange loader – populates the exchanges table from /Exchange/List.
"""

from __future__ import annotations

import logging

import psycopg2

from api_client import EODDataClient
from database import upsert_rows

logger = logging.getLogger(__name__)


def load_exchanges(
    client: EODDataClient,
    conn: psycopg2.extensions.connection,
    exchange_filter: list[str] | None = None,
) -> list[str]:
    """
    Fetch all exchanges from the API and upsert into public.exchanges.

    Parameters
    ----------
    exchange_filter : list of exchange codes to restrict to, or None for all.

    Returns
    -------
    List of exchange codes that were loaded (used by downstream loaders).
    """
    raw = client.list_exchanges()
    if not raw:
        logger.warning("No exchanges returned from API")
        return []

    if exchange_filter:
        upper_filter = {e.upper() for e in exchange_filter}
        raw = [r for r in raw if r.get("code", "").upper() in upper_filter]
        logger.info("Filtered to %d exchanges: %s", len(raw), sorted(upper_filter))

    rows = []
    for r in raw:
        code = r.get("code")
        name = r.get("name")
        if not code or not name:
            continue
        rows.append(
            {
                "exchange_code": code,
                "exchange_name": name,
                "country_code": r.get("country") or None,
                "currency_code": r.get("currency") or None,
            }
        )

    upsert_rows(
        conn,
        table="exchanges",
        rows=rows,
        conflict_columns=["exchange_code"],
        update_columns=["exchange_name", "country_code", "currency_code"],
    )
    loaded_codes = [r["exchange_code"] for r in rows]
    logger.info("Exchanges: upserted %d rows", len(rows))
    return loaded_codes
