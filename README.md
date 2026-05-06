# Stock Indicators ETL

Downloads market data from the [EODData API v1](https://api.eoddata.com) and stores it in a PostgreSQL database matching `schema.sql`.

## Project layout

```
stock_indicators/
├── .env.example          # Environment variable template
├── config.py             # Config dataclass (reads .env)
├── database.py           # psycopg2 connection pool + upsert helpers
├── api_client.py         # EODData REST API client (rate-limit aware)
├── stock_charting/
│   ├── app.py         # Simple dash charting app for postgres data
│   ├── README.md
├── loaders/
│   ├── metadata_loader.py  # Countries & Currencies (no auth required)
│   ├── exchange_loader.py  # Exchanges
│   └── symbol_loader.py    # Symbols, Profiles, Fundamentals, Technicals, Quotes
├── sync.py               # Orchestration – full pipeline
├── main.py               # CLI entry point
├── requirements.txt
└── bulk_load_history.py  # bulk history loader
```

## Quick start

### 1. Install dependencies

```bash
git clone https://github.com/JonAKris/stock_indicators
cd stock_indicators
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env – fill in EOD_API_KEY and DB_* values
```

### 3. Apply the database schema

```bash
sudo su postgres
psql
CREATE USER stockman;
CREATE DATABASE stocks;
GRANT ALL PRIVILEGES ON DATABASE stocks TO USER stockman;
\q
sudo su postgres -c 'psql -U stockman -d stockdb -f schema.sql'
```

### 4. Run the sync

```bash
# Full sync (all exchanges, daily quotes, last 365 days)
python main.py

# Specific exchanges only
python main.py --exchanges NASDAQ NYSE AMEX

# Only refresh symbols and quotes (skip profiles/fundamentals/technicals)
python main.py --steps symbols quotes

# Weekly quotes, last 5 years
python main.py --interval w --days 1825

# Debug output
python main.py --verbose
```

## Pipeline steps

| Step | API endpoint(s) | DB table(s) |
|---|---|---|
| `metadata` | `/Country/List`, `/Currency/List` | `countries`, `currencies` |
| `exchanges` | `/Exchange/List` | `exchanges` |
| `symbols` | `/Symbol/List/{exchange}` | `symbol` |
| `profiles` | `/Profile/List/{exchange}` | `symbol_profile` |
| `fundamentals` | `/Fundamental/List/{exchange}` | `symbol_fundamental` |
| `technicals` | `/Technical/List/{exchange}` | `symbol_technical` |
| `quotes` | `/Quote/List/{exchange}/{symbol}` | `symbol_quote` |

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TIMEOUT` | No | 180 | Network timeout in seconds |
| `EOD_API_KEY` | **Yes** | – | Your EODData API key |
| `DB_HOST` | No | `localhost` | PostgreSQL host |
| `DB_PORT` | No | `5432` | PostgreSQL port |
| `DB_NAME` | No | `stocks` | Database name |
| `DB_USER` | No | `stockman` | Database user |
| `DB_PASS` | **Yes** | – | Database password |
| `EXCHANGES` | No | *(all)* | Comma-separated exchange codes to sync |
| `QUOTE_INTERVAL` | No | `d` | Quote interval (`d`, `w`, `m`, `q`, `y`, `1`, `5`, `10`, `15`, `30`, `h`) |
| `QUOTE_DAYS` | No | `365` | History depth in days (0 = all available) |
| `MAX_WORKERS` | No | `4` | Parallel threads for per-symbol quote downloads |
| `REQUEST_DELAY` | No | `0.25` | Seconds to wait between API calls |

## Design notes

- **Idempotent** – every load uses `INSERT … ON CONFLICT … DO UPDATE`, so re-runs are safe.
- **Rate-limit resilient** – HTTP 429 responses trigger exponential back-off (up to ~64 s).
- **Exchange filter** – set `EXCHANGES` (or pass `--exchanges`) to limit scope; useful for incremental runs.
- **Concurrent quotes** – symbol-level quote history is fetched in parallel (`MAX_WORKERS` threads), each with its own DB connection from the pool.
- **Selective steps** – use `--steps` to re-run only the parts that need refreshing.
- **AI Code Generation** 100% coded using Claude Code.