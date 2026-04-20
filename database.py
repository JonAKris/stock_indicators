"""
Database connection pool and helper utilities for the Stock Indicators ETL.
Uses psycopg2 with a SimpleConnectionPool for modest concurrency.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator, Sequence

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from config import Config

logger = logging.getLogger(__name__)

_pool: ThreadedConnectionPool | None = None

# ---------------------------------------------------------------------------
# Column-type cache – maps "schema.table" → {column_name: cast_suffix}
# Populated lazily on first upsert; valid for the process lifetime.
# ---------------------------------------------------------------------------
_type_cache: dict[str, dict[str, str]] = {}

# Map PostgreSQL udt_name → explicit cast suffix to embed in the VALUES template.
# Only non-text types need a cast; text/varchar/bpchar are omitted (empty string).
_UDT_CAST: dict[str, str] = {
    "date":        "::date",
    "timestamp":   "::timestamp",
    "timestamptz": "::timestamptz",
    "time":        "::time",
    "timetz":      "::timetz",
    "int2":        "::smallint",
    "int4":        "::integer",
    "int8":        "::bigint",
    "float4":      "::real",
    "float8":      "::double precision",
    "numeric":     "::numeric",
    "bool":        "::boolean",
    "uuid":        "::uuid",
    "json":        "::json",
    "jsonb":       "::jsonb",
}


def _column_casts(
    conn: psycopg2.extensions.connection,
    table: str,
    schema: str = "public",
) -> dict[str, str]:
    """
    Return {column_name: cast_suffix} for every column in *schema.table*.
    Columns whose type needs no explicit cast have an empty-string suffix.
    Results are cached for the process lifetime.
    """
    cache_key = f"{schema}.{table}"
    if cache_key in _type_cache:
        return _type_cache[cache_key]

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, udt_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        rows = cur.fetchall()

    result = {col: _UDT_CAST.get(udt, "") for col, udt in rows}
    _type_cache[cache_key] = result
    logger.debug("_column_casts: %s → %s", cache_key, result)
    return result


def init_pool(config: Config, minconn: int = 1, maxconn: int = 10) -> None:
    """Initialise the global connection pool. Call once at startup."""
    global _pool
    _pool = ThreadedConnectionPool(minconn, maxconn, dsn=config.dsn)
    logger.info("Database connection pool initialised (min=%d, max=%d)", minconn, maxconn)


def close_pool() -> None:
    """Close all connections in the pool."""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None


@contextmanager
def get_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    """Yield a connection from the pool, returning it when done."""
    if _pool is None:
        raise RuntimeError("Connection pool has not been initialised. Call init_pool() first.")
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


@contextmanager
def get_cursor(
    conn: psycopg2.extensions.connection,
) -> Generator[psycopg2.extensions.cursor, None, None]:
    """Yield a DictCursor from the given connection."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        yield cur


def execute_many(
    conn: psycopg2.extensions.connection,
    sql: str,
    rows: Sequence[dict[str, Any]],
    page_size: int = 500,
) -> int:
    """
    Execute an INSERT … ON CONFLICT … statement for each row dict in *rows*.
    Uses execute_values for efficient batch inserts.
    Returns the total number of rows affected.
    """
    if not rows:
        return 0

    affected = 0
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, template=None, page_size=page_size)
        affected = cur.rowcount
    return affected


def upsert_rows(
    conn: psycopg2.extensions.connection,
    table: str,
    rows: list[dict[str, Any]],
    conflict_columns: list[str],
    update_columns: list[str] | None = None,
    schema: str = "public",
) -> int:
    """
    Generic upsert helper using a SQL MERGE statement (requires PostgreSQL 15+).

    MERGE INTO <table> AS t
    USING (VALUES %s) AS s(<cols>)
    ON <join condition>
    WHEN MATCHED THEN UPDATE SET ...
    WHEN NOT MATCHED THEN INSERT ...

    If update_columns is None all non-conflict columns are updated.
    If update_columns is an empty list only inserts are performed (no update on match).
    Duplicate rows (same conflict key) are deduplicated before executing so a
    single MERGE batch never targets the same target row twice.
    Returns the total number of rows merged (inserted + updated).
    """
    if not rows:
        return 0

    # Deduplicate: keep the last occurrence for each unique conflict key.
    # This handles APIs that return the same entity more than once in one response.
    seen: dict[tuple, dict] = {}
    for row in rows:
        key = tuple(row[c] for c in conflict_columns)
        seen[key] = row
    rows = list(seen.values())

    all_cols = list(rows[0].keys())
    if update_columns is None:
        update_columns = [c for c in all_cols if c not in conflict_columns]

    # Column list used in both USING alias and INSERT target
    col_list = ", ".join(f'"{c}"' for c in all_cols)

    # JOIN predicate linking the target table to the source VALUES
    join_cond = " AND ".join(f't."{c}" = s."{c}"' for c in conflict_columns)

    # Build WHEN clauses
    merge_clauses: list[str] = []

    if update_columns:
        update_set = ", ".join(f'"{c}" = s."{c}"' for c in update_columns)
        merge_clauses.append(f"WHEN MATCHED THEN UPDATE SET {update_set}")
    # else: no WHEN MATCHED clause → matched rows are left untouched

    insert_cols = col_list
    insert_vals = ", ".join(f's."{c}"' for c in all_cols)
    merge_clauses.append(
        f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})"
    )

    sql = (
        f'MERGE INTO {schema}."{table}" AS t '
        f"USING (VALUES %s) AS s({col_list}) "
        f"ON {join_cond} "
        + " ".join(merge_clauses)
    )

    # Build a per-column VALUES template that includes explicit PG type casts.
    # This is necessary because MERGE's USING (VALUES ...) source infers every
    # column as 'text' by default; without casts PostgreSQL raises
    # DatatypeMismatch when the target column is date, numeric, bigint, etc.
    casts = _column_casts(conn, table, schema)
    template = (
        "("
        + ", ".join(f"%({c})s{casts.get(c, '')}" for c in all_cols)
        + ")"
    )

    affected = 0
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, template=template, page_size=500)
        affected = cur.rowcount

    logger.debug("upsert_rows: table=%s rows=%d affected=%d", table, len(rows), affected)
    return affected
