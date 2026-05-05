# Stockman — Dash Portfolio Simulator

A single-file Dash app for managing portfolios, trades, and cash transactions
on top of the Stockman Postgres market-data warehouse.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
python app.py
```

## Serve with gunicorn, insure port 8000 is open if firewalled.

```bash
gunicorn app:app --bind 0.0.0.0:8000
```

Open http://localhost:8000.

## Prerequisites

The schema must be loaded first. From the project root:

Make sure the `symbol` table is populated — the trade form's symbol dropdown
reads from it. If it's empty, you'll have no symbols to trade against.

## What's in the UI

- **Portfolios tab.** Performance summary at top (cash, market value, realized + unrealized P&L, return %). Editable portfolio table below. Soft-delete via the `is_active` toggle, hard-delete (cascades trades) via the delete button.
- **Trades tab.** Filter by portfolio. New trade form with symbol dropdown sourced from the DB. Inline edit of date, side, quantity, price, fees, notes. Multi-row delete.
- **Positions tab.** Read-only view of `portfolio_positions` with split-adjusted quantities and unrealized P&L.
- **Cash tab.** Deposits, withdrawals, dividends, fees. Same edit/delete pattern.

## Architecture notes

**Refresh model.** A `dcc.Store` named `refresh-trigger` holds a counter. Every mutation increments it; every render callback listens to it. This avoids cross-callback dependencies and gives each table a single source of truth for "should I refetch."

**Inline edits.** Each editable table compares `data` to `data_previous` to detect what changed, then issues an UPDATE per changed row. If the UPDATE fails (e.g., CHECK constraint), the banner shows the error and the table refetches to show actual DB state.

**Symbol dropdown.** Sourced from `symbol` joined to `symbol_profile` for display names. If your symbol catalog is large (>10k rows), this dropdown will get sluggish — switch to `dcc.Dropdown(search_value=...)` with a server-side callback that queries by `LIKE` prefix.

**Money formatting.** Numeric columns are formatted as strings before display. This means filtering on those columns is string-based, not numeric. Acceptable trade-off for a simulator; switch to `dash_table.FormatTemplate.money(2)` per-column if you want numeric filters.

## Things this app does not do (and probably should, eventually)

- **Oversell guard.** You can record a SELL that exceeds your holding. Easy to add as a callback validation before INSERT.
- **Multi-currency rollup.** Cash balance assumes single-currency per portfolio. Mixing currencies will produce garbage numbers until you add an FX rates table.
- **Splits/dividends ingestion.** The schema has tables for them but the app doesn't import from EODData. Add a "Sync corporate actions" button that calls `/Splits/List/{exchange}` and upserts.
- **Auto-create cash transaction on dividend.** When you record a dividend on a held position, the app should compute `shares × per_share_amount` and create a `cash_transactions` row of type DIVIDEND. Currently manual.
- **Charts.** No equity curve, no drawdown, no per-symbol performance chart. The data is all there in `symbol_quote` — add a Plotly chart on the Positions or Portfolios tab.
- **Auth.** No login. Anyone who reaches the URL can edit everything. Fine for localhost; add `dash-auth` or front it with nginx basic auth before exposing it.
