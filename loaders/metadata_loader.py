"""
Metadata loader – populates the countries and currencies reference tables.

These endpoints do NOT require an API key.
"""

from __future__ import annotations

import logging

import psycopg2

from api_client import EODDataClient
from database import upsert_rows

logger = logging.getLogger(__name__)


def load_countries(client: EODDataClient, conn: psycopg2.extensions.connection) -> int:
    """Fetch /Country/List and upsert into public.countries."""
    raw = client.list_countries()
    if not raw:
        logger.warning("No countries returned from API")
        return 0

    rows = [
        {"country_code": r["code"], "country_name": r["name"]}
        for r in raw
        if r.get("code") and r.get("name")
    ]

    affected = upsert_rows(
        conn,
        table="countries",
        rows=rows,
        conflict_columns=["country_code"],
        update_columns=["country_name"],
    )
    logger.info("Countries: upserted %d rows", len(rows))
    return affected


def load_currencies(client: EODDataClient, conn: psycopg2.extensions.connection) -> int:
    """Fetch /Currency/List and upsert into public.currencies."""
    raw = client.list_currencies()
    if not raw:
        logger.warning("No currencies returned from API")
        return 0

    rows = [
        {"currency_code": r["code"], "currency_name": r["name"]}
        for r in raw
        if r.get("code") and r.get("name")
    ]

    affected = upsert_rows(
        conn,
        table="currencies",
        rows=rows,
        conflict_columns=["currency_code"],
        update_columns=["currency_name"],
    )
    logger.info("Currencies: upserted %d rows", len(rows))
    return affected
