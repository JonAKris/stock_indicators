"""
detect_seasonality.py

Tests each symbol's normalized close-price series in public.symbol_quote for
seasonality at the natural calendar periods for its interval_code, and
optionally writes the results to:

  * public.symbol_technical            (--write-db)
  * public.symbol_seasonality_history  (--write-history)

Per-symbol analysis runs in a *process* pool. STL with robust=True does NOT
reliably release the GIL across statsmodels versions, so threads stayed pinned
to one core in practice. Processes sidestep the GIL entirely. The per-task
work (loading a series, fitting STL, running three other tests -- roughly
~1 second per symbol on a modern core) is large enough that pickling overhead
between processes is negligible.

Each worker:
  - opens its own psycopg2 connection (process-local, lazy)
  - pins BLAS/OpenMP to 1 thread to prevent N*N oversubscription
  - loads its assigned symbol's series, analyzes, returns the result

Usage:
    python detect_seasonality.py                              # CSV only
    python detect_seasonality.py --workers 16                 # 16 worker processes
    python detect_seasonality.py --write-db --write-history   # write to both tables
    python detect_seasonality.py --interval w
    python detect_seasonality.py --symbol NASDAQ:AAPL
    python detect_seasonality.py --min-obs 500 --out results.csv

Run the matching SQL files once before --write-db / --write-history:
    psql -f add_seasonality_columns.sql
    psql -f create_seasonality_history.sql

Connection: DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASS, or --dsn.
"""

from __future__ import annotations

import argparse
import csv
import logging
import multiprocessing as mp
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime, date, timezone
from typing import Iterator
from dotenv import load_dotenv

load_dotenv()

# ---- BLAS thread limiting: must happen BEFORE NumPy is imported ----
# Without this, each worker process spawns up to (cores) BLAS threads, so
# `--workers 16` on a 16-core box launches 256 native threads, all fighting
# for the same cores. Setting these env vars before numpy loads is the
# canonical fix.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from scipy import signal, stats
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.seasonal import STL


# ---------- Configuration: candidate period per interval ----------

PERIOD_BY_INTERVAL = {
    "d": (252, "annual"),
    "w": (52,  "annual"),
    "m": (12,  "annual"),
    "q": (4,   "annual"),
    "y": (None, None),
    "h": (None, None),
    "1": (None, None),
    "5": (None, None),
    "10": (None, None),
    "15": (None, None),
    "30": (None, None),
}

BUCKET_BY_INTERVAL = {
    "d": ("month", lambda d: d.month),
    "w": ("month", lambda d: d.month),
    "m": ("month", lambda d: d.month),
    "q": ("quarter", lambda d: d.quarter),
}


# ---------- Result container ----------

@dataclass
class SeasonalityResult:
    exchange_code: str
    symbol_code: str
    interval_code: str
    latest_as_of_date: date | None
    n_obs: int
    period: int | None
    period_label: str | None

    stl_strength: float | None
    ljungbox_pvalue: float | None
    dom_period_bars: float | None
    dom_period_ratio: float | None
    kw_pvalue: float | None
    kw_bucket: str | None

    verdict: str
    notes: str = ""


# ---------- DB access ----------

LOAD_SQL = """
    SELECT as_of_date, normalized_close
      FROM public.symbol_quote
     WHERE exchange_code = %s
       AND symbol_code   = %s
       AND interval_code = %s
       AND normalized_close IS NOT NULL
     ORDER BY as_of_date
"""

LIST_SQL = """
    SELECT exchange_code, symbol_code, interval_code, COUNT(*) AS n
      FROM public.symbol_quote
     WHERE interval_code = %s
       AND normalized_close IS NOT NULL
     GROUP BY exchange_code, symbol_code, interval_code
     HAVING COUNT(*) >= %s
     ORDER BY exchange_code, symbol_code
"""


