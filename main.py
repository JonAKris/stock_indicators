#!/usr/bin/env python3
"""
main.py – CLI entry point for the EODData → PostgreSQL ETL pipeline.

Usage:
    python main.py                          # full sync (all exchanges)
    python main.py --exchanges NASDAQ NYSE  # specific exchanges
    python main.py --steps metadata exchanges symbols  # selective steps
    python main.py --interval d --days 90   # daily quotes, last 90 days

Run `python main.py --help` for all options.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from config import Config
from database import close_pool
from sync import run_full_sync

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=level,
        stream=sys.stdout,
    )
    # Quieten noisy third-party libs
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)

VALID_STEPS = ["metadata", "exchanges", "symbols", "profiles", "fundamentals", "technicals", "quotes"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync EODData market data into PostgreSQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--exchanges",
        nargs="+",
        metavar="CODE",
        help="Exchange codes to sync (e.g. NASDAQ NYSE). Defaults to all.",
    )
    parser.add_argument(
        "--steps",
        nargs="+",
        choices=VALID_STEPS,
        metavar="STEP",
        help=(
            "Subset of pipeline steps to run. "
            f"Choices: {', '.join(VALID_STEPS)}. Defaults to all."
        ),
    )
    parser.add_argument(
        "--interval",
        default=None,
        metavar="INTERVAL",
        help="Quote interval override: d, w, m, q, y, 1, 5, 10, 15, 30, h",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG logging",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _configure_logging(args.verbose)

    # Build config, then apply CLI overrides
    try:
        config = Config()
    except KeyError as exc:
        logger.error("Missing required environment variable: %s", exc)
        logger.error("Copy .env.example to .env and fill in the values.")
        return 1

    if args.exchanges:
        config.EXCHANGES = [e.upper() for e in args.exchanges]
    if args.interval:
        config.QUOTE_INTERVAL = args.interval

    logger.info("Starting EODData sync")
    logger.info("  Exchanges : %s", config.EXCHANGES or "ALL")
    logger.info("  Steps     : %s", args.steps or "ALL")
    logger.info("  Interval  : %s", config.QUOTE_INTERVAL)

    start = time.monotonic()
    try:
        run_full_sync(config, steps=args.steps)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except Exception as exc:
        logger.error("Fatal error: %s", exc, exc_info=True)
        return 1
    finally:
        close_pool()

    elapsed = time.monotonic() - start
    logger.info("Sync complete in %.1f seconds", elapsed)
    return 0


if __name__ == "__main__":
    main()
