"""
Database access layer for the stock charting app.
All SQL is parameterized and scoped to the public schema described in schema.sql.
"""

import os
from contextlib import contextmanager
from typing import Optional

import pandas as pd
import psycopg2
import psycopg2.extras
from psycopg2 import pool


class Database:
    """Thin wrapper around a psycopg2 connection pool."""

    def __init__(self):
        self._pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=int(os.getenv("DB_MAX_CONN", "5")),
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.getenv("DB_NAME", "stockman"),
            user=os.getenv("DB_USER", "stockman"),
            password=os.getenv("DB_PASS", ""),
        )

    # ---- connection helpers ------------------------------------------------
    @contextmanager
    def _cursor(self, dict_cursor: bool = True):
        conn = self._pool.getconn()
        try:
            cursor_factory = psycopg2.extras.RealDictCursor if dict_cursor else None
            with conn.cursor(cursor_factory=cursor_factory) as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    # ---- reference data ----------------------------------------------------
    def list_exchanges(self) -> list[dict]:
        """Return exchanges. Falls back to DISTINCT from the symbol table if
        the exchanges table is empty (useful during development)."""
        with self._cursor() as cur:
            cur.execute("""
                SELECT exchange_code, exchange_name
                FROM   public.exchanges
                ORDER  BY exchange_code
            """)
            rows = cur.fetchall()

            if not rows:
                cur.execute("""
                    SELECT DISTINCT exchange_code,
                           exchange_code AS exchange_name
                    FROM   public.symbol
                    ORDER  BY exchange_code
                """)
                rows = cur.fetchall()

            return [dict(r) for r in rows]

    def list_symbols(self, exchange_code: str, limit: int = 2000) -> list[dict]:
        with self._cursor() as cur:
            cur.execute("""
                SELECT symbol_code, name
                FROM   public.symbol
                WHERE  exchange_code = %s
                ORDER  BY symbol_code
                LIMIT  %s
            """, (exchange_code, limit))
            return [dict(r) for r in cur.fetchall()]

    # ---- snapshots ---------------------------------------------------------
    def get_symbol_snapshot(self, exchange_code: str, symbol_code: str) -> Optional[dict]:
        with self._cursor() as cur:
            cur.execute("""
                SELECT exchange_code, symbol_code, name, type, currency,
                       as_of_date, open_price, high_price, low_price, close_price,
                       volume, previous_price, change_amount, bid_price, ask_price
                FROM   public.symbol
                WHERE  exchange_code = %s AND symbol_code = %s
            """, (exchange_code, symbol_code))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_profile(self, exchange_code: str, symbol_code: str) -> Optional[dict]:
        with self._cursor() as cur:
            cur.execute("""
                SELECT *
                FROM   public.symbol_profile
                WHERE  exchange_code = %s AND symbol_code = %s
            """, (exchange_code, symbol_code))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_fundamentals(self, exchange_code: str, symbol_code: str) -> Optional[dict]:
        with self._cursor() as cur:
            cur.execute("""
                SELECT *
                FROM   public.symbol_fundamental
                WHERE  exchange_code = %s AND symbol_code = %s
            """, (exchange_code, symbol_code))
            row = cur.fetchone()
            return dict(row) if row else None

    # ---- time series -------------------------------------------------------
    def get_quotes(
        self,
        exchange_code: str,
        symbol_code: str,
        interval_code: str = "d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Return an OHLCV DataFrame ordered by date ascending."""
        sql = """
            SELECT as_of_date, open_price, high_price, low_price, close_price,
                   adjusted_close, volume, previous_price, change_amount,
                   bid_price, ask_price
            FROM   public.symbol_quote
            WHERE  exchange_code = %s
              AND  symbol_code   = %s
              AND  interval_code = %s
        """
        params: list = [exchange_code, symbol_code, interval_code]
        if start_date:
            sql += " AND as_of_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND as_of_date <= %s"
            params.append(end_date)
        sql += " ORDER BY as_of_date ASC"

        with self._cursor(dict_cursor=False) as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()

        df = pd.DataFrame(rows, columns=cols)
        # Convert numerics (psycopg2 returns Decimal) to float for plotting.
        numeric_cols = [
            "open_price", "high_price", "low_price", "close_price",
            "adjusted_close", "previous_price", "change_amount",
            "bid_price", "ask_price",
        ]
        for c in numeric_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        if "as_of_date" in df.columns:
            df["as_of_date"] = pd.to_datetime(df["as_of_date"])
        return df

    def get_technicals(
        self,
        exchange_code: str,
        symbol_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        sql = """
            SELECT *
            FROM   public.symbol_technical
            WHERE  exchange_code = %s
              AND  symbol_code   = %s
        """
        params: list = [exchange_code, symbol_code]
        if start_date:
            sql += " AND as_of_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND as_of_date <= %s"
            params.append(end_date)
        sql += " ORDER BY as_of_date ASC"

        with self._cursor(dict_cursor=False) as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()

        df = pd.DataFrame(rows, columns=cols)
        if df.empty:
            return df

        # Cast Decimal columns to float so plotly handles them cleanly.
        for c in df.columns:
            if c in ("exchange_code", "symbol_code", "as_of_date"):
                continue
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["as_of_date"] = pd.to_datetime(df["as_of_date"])
        return df