def load_series(conn, exch: str, sym: str, ivl: str) -> pd.Series:
    with conn.cursor() as cur:
        cur.execute(LOAD_SQL, (exch, sym, ivl))
        rows = cur.fetchall()
    if not rows:
        return pd.Series(dtype=float)
    idx = pd.DatetimeIndex([r[0] for r in rows])
    vals = np.array([float(r[1]) for r in rows], dtype=float)
    return pd.Series(vals, index=idx, name="normalized_close")


def list_symbols(conn, ivl: str, min_obs: int) -> list[tuple[str, str, str, int]]:
    with conn.cursor() as cur:
        cur.execute(LIST_SQL, (ivl, min_obs))
        return cur.fetchall()


# ---------- Individual tests ----------

def stl_strength(returns: np.ndarray, period: int) -> float | None:
    if len(returns) < 2 * period + 1:
        return None
    try:
        res = STL(returns, period=period, robust=True).fit()
    except Exception:
        return None
    var_resid = np.nanvar(res.resid)
    var_resid_plus_seas = np.nanvar(res.resid + res.seasonal)
    if var_resid_plus_seas == 0:
        return None
    return float(max(0.0, 1.0 - var_resid / var_resid_plus_seas))


def ljungbox_seasonal(returns: np.ndarray, period: int) -> float | None:
    lags = [lag for lag in (period, 2 * period, 3 * period) if lag < len(returns) // 2]
    if not lags:
        return None
    try:
        lb = acorr_ljungbox(returns, lags=lags, return_df=True)
    except Exception:
        return None
    return float(lb["lb_pvalue"].min())


def periodogram_peak(returns: np.ndarray, target_period: int) -> tuple[float | None, float | None]:
    if len(returns) < 4:
        return None, None
    freqs, power = signal.periodogram(returns, detrend="constant", scaling="spectrum")
    freqs, power = freqs[1:], power[1:]
    if len(power) == 0 or np.all(power == 0):
        return None, None
    peak_idx = int(np.argmax(power))
    peak_freq = freqs[peak_idx]
    if peak_freq == 0:
        return None, None
    dom_period = 1.0 / peak_freq
    median_power = float(np.median(power))
    if median_power == 0:
        return float(dom_period), None
    return float(dom_period), float(power[peak_idx] / median_power)


def kruskal_by_bucket(returns: pd.Series, bucket_fn) -> float | None:
    buckets = returns.index.to_series().apply(bucket_fn)
    groups = [returns.values[buckets.values == b] for b in sorted(buckets.unique())]
    groups = [g for g in groups if len(g) >= 2]
    if len(groups) < 2:
        return None
    try:
        _, p = stats.kruskal(*groups)
    except Exception:
        return None
    return float(p)


# ---------- Combining tests into a verdict ----------

def make_verdict(r: SeasonalityResult) -> str:
    if r.period is None:
        return "insufficient_data"
    if r.stl_strength is None and r.ljungbox_pvalue is None and r.kw_pvalue is None:
        return "insufficient_data"

    votes_for = 0
    votes_against = 0

    if r.stl_strength is not None:
        if r.stl_strength >= 0.64:
            votes_for += 2
        elif r.stl_strength >= 0.30:
            votes_for += 1
        else:
            votes_against += 1

    if r.ljungbox_pvalue is not None:
        if r.ljungbox_pvalue < 0.01:
            votes_for += 1
        elif r.ljungbox_pvalue > 0.10:
            votes_against += 1

    if r.dom_period_ratio is not None and r.dom_period_bars is not None and r.period:
        if r.dom_period_ratio > 5 and 0.8 * r.period <= r.dom_period_bars <= 1.2 * r.period:
            votes_for += 1
        elif r.dom_period_ratio < 2:
            votes_against += 1

    if r.kw_pvalue is not None:
        if r.kw_pvalue < 0.01:
            votes_for += 1
        elif r.kw_pvalue > 0.10:
            votes_against += 1

    if votes_for >= 3 and votes_for > votes_against:
        return "seasonal"
    if votes_for >= 1 and votes_for >= votes_against:
        return "weak"
    return "none"


# ---------- Per-series pipeline ----------

def analyze(series: pd.Series, exch: str, sym: str, ivl: str) -> SeasonalityResult:
    period, label = PERIOD_BY_INTERVAL.get(ivl, (None, None))
    bucket_name, bucket_fn = BUCKET_BY_INTERVAL.get(ivl, (None, None))
    latest = series.index.max().date() if len(series) else None

    base = SeasonalityResult(
        exchange_code=exch, symbol_code=sym, interval_code=ivl,
        latest_as_of_date=latest,
        n_obs=len(series), period=period, period_label=label,
        stl_strength=None, ljungbox_pvalue=None,
        dom_period_bars=None, dom_period_ratio=None,
        kw_pvalue=None, kw_bucket=bucket_name,
        verdict="insufficient_data",
    )

    if period is None:
        base.notes = f"no defined seasonal period for interval '{ivl}'"
        return base
    if len(series) < max(2 * period + 1, 30):
        base.notes = f"need >= {2 * period + 1} obs, have {len(series)}"
        return base

    diffs = series.diff().dropna()
    if diffs.std() == 0:
        base.notes = "series is flat after differencing"
        return base

    arr = diffs.values
    base.stl_strength    = stl_strength(arr, period)
    base.ljungbox_pvalue = ljungbox_seasonal(arr, period)
    dom_p, ratio         = periodogram_peak(arr, period)
    base.dom_period_bars = dom_p
    base.dom_period_ratio = ratio
    if bucket_fn is not None:
        base.kw_pvalue = kruskal_by_bucket(diffs, bucket_fn)

    base.verdict = make_verdict(base)
    return base


# ---------- Worker process: one connection per worker, reused for all tasks ----------

# Each worker process keeps a single connection cached at module scope. This is
# initialized lazily on first use (by initializer or first call) and reused for
# every task this worker handles, which avoids the per-task connection setup
# cost. Workers exit cleanly when the pool shuts down.
_WORKER_CONN = None
_WORKER_DSN: dict | str | None = None


def _worker_init(dsn_or_kwargs):
    """Pool initializer: store the DSN/kwargs for lazy connection."""
    global _WORKER_DSN
    _WORKER_DSN = dsn_or_kwargs


def _get_worker_conn():
    global _WORKER_CONN
    if _WORKER_CONN is None or _WORKER_CONN.closed:
        if isinstance(_WORKER_DSN, str):
            _WORKER_CONN = psycopg2.connect(_WORKER_DSN)
        else:
            _WORKER_CONN = psycopg2.connect(**_WORKER_DSN)
    return _WORKER_CONN


def _worker_run(target: tuple[str, str, str]) -> SeasonalityResult | None:
    exch, sym, ivl = target
    try:
        conn = _get_worker_conn()
        series = load_series(conn, exch, sym, ivl)
        return analyze(series, exch, sym, ivl)
    except Exception:
        # Log inside the worker; exception object would lose context across IPC.
        logging.exception("Worker failed on %s:%s/%s", exch, sym, ivl)
        return None


# ---------- Orchestration ----------

def parallel_analyze(targets: list[tuple[str, str, str]],
                     n_workers: int,
                     dsn_or_kwargs,
                     progress_every: int,
                     ) -> list[SeasonalityResult]:
    out: list[SeasonalityResult] = []

    if n_workers <= 1:
        # Single-process path -- one connection, simple loop. Good for debugging.
        _worker_init(dsn_or_kwargs)
        try:
            t0 = time.monotonic()
            for i, target in enumerate(targets, 1):
                r = _worker_run(target)
                if r is not None:
                    out.append(r)
                if i % progress_every == 0:
                    rate = i / (time.monotonic() - t0)
                    eta = (len(targets) - i) / rate if rate > 0 else 0
                    logging.info("Processed %d/%d (%.1f symbols/s, ETA %.0fs)",
                                 i, len(targets), rate, eta)
        finally:
            if _WORKER_CONN is not None:
                _WORKER_CONN.close()
        return out

    # Process pool. 'spawn' is safer than 'fork' for processes that hold DB
    # connections, threads, or BLAS state -- but it does require the worker
    # functions to be importable at module top level, which they are.
    ctx = mp.get_context("spawn")

    t0 = time.monotonic()
    completed = 0
    last_log = t0

    with ProcessPoolExecutor(
        max_workers=n_workers,
        mp_context=ctx,
        initializer=_worker_init,
        initargs=(dsn_or_kwargs,),
    ) as ex:
        futures = {ex.submit(_worker_run, t): t for t in targets}
        for fut in as_completed(futures):
            try:
                r = fut.result()
            except Exception:
                logging.exception("Future failed for %s", futures[fut])
                r = None
            if r is not None:
                out.append(r)
            completed += 1
            now = time.monotonic()
            if completed % progress_every == 0 or (now - last_log) >= 2.0:
                rate = completed / (now - t0)
                eta = (len(targets) - completed) / rate if rate > 0 else 0
                logging.info("Processed %d/%d (%.1f symbols/s, ETA %.0fs)",
                             completed, len(targets), rate, eta)
                last_log = now

    elapsed = time.monotonic() - t0
    logging.info("Analysis complete: %d symbols in %.1fs (%.1f symbols/s, %d workers)",
                 completed, elapsed, completed / elapsed if elapsed else 0, n_workers)
    return out


# ---------- Numeric capping ----------

NUMERIC_CAPS = {
    "stl_strength":     (-99.9999,        99.9999),
    "ljungbox_pvalue":  (0.0,             1.0),
    "dom_period_bars":  (-999999.9999,    999999.9999),
    "dom_period_ratio": (-99999999.9999,  99999999.9999),
    "kw_pvalue":        (0.0,             1.0),
}


def _cap(name: str, value):
    if value is None:
        return None
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    lo, hi = NUMERIC_CAPS[name]
    return max(lo, min(hi, value))


def _result_to_row(r: SeasonalityResult, computed_at: datetime) -> tuple | None:
    if r.latest_as_of_date is None:
        return None
    return (
        r.exchange_code, r.symbol_code, r.latest_as_of_date,
        r.interval_code, r.period, r.period_label, r.n_obs,
        _cap("stl_strength",     r.stl_strength),
        _cap("ljungbox_pvalue",  r.ljungbox_pvalue),
        _cap("dom_period_bars",  r.dom_period_bars),
        _cap("dom_period_ratio", r.dom_period_ratio),
        _cap("kw_pvalue",        r.kw_pvalue),
        r.kw_bucket, r.verdict, r.notes, computed_at,
    )


# ---------- Write-back: symbol_technical ----------

WRITE_TECHNICAL_TEMP = """
    CREATE TEMP TABLE _seasonality_stage_tech (
        exchange_code            text,
        symbol_code              text,
        as_of_date               date,
        seasonality_interval     text,
        seasonality_period       integer,
        seasonality_period_label text,
        seasonality_n_obs        integer,
        stl_strength             numeric(6, 4),
        ljungbox_pvalue          numeric(8, 6),
        dom_period_bars          numeric(10, 4),
        dom_period_ratio         numeric(12, 4),
        kw_pvalue                numeric(8, 6),
        kw_bucket                text,
        seasonality_verdict      text,
        notes                    text,
        seasonality_computed_at  timestamp without time zone
    ) ON COMMIT DROP
"""


def write_technical(conn, results: list[SeasonalityResult], computed_at: datetime) -> tuple[int, int]:
    rows = [t for t in (_result_to_row(r, computed_at) for r in results) if t is not None]
    if not rows:
        return 0, 0
    with conn.cursor() as cur:
        cur.execute(WRITE_TECHNICAL_TEMP)
        execute_values(cur, "INSERT INTO _seasonality_stage_tech VALUES %s",
                       rows, page_size=2_000)
        cur.execute("""
            UPDATE public.symbol_technical AS t
               SET seasonality_interval     = s.seasonality_interval,
                   seasonality_period       = s.seasonality_period,
                   seasonality_period_label = s.seasonality_period_label,
                   seasonality_n_obs        = s.seasonality_n_obs,
                   stl_strength             = s.stl_strength,
                   ljungbox_pvalue          = s.ljungbox_pvalue,
                   dom_period_bars          = s.dom_period_bars,
                   dom_period_ratio         = s.dom_period_ratio,
                   kw_pvalue                = s.kw_pvalue,
                   kw_bucket                = s.kw_bucket,
                   seasonality_verdict      = s.seasonality_verdict,
                   seasonality_computed_at  = s.seasonality_computed_at
              FROM _seasonality_stage_tech s
             WHERE t.exchange_code = s.exchange_code
               AND t.symbol_code   = s.symbol_code
               AND t.as_of_date    = s.as_of_date
        """)
        updated = cur.rowcount
        cur.execute("""
            SELECT COUNT(*)
              FROM _seasonality_stage_tech s
              LEFT JOIN public.symbol_technical t
                ON  t.exchange_code = s.exchange_code
                AND t.symbol_code   = s.symbol_code
                AND t.as_of_date    = s.as_of_date
             WHERE t.exchange_code IS NULL
        """)
        missing = cur.fetchone()[0]
    return updated, missing


# ---------- Write-back: symbol_seasonality_history ----------

HISTORY_INSERT_SQL = """
    INSERT INTO public.symbol_seasonality_history (
        exchange_code, symbol_code, as_of_date, seasonality_interval,
        seasonality_period, seasonality_period_label, seasonality_n_obs,
        stl_strength, ljungbox_pvalue, dom_period_bars, dom_period_ratio,
        kw_pvalue, kw_bucket, seasonality_verdict, notes, seasonality_computed_at
    ) VALUES %s
    ON CONFLICT (exchange_code, symbol_code, as_of_date, seasonality_interval)
    DO UPDATE SET
        seasonality_period       = EXCLUDED.seasonality_period,
        seasonality_period_label = EXCLUDED.seasonality_period_label,
        seasonality_n_obs        = EXCLUDED.seasonality_n_obs,
        stl_strength             = EXCLUDED.stl_strength,
        ljungbox_pvalue          = EXCLUDED.ljungbox_pvalue,
        dom_period_bars          = EXCLUDED.dom_period_bars,
        dom_period_ratio         = EXCLUDED.dom_period_ratio,
        kw_pvalue                = EXCLUDED.kw_pvalue,
        kw_bucket                = EXCLUDED.kw_bucket,
        seasonality_verdict      = EXCLUDED.seasonality_verdict,
        notes                    = EXCLUDED.notes,
        seasonality_computed_at  = EXCLUDED.seasonality_computed_at
"""


def write_history(conn, results: list[SeasonalityResult], computed_at: datetime) -> int:
    rows = [t for t in (_result_to_row(r, computed_at) for r in results) if t is not None]
    if not rows:
        return 0
    with conn.cursor() as cur:
        execute_values(cur, HISTORY_INSERT_SQL, rows, page_size=2_000)
        return cur.rowcount


# ---------- Driver ----------

def collect_targets(conn, args) -> list[tuple[str, str, str]]:
    if args.symbol:
        token = args.symbol.replace(":", " ").split()
        if len(token) != 2:
            raise SystemExit(f"--symbol expects EXCH:SYM, got {args.symbol!r}")
        return [(token[0], token[1], args.interval)]
    rows = list_symbols(conn, args.interval, args.min_obs)
    logging.info("Found %d symbols meeting min-obs threshold.", len(rows))
    return [(exch, sym, ivl) for exch, sym, ivl, _n in rows]


def make_dsn_kwargs() -> dict:
    return dict(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
    )


def make_conn(dsn: str | None):
    if dsn:
        return psycopg2.connect(dsn)
    return psycopg2.connect(**make_dsn_kwargs())


def parse_args(argv=None):
    default_workers = min(16, os.cpu_count() or 1)
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--dsn")
    p.add_argument("--interval", default="d",
                   help="interval_code to analyze (default: d)")
    p.add_argument("--symbol",
                   help="single symbol as EXCH:SYM, e.g. NASDAQ:AAPL")
    p.add_argument("--min-obs", type=int, default=600,
                   help="skip series with fewer rows (default 600)")
    p.add_argument("--out", default="seasonality_results.csv",
                   help="CSV output path")
    p.add_argument("--workers", type=int, default=default_workers,
                   help=f"parallel worker PROCESSES (default {default_workers}, "
                        f"based on detected CPU count; use 1 for single-process)")
    p.add_argument("--progress-every", type=int, default=100,
                   help="log progress every N completions (default 100)")
    p.add_argument("--write-db", action="store_true",
                   help="UPDATE symbol_technical with latest snapshot")
    p.add_argument("--write-history", action="store_true",
                   help="UPSERT results into symbol_seasonality_history")
    p.add_argument("--dry-run", action="store_true",
                   help="With --write-db / --write-history: roll back instead of committing")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(processName)s] %(message)s",
    )
    logging.info("Configuration: workers=%d, cpu_count=%d, BLAS threads pinned to 1",
                 args.workers, os.cpu_count() or 0)

    # Phase 0: collect targets on the main process.
    try:
        conn = make_conn(args.dsn)
    except psycopg2.Error as e:
        logging.error("Could not connect: %s", e)
        return 2
    try:
        targets = collect_targets(conn, args)
    finally:
        conn.close()

    if not targets:
        logging.warning("No symbols matched the criteria; nothing to do.")
        return 0

    # Phase 1: analysis in parallel.
    dsn_or_kwargs = args.dsn if args.dsn else make_dsn_kwargs()
    results = parallel_analyze(
        targets, args.workers, dsn_or_kwargs,
        progress_every=args.progress_every,
    )

    counts = {"seasonal": 0, "weak": 0, "none": 0, "insufficient_data": 0}
    for r in results:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1

    # Phase 2: write-back (main process, single connection, single transaction).
    computed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if (args.write_db or args.write_history) and results:
        try:
            conn = make_conn(args.dsn)
        except psycopg2.Error as e:
            logging.error("Could not connect for write-back: %s", e)
            return 1
        try:
            with conn:
                if args.write_history:
                    logging.info("Upserting %d rows into symbol_seasonality_history...",
                                 len(results))
                    n_hist = write_history(conn, results, computed_at)
                    logging.info("History upsert affected %d rows.", n_hist)

                if args.write_db:
                    logging.info("Updating symbol_technical with %d results...",
                                 len(results))
                    updated, missing = write_technical(conn, results, computed_at)
                    logging.info("UPDATE matched %d rows in symbol_technical.", updated)
                    if missing:
                        logging.warning(
                            "%d staged rows had no matching (exchange, symbol, as_of_date) "
                            "in symbol_technical and were not applied.",
                            missing,
                        )

                if args.dry_run:
                    logging.warning("--dry-run: rolling back.")
                    conn.rollback()
        except psycopg2.Error as e:
            logging.error("Write-back failed: %s", e)
            return 1
        finally:
            conn.close()

    # CSV always written.
    if results:
        fieldnames = list(asdict(results[0]).keys())
        with open(args.out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader()
            for r in results:
                row = asdict(r)
                if isinstance(row.get("latest_as_of_date"), date):
                    row["latest_as_of_date"] = row["latest_as_of_date"].isoformat()
                w.writerow(row)
        logging.info("Wrote %d rows to %s", len(results), args.out)

    print("\nSeasonality verdict summary:")
    for k in ("seasonal", "weak", "none", "insufficient_data"):
        print(f"  {k:<20s} {counts.get(k, 0):>6d}")

    seasonal = [r for r in results if r.verdict == "seasonal"]
    if seasonal:
        seasonal.sort(key=lambda r: -(r.stl_strength or 0))
        print("\nTop 10 by STL seasonal strength:")
        for r in seasonal[:10]:
            print(f"  {r.exchange_code}:{r.symbol_code:<10s} "
                  f"Fs={r.stl_strength:.3f}  "
                  f"LB-p={r.ljungbox_pvalue if r.ljungbox_pvalue is not None else float('nan'):.4f}  "
                  f"KW-p={r.kw_pvalue if r.kw_pvalue is not None else float('nan'):.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())