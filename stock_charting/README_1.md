# Stock Charting App

A Plotly Dash stock charting dashboard backed by the PostgreSQL schema in `schema.sql` (`public.symbol`, `public.symbol_quote`, `public.symbol_profile`, `public.symbol_fundamental`, `public.symbol_technical`, plus `public.exchanges` / `public.countries` / `public.currencies`).

## Features

- **Exchange & symbol pickers** populated live from the `exchanges` and `symbol` tables.
- **Candlestick / OHLC / line / area charts** sourced from `symbol_quote` with configurable interval (`d`, `w`, `m`, `q`, `y`, `1`, `5`, `15`, `30`, `h`) and date range.
- **Volume pane** with up/down colouring keyed off open vs. close.
- **Overlay indicators** from `symbol_technical`: SMA 20/50/200, EMA 20/50, Bollinger Bands (20), Parabolic SAR.
- **Oscillator pane** with RSI(14), MACD, Stochastic %D(14), CCI, Williams %R.
- **Log-scale toggle** on the price pane.
- **Header snapshot** of latest close, change, volume, bid/ask from the `symbol` table.
- **Fundamentals tab** grouping valuation, per-share, profitability and balance-sheet metrics.
- **Profile tab** with identity (ISIN, CUSIP, FIGI, CIK, LEI, sector, industry) and contact info.
- **Data tab** with a sortable / filterable OHLCV table.

## Project layout

```
stock_charting_app/
├── app.py              # Dash layout + callbacks
├── db.py               # psycopg2 connection pool + queries
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

1. **Install dependencies**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure the database connection**

   Copy `.env.example` to `.env` and fill in your credentials, or export the variables in your shell:

   ```bash
   export DB_HOST=localhost
   export DB_PORT=5432
   export DB_NAME=stockman
   export DB_USER=stockman
   export DB_PASSWORD=yourpassword
   ```

   The defaults match the owners in `schema.sql` (`stockman` / `postgres`). Grant the connecting user `SELECT` on the five `public.symbol*` tables and on `public.exchanges`, `public.countries`, `public.currencies`.

3. **Run the app**

   ```bash
   python app.py
   ```

   Then open <http://127.0.0.1:8050>.

   For production:

   ```bash
   gunicorn -w 4 -b 0.0.0.0:8050 app:server
   ```

## Notes on the schema

- `symbol` holds one latest-snapshot row per `(exchange_code, symbol_code)`; the header strip reads from here.
- `symbol_quote` holds the time series keyed by `(exchange_code, symbol_code, interval_code, as_of_date)` — this is what the price chart plots. The `interval_code` check constraint allows `d/w/m/q/y/1/5/10/15/30/h`.
- `symbol_technical` is keyed by `(exchange_code, symbol_code, as_of_date)` with no interval — indicators are joined on date, so overlays align best with daily (`d`) quotes.
- If `public.exchanges` is empty, the app falls back to `SELECT DISTINCT exchange_code FROM public.symbol` so the UI still works.

## Customizing

- **Add indicators:** extend `OVERLAY_INDICATORS` / `OSCILLATORS` in `app.py` and add a branch in `_add_overlays` / `_add_oscillator`. Any column present in `symbol_technical` is fair game.
- **Change the default date range:** edit the `DatePickerRange` defaults in `build_sidebar()`.
- **Theme:** swap `dbc.themes.FLATLY` for any other [Bootswatch theme](https://bootswatch.com/) shipped with dash-bootstrap-components.
