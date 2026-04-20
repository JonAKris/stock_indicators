"""
sync.py – high-level orchestration for a full ETL run.

Can be imported and called programmatically, or run directly as a module.
All state is logged; failures on one exchange don't abort others.
"""

from __future__ import annotations

import logging
from typing import Callable

from api_client import EODDataClient
from config import Config
from database import get_conn, init_pool
from loaders.exchange_loader import load_exchanges
from loaders.metadata_loader import load_countries, load_currencies
from loaders.symbol_loader import (
    load_fundamentals,
    load_profiles,
    load_quotes_by_exchange,
    load_symbols,
    load_technicals,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step registry – each step is (name, callable(client, conn, *args))
# ---------------------------------------------------------------------------

def run_full_sync(config: Config, steps: list[str] | None = None) -> None:
    """
    Execute a complete ETL pipeline:

      1. Metadata  – countries, currencies  (no auth)
      2. Exchanges – load exchange list
      3. Per exchange:
           a. Symbols (+ current price snapshot)
           b. Profiles
           c. Fundamentals
           d. Technicals
           e. Quotes (all symbols, single call per exchange)

    Parameters
    ----------
    steps : restrict which top-level steps to run.
            Options: 'metadata', 'exchanges', 'symbols', 'profiles',
                     'fundamentals', 'technicals', 'quotes'
            None  → run everything.
    """
    allowed = set(steps) if steps else None

    def _run(step_name: str, fn: Callable, *args, **kwargs):
        if allowed and step_name not in allowed:
            logger.info("Skipping step: %s", step_name)
            return None
        logger.info("=== Starting step: %s ===", step_name)
        result = fn(*args, **kwargs)
        logger.info("=== Finished step: %s ===", step_name)
        return result

    client = EODDataClient(config)
    init_pool(config, minconn=2, maxconn=5)

    # ------------------------------------------------------------------
    # Step 1: Metadata
    # ------------------------------------------------------------------
    with get_conn() as conn:
        _run("metadata", _load_metadata, client, conn)

    # ------------------------------------------------------------------
    # Step 2: Exchanges
    # ------------------------------------------------------------------
    with get_conn() as conn:
        exchange_codes = _run("exchanges", load_exchanges, client, conn, config.EXCHANGES or None)

    if not exchange_codes:
        logger.warning("No exchanges loaded – aborting symbol sync")
        return

    # ------------------------------------------------------------------
    # Steps 3-7: Per-exchange symbol data
    # ------------------------------------------------------------------
    for exc_code in exchange_codes:
        logger.info("--- Processing exchange: %s ---", exc_code)
        try:
            _sync_exchange(client, config, exc_code, allowed)
        except Exception as err:
            logger.error("Exchange %s failed: %s", exc_code, err, exc_info=True)


def _load_metadata(client: EODDataClient, conn) -> None:
    load_countries(client, conn)
    load_currencies(client, conn)


def _sync_exchange(
    client: EODDataClient,
    config: Config,
    exchange_code: str,
    allowed: set[str] | None,
) -> None:
    def _step(name, fn, *args, **kwargs):
        if allowed and name not in allowed:
            return None
        return fn(*args, **kwargs)

    # Symbols (snapshot)
    with get_conn() as conn:
        _step("symbols", load_symbols, client, conn, exchange_code)

    # Profiles
    with get_conn() as conn:
        _step("profiles", load_profiles, client, conn, exchange_code)

    # Fundamentals
    with get_conn() as conn:
        _step("fundamentals", load_fundamentals, client, conn, exchange_code)

    # Technicals
    with get_conn() as conn:
        _step("technicals", load_technicals, client, conn, exchange_code)

    # Quotes – single call returns all symbols for the exchange
    with get_conn() as conn:
        _step("quotes", load_quotes_by_exchange, client, conn, exchange_code, config.QUOTE_INTERVAL)
