"""
normalize_close_prices.py

Computes min-max normalized close prices for each (exchange_code, symbol_code,
interval_code) group in public.symbol_quote and writes the result to the
normalized_close column.

Normalization formula (per group):
    normalized_close = (close_price - min_close) / (max_close - min_close)

When min == max for a group (a flat series, or a single row), normalized_close
is set to NULL to avoid a divide-by-zero and to flag the degenerate case.

Run the accompanying add_normalized_close.sql once before running this script.

Connection settings come from environment variables:
    PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
or pass them via --dsn "postgresql://user:pass@host:port/db".
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from contextlib import contextmanager

import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BATCH_SIZE = 5000


# ---------- SQL ----------

# Pull every row's identity + close, plus the per-group min/max computed by
# window functions. Doing min/max in SQL avoids a second round-trip and keeps
# memory bounded on the client even for very large tables (we still stream
# via a server-side cursor).
SELECT_WITH_BOUNDS = """
    SELECT
        exchange_code,
        symbol_code,
        interval_code,
        as_of_date,
        close_price,
        MIN(close_price) OVER w AS min_close,
        MAX(close_price) OVER w AS max_close
    FROM public.symbol_quote
    WHERE close_price IS NOT NULL
    WINDOW w AS (PARTITION BY exchange_code, symbol_code, interval_code)
"""

# Use a temp table + UPDATE ... FROM join. This is dramatically faster than
# row-by-row UPDATEs over a 4-column composite primary key.
CREATE_TEMP = """
    CREATE TEMP TABLE _norm_close (
        exchange_code text,
        symbol_code   text,
        interval_code text,
        as_of_date    date,
        normalized_close numeric(12, 8)
    ) ON COMMIT DROP
"""

UPDATE_FROM_TEMP = """
    UPDATE public.symbol_quote AS q
       SET normalized_close = n.normalized_close
      FROM _norm_close AS n
     WHERE q.exchange_code = n.exchange_code
       AND q.symbol_code   = n.symbol_code
       AND q.interval_code = n.interval_code
       AND q.as_of_date    = n.as_of_date
"""


# ---------- Helpers ----------

def normalize(close, lo, hi):
    """Min-max normalize. Returns None if the group is degenerate."""
    if lo is None or hi is None or close is None:
        return None
    if hi == lo:
        return None
    return float((close - lo) / (hi - lo))


@contextmanager
def server_side_cursor(conn, name="norm_cur", itersize=10_000):
    """Named (server-side) cursor so we don't pull the whole table into RAM."""
    cur = conn.cursor(name=name)
    cur.itersize = itersize
    try:
        yield cur
    finally:
        cur.close()


def compute_and_load(conn, batch_size: int) -> int:
    """
    Stream rows from symbol_quote, compute normalized close, and bulk-load
    into a temp table. Returns the number of rows staged.
    """
    total = 0
    with conn.cursor() as setup:
        setup.execute(CREATE_TEMP)

    with server_side_cursor(conn) as src, conn.cursor() as dst:
        src.execute(SELECT_WITH_BOUNDS)
        batch = []
        for exch, sym, ivl, dt, close, lo, hi in src:
            batch.append((exch, sym, ivl, dt, normalize(close, lo, hi)))
            if len(batch) >= batch_size:
                execute_values(
                    dst,
                    "INSERT INTO _norm_close VALUES %s",
                    batch,
                    page_size=batch_size,
                )
                total += len(batch)
                batch.clear()
                logging.info("Staged %s rows...", f"{total:,}")
        if batch:
            execute_values(
                dst,
                "INSERT INTO _norm_close VALUES %s",
                batch,
                page_size=len(batch),
            )
            total += len(batch)

    return total


def apply_update(conn) -> int:
    """Run the UPDATE ... FROM and return the number of rows changed."""
    with conn.cursor() as cur:
        cur.execute(UPDATE_FROM_TEMP)
        return cur.rowcount


# ---------- Entry point ----------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dsn", help="Postgres DSN (overrides DB_* env vars).")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--dry-run", action="store_true",
                   help="Compute and stage but roll back instead of committing.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def make_conn(dsn: str | None):
    if dsn:
        return psycopg2.connect(dsn)
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
    )


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        conn = make_conn(args.dsn)
    except psycopg2.Error as e:
        logging.error("Could not connect: %s", e)
        return 2

    try:
        with conn:  # transactional block
            logging.info("Computing normalized close prices...")
            staged = compute_and_load(conn, args.batch_size)
            logging.info("Staged %s rows. Applying update...", f"{staged:,}")
            updated = apply_update(conn)
            logging.info("Updated %s rows in public.symbol_quote.", f"{updated:,}")

            if args.dry_run:
                logging.warning("--dry-run set, rolling back.")
                conn.rollback()
                return 0
        logging.info("Committed.")
        return 0
    except psycopg2.Error as e:
        logging.error("Database error: %s", e)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
