"""
Stockman — Portfolio Simulator
Dash web app for managing portfolios, trades, and cash transactions
against the Postgres market-data warehouse.

Run:
    pip install -r requirements.txt
    cp .env.example .env   # then edit credentials
    python app.py
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dash_table, dcc, html, no_update
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()


def build_db_url() -> str:
    """Build a SQLAlchemy URL from .env. Prefers DATABASE_URL, falls back to DB_* vars."""
    if url := os.getenv("DATABASE_URL"):
        return url
    user = os.getenv("DB_USER", "stockman")
    pw = os.getenv("DB_PASS", "")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    db = os.getenv("DB_NAME", "stockman")
    return f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}"


engine: Engine = create_engine(build_db_url(), pool_pre_ping=True, future=True)


@contextmanager
def conn():
    with engine.begin() as c:
        yield c


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------

def q(sql: str, **params) -> pd.DataFrame:
    with engine.connect() as c:
        return pd.read_sql(text(sql), c, params=params)


def exec_sql(sql: str, **params) -> None:
    with conn() as c:
        c.execute(text(sql), params)


def fetch_portfolios(active_only: bool = False) -> pd.DataFrame:
    where = "WHERE is_active" if active_only else ""
    return q(f"""
        SELECT id, name, description, base_currency, initial_cash,
               is_active, created_at, updated_at
        FROM public.portfolios
        {where}
        ORDER BY id
    """)


def fetch_performance() -> pd.DataFrame:
    return q("SELECT * FROM public.portfolio_performance ORDER BY portfolio_id")


def fetch_positions(portfolio_id: int | None = None) -> pd.DataFrame:
    if portfolio_id is None:
        return q("SELECT * FROM public.portfolio_positions ORDER BY portfolio_id, symbol_code")
    return q(
        "SELECT * FROM public.portfolio_positions WHERE portfolio_id = :pid ORDER BY symbol_code",
        pid=portfolio_id,
    )


def fetch_trades(portfolio_id: int | None = None) -> pd.DataFrame:
    base = """
        SELECT t.id, t.portfolio_id, p.name AS portfolio,
               t.exchange_code, t.symbol_code,
               t.trade_date, t.side, t.quantity, t.price, t.fees,
               t.currency, t.notes, t.created_at, t.updated_at
        FROM public.trades t
        JOIN public.portfolios p ON p.id = t.portfolio_id
    """
    if portfolio_id is None:
        return q(base + " ORDER BY t.trade_date DESC, t.id DESC")
    return q(base + " WHERE t.portfolio_id = :pid ORDER BY t.trade_date DESC, t.id DESC",
             pid=portfolio_id)


def fetch_cash(portfolio_id: int | None = None) -> pd.DataFrame:
    base = """
        SELECT ct.id, ct.portfolio_id, p.name AS portfolio,
               ct.txn_date, ct.type, ct.amount, ct.currency, ct.notes,
               ct.created_at, ct.updated_at
        FROM public.cash_transactions ct
        JOIN public.portfolios p ON p.id = ct.portfolio_id
    """
    if portfolio_id is None:
        return q(base + " ORDER BY ct.txn_date DESC, ct.id DESC")
    return q(base + " WHERE ct.portfolio_id = :pid ORDER BY ct.txn_date DESC, ct.id DESC",
             pid=portfolio_id)


def fetch_symbol_options() -> list[dict]:
    """Symbols available for trading — sourced from the symbol table."""
    df = q("""
        SELECT s.exchange_code, s.symbol_code,
               COALESCE(sp.name, s.symbol_code) AS display_name
        FROM public.symbol s
        LEFT JOIN public.symbol_profile sp
          ON sp.exchange_code = s.exchange_code AND sp.symbol_code = s.symbol_code
        ORDER BY s.exchange_code, s.symbol_code
    """)
    return [
        {
            "label": f"{r.exchange_code}:{r.symbol_code} — {r.display_name}",
            "value": f"{r.exchange_code}|{r.symbol_code}",
        }
        for r in df.itertuples(index=False)
    ]


def fetch_portfolio_options(active_only: bool = True) -> list[dict]:
    df = fetch_portfolios(active_only=active_only)
    return [{"label": f"#{r.id} — {r.name}", "value": int(r.id)} for r in df.itertuples(index=False)]


def fetch_exchange_options() -> list[dict]:
    """Distinct exchange codes that have at least one symbol."""
    df = q("""
        SELECT DISTINCT s.exchange_code,
               COALESCE(e.exchange_name, s.exchange_code) AS name
        FROM public.symbol s
        LEFT JOIN public.exchanges e ON e.exchange_code = s.exchange_code
        ORDER BY s.exchange_code
    """)
    return [
        {"label": f"{r.exchange_code} — {r.name}" if r.name != r.exchange_code
                  else r.exchange_code,
         "value": r.exchange_code}
        for r in df.itertuples(index=False)
    ]


def fetch_symbol_options_for_exchange(exchange_code: str) -> list[dict]:
    """Symbols filtered to one exchange. Values are bare symbol_code (no pipe)."""
    df = q("""
        SELECT s.symbol_code,
               COALESCE(sp.name, s.symbol_code) AS display_name
        FROM public.symbol s
        LEFT JOIN public.symbol_profile sp
          ON sp.exchange_code = s.exchange_code AND sp.symbol_code = s.symbol_code
        WHERE s.exchange_code = :exch
        ORDER BY s.symbol_code
    """, exch=exchange_code)
    return [
        {"label": f"{r.symbol_code} — {r.display_name}", "value": r.symbol_code}
        for r in df.itertuples(index=False)
    ]


def fetch_daily_quotes(exchange_code: str, symbol_code: str,
                       from_date: str | None = None,
                       to_date: str | None = None) -> pd.DataFrame:
    """Daily OHLCV from symbol_quote where interval_code = 'd'."""
    sql = """
        SELECT as_of_date, open_price, high_price, low_price, close_price, volume
        FROM public.symbol_quote
        WHERE exchange_code = :exch
          AND symbol_code = :sym
          AND interval_code = 'd'
    """
    params: dict[str, Any] = {"exch": exchange_code, "sym": symbol_code}
    if from_date:
        sql += " AND as_of_date >= :from_dt"
        params["from_dt"] = from_date
    if to_date:
        sql += " AND as_of_date <= :to_dt"
        params["to_dt"] = to_date
    sql += " ORDER BY as_of_date"
    return q(sql, **params)


def fetch_trade_markers(portfolio_id: int | None,
                        exchange_code: str, symbol_code: str) -> pd.DataFrame:
    """Trades for a given symbol, optionally filtered to one portfolio.
    Used to overlay buy/sell markers on the price chart."""
    sql = """
        SELECT trade_date, side, quantity, price, portfolio_id
        FROM public.trades
        WHERE exchange_code = :exch AND symbol_code = :sym
    """
    params: dict[str, Any] = {"exch": exchange_code, "sym": symbol_code}
    if portfolio_id is not None:
        sql += " AND portfolio_id = :pid"
        params["pid"] = portfolio_id
    sql += " ORDER BY trade_date"
    return q(sql, **params)


def fetch_profile(exchange_code: str, symbol_code: str) -> dict | None:
    df = q("""
        SELECT * FROM public.symbol_profile
        WHERE exchange_code = :exch AND symbol_code = :sym
    """, exch=exchange_code, sym=symbol_code)
    return df.iloc[0].to_dict() if not df.empty else None


def fetch_fundamental(exchange_code: str, symbol_code: str) -> dict | None:
    df = q("""
        SELECT * FROM public.symbol_fundamental
        WHERE exchange_code = :exch AND symbol_code = :sym
    """, exch=exchange_code, sym=symbol_code)
    return df.iloc[0].to_dict() if not df.empty else None


def fetch_technical(exchange_code: str, symbol_code: str) -> dict | None:
    df = q("""
        SELECT * FROM public.symbol_technical
        WHERE exchange_code = :exch AND symbol_code = :sym
        ORDER BY as_of_date DESC
        LIMIT 1
    """, exch=exchange_code, sym=symbol_code)
    return df.iloc[0].to_dict() if not df.empty else None


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

CURRENCY_OPTS = [{"label": c, "value": c} for c in ("USD", "EUR", "GBP", "CAD", "AUD", "JPY")]
SIDE_OPTS = [{"label": "BUY", "value": "BUY"}, {"label": "SELL", "value": "SELL"}]
CASH_TYPE_OPTS = [{"label": t, "value": t} for t in
                  ("DEPOSIT", "WITHDRAWAL", "DIVIDEND", "FEE", "INTEREST", "FX_ADJUST")]

NUMBER_FORMAT = dash_table.FormatTemplate.money(2)
PERCENT_FORMAT = dash_table.FormatTemplate.percentage(2)


def df_to_table(df: pd.DataFrame, table_id: str, **kwargs) -> dash_table.DataTable:
    return dash_table.DataTable(
        id=table_id,
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        page_size=15,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "system-ui, sans-serif", "fontSize": "13px", "padding": "6px"},
        style_header={"fontWeight": "bold", "backgroundColor": "#f4f4f4"},
        **kwargs,
    )


def banner(msg: str, kind: str = "info") -> html.Div:
    colors = {"info": "#e7f3ff", "success": "#e7ffe7", "error": "#ffe7e7"}
    return html.Div(msg, style={
        "padding": "8px 12px", "borderRadius": "4px",
        "backgroundColor": colors.get(kind, "#eee"), "marginBottom": "8px",
    })


def held_quantity(portfolio_id: int, exchange_code: str, symbol_code: str) -> Decimal:
    """Net split-adjusted holding for a portfolio/symbol. Used as oversell guard."""
    df = q("""
        SELECT COALESCE(SUM(CASE WHEN side = 'BUY' THEN adj_quantity
                                 ELSE -adj_quantity END), 0) AS qty
        FROM public.split_adjusted_trades
        WHERE portfolio_id = :pid AND exchange_code = :exch AND symbol_code = :sym
    """, pid=portfolio_id, exch=exchange_code, sym=symbol_code)
    return Decimal(str(df.iloc[0]["qty"])) if not df.empty else Decimal(0)


def validate_trade(pf_id, sym_val, side, date, qty, price, fees,
                   editing_trade_id: int | None = None) -> str | None:
    """Return error message string, or None if valid. Used for both create and edit."""
    if not pf_id:
        return "Portfolio is required."
    if not sym_val:
        return "Symbol is required."
    if "|" not in str(sym_val):
        return "Symbol must be in 'EXCHANGE|SYMBOL' format."
    if side not in ("BUY", "SELL"):
        return "Side must be BUY or SELL."
    if not date:
        return "Trade date is required."
    try:
        parsed_date = pd.to_datetime(date).date()
    except (ValueError, TypeError):
        return f"Invalid date: {date!r}."
    if parsed_date > pd.Timestamp.today().date():
        return f"Trade date {parsed_date} is in the future."
    try:
        qty_d = Decimal(str(qty)) if qty is not None else None
    except Exception:
        return f"Quantity is not a number: {qty!r}."
    if qty_d is None or qty_d <= 0:
        return "Quantity must be greater than zero."
    try:
        price_d = Decimal(str(price)) if price is not None else None
    except Exception:
        return f"Price is not a number: {price!r}."
    if price_d is None or price_d < 0:
        return "Price must be zero or positive."
    if fees is not None:
        try:
            fees_d = Decimal(str(fees))
        except Exception:
            return f"Fees is not a number: {fees!r}."
        if fees_d < 0:
            return "Fees cannot be negative."
    # Oversell guard for SELL
    if side == "SELL":
        exch, sym = str(sym_val).split("|", 1)
        held = held_quantity(int(pf_id), exch, sym)
        # If editing an existing SELL, add its current qty back to held before checking
        if editing_trade_id is not None:
            existing = q("""
                SELECT side, quantity FROM public.trades WHERE id = :id
            """, id=editing_trade_id)
            if not existing.empty and existing.iloc[0]["side"] == "SELL":
                held += Decimal(str(existing.iloc[0]["quantity"]))
        if qty_d > held:
            return (f"Oversell: trying to sell {qty_d} but portfolio only holds "
                    f"{held} shares of {sym} on {exch}.")
    return None


def validate_cash(pf_id, ttype, date, amount) -> str | None:
    if not pf_id:
        return "Portfolio is required."
    if ttype not in ("DEPOSIT", "WITHDRAWAL", "DIVIDEND", "FEE", "INTEREST", "FX_ADJUST"):
        return f"Invalid type: {ttype!r}."
    if not date:
        return "Date is required."
    try:
        pd.to_datetime(date).date()
    except (ValueError, TypeError):
        return f"Invalid date: {date!r}."
    if amount is None:
        return "Amount is required."
    try:
        Decimal(str(amount))
    except Exception:
        return f"Amount is not a number: {amount!r}."
    return None


def validate_portfolio(name, ccy, cash) -> str | None:
    if not name or not str(name).strip():
        return "Name is required."
    if len(str(name)) > 100:
        return "Name is too long (max 100 chars)."
    if ccy and len(str(ccy)) != 3:
        return "Base currency must be a 3-letter code (e.g. USD)."
    if cash is not None:
        try:
            if Decimal(str(cash)) < 0:
                return "Initial cash cannot be negative."
        except Exception:
            return f"Initial cash is not a number: {cash!r}."
    return None


def _fmt_value(v: Any) -> str:
    """Format a single field value for display in info panels."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    if isinstance(v, (int,)) and not isinstance(v, bool):
        return f"{v:,}"
    if isinstance(v, (float, Decimal)):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return str(v)
        if abs(f) >= 1_000_000_000:
            return f"{f/1_000_000_000:,.2f}B"
        if abs(f) >= 1_000_000:
            return f"{f/1_000_000:,.2f}M"
        if abs(f) >= 1_000:
            return f"{f:,.2f}"
        return f"{f:,.4f}"
    return str(v)


def _info_grid(items: list[tuple[str, Any]]) -> html.Div:
    """Two-column key/value grid. Skips fields whose value is None/NaN."""
    cells = []
    for label, value in items:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        cells.append(html.Div([
            html.Div(label, style={"fontSize": "11px", "color": "#888",
                                    "textTransform": "uppercase",
                                    "letterSpacing": "0.5px"}),
            html.Div(_fmt_value(value), style={"fontSize": "14px",
                                                "fontWeight": "500",
                                                "marginTop": "2px"}),
        ], style={"padding": "6px 10px"}))
    if not cells:
        return html.Div("No data available.",
                        style={"color": "#999", "padding": "10px"})
    return html.Div(cells, style={
        "display": "grid",
        "gridTemplateColumns": "repeat(auto-fill, minmax(180px, 1fr))",
        "gap": "4px",
    })


def _panel(title: str, body) -> html.Div:
    return html.Div([
        html.H4(title, style={"margin": "0 0 8px 0",
                              "padding": "8px 12px",
                              "borderBottom": "1px solid #eee",
                              "backgroundColor": "#fafafa"}),
        html.Div(body, style={"padding": "8px 4px"}),
    ], style={"border": "1px solid #ddd", "borderRadius": "4px",
              "marginTop": "16px", "backgroundColor": "white"})


def render_profile_panel(p: dict | None) -> html.Div:
    if not p:
        return _panel("Profile", html.Div("No profile data for this symbol.",
                                           style={"color": "#999", "padding": "10px"}))
    header = []
    if p.get("name"):
        header.append(html.Div(p["name"], style={"fontSize": "18px",
                                                  "fontWeight": "600",
                                                  "padding": "0 10px 8px"}))
    if p.get("description") or p.get("about"):
        text = p.get("description") or p.get("about")
        header.append(html.Div(text, style={"padding": "0 10px 12px",
                                             "color": "#444",
                                             "lineHeight": "1.5",
                                             "fontSize": "13px"}))
    grid = _info_grid([
        ("Sector", p.get("sector")),
        ("Industry", p.get("industry")),
        ("Country", p.get("country")),
        ("Currency", p.get("currency")),
        ("Type", p.get("type")),
        ("FIGI", p.get("figi")),
        ("ISIN", p.get("isin")),
        ("CUSIP", p.get("cusip")),
        ("CIK", p.get("cik")),
        ("LEI", p.get("lei")),
        ("Phone", p.get("phone")),
        ("Address", p.get("address")),
    ])
    website = p.get("website")
    site_link = html.Div(
        html.A(website, href=website, target="_blank",
               style={"color": "#0366d6"}),
        style={"padding": "10px"}
    ) if website else None
    body = [*header, grid]
    if site_link is not None:
        body.append(site_link)
    return _panel("Profile", body)


def render_fundamental_panel(f: dict | None) -> html.Div:
    if not f:
        return _panel("Fundamentals",
                      html.Div("No fundamental data for this symbol.",
                               style={"color": "#999", "padding": "10px"}))
    grid = _info_grid([
        ("Market Cap", f.get("market_capitalization")),
        ("Shares Outstanding", f.get("shares_outstanding")),
        ("EBITDA", f.get("ebitda")),
        ("Revenue", f.get("revenue")),
        ("Gross Profit", f.get("gross_profit")),
        ("EPS", f.get("earnings_per_share")),
        ("Revenue / Share", f.get("revenue_per_share")),
        ("Book Value / Share", f.get("book_value_per_share")),
        ("Trailing P/E", f.get("trailing_pe")),
        ("Forward P/E", f.get("forward_pe")),
        ("PEG", f.get("peg")),
        ("Price / Sales", f.get("price_to_sales")),
        ("Price / Book", f.get("price_to_book")),
        ("Beta", f.get("beta")),
        ("Dividend / Share", f.get("dividend_per_share")),
        ("Dividend Yield", f.get("dividend_yield")),
        ("Dividend Date", f.get("dividend_date")),
        ("Gross Margin", f.get("gross_margin")),
        ("Profit Margin", f.get("profit_margin")),
        ("Operating Margin", f.get("operating_margin")),
        ("ROA", f.get("return_on_assets")),
        ("ROE", f.get("return_on_equity")),
        ("Total Cash", f.get("total_cash")),
        ("Cash / Share", f.get("total_cash_per_share")),
        ("Total Debt", f.get("total_debt")),
        ("Debt / Equity", f.get("total_debt_to_equity")),
    ])
    return _panel("Fundamentals", grid)


def render_technical_panel(t: dict | None) -> html.Div:
    if not t:
        return _panel("Technicals",
                      html.Div("No technical data for this symbol.",
                               style={"color": "#999", "padding": "10px"}))
    as_of = t.get("as_of_date")
    header = html.Div(f"As of {as_of}",
                      style={"padding": "0 10px 8px",
                             "color": "#666", "fontSize": "12px"}) if as_of else None

    perf_grid = _info_grid([
        ("YTD Change", t.get("ytd_change")),
        ("Quarter Change", t.get("quarter_change")),
        ("Biannual Change", t.get("biannual_change")),
        ("Year Change", t.get("year_change")),
        ("Year High", t.get("year_high")),
        ("Year Low", t.get("year_low")),
        ("Year Avg Volume", t.get("year_avg_volume")),
        ("Volatility", t.get("volatility")),
        ("Liquidity", t.get("liquidity")),
        ("ATR", t.get("atr")),
    ])
    ma_grid = _info_grid([
        ("MA 5", t.get("ma5")), ("MA 10", t.get("ma10")),
        ("MA 20", t.get("ma20")), ("MA 50", t.get("ma50")),
        ("MA 100", t.get("ma100")), ("MA 200", t.get("ma200")),
        ("EMA 20", t.get("ema20")), ("EMA 50", t.get("ema50")),
        ("EMA 200", t.get("ema200")),
    ])
    osc_grid = _info_grid([
        ("RSI 14", t.get("rsi14")), ("RSI 9", t.get("rsi9")),
        ("MACD", t.get("macd")),
        ("Stoch 14 Fast", t.get("sto14_fast")),
        ("Stoch 14 Slow", t.get("sto14_slow")),
        ("Williams %R 14", t.get("wpr14")),
        ("Momentum 14", t.get("mtm14")),
        ("ROC 14", t.get("roc14")),
        ("CCI", t.get("cci")),
        ("Aroon 20", t.get("aroon20")),
        ("DMI +", t.get("dmi_positive")),
        ("DMI -", t.get("dmi_negative")),
        ("BB Upper 20", t.get("upper_bb20")),
        ("BB Lower 20", t.get("lower_bb20")),
        ("BB Bandwidth", t.get("bandwidth_bb20")),
        ("SAR", t.get("sar")),
    ])
    body = [
        b for b in [
            header,
            html.H5("Performance & Volatility",
                    style={"margin": "12px 10px 4px", "color": "#555"}),
            perf_grid,
            html.H5("Moving Averages",
                    style={"margin": "16px 10px 4px", "color": "#555"}),
            ma_grid,
            html.H5("Oscillators & Bands",
                    style={"margin": "16px 10px 4px", "color": "#555"}),
            osc_grid,
        ] if b is not None
    ]
    return _panel("Technicals", body)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = Dash(__name__, suppress_callback_exceptions=True, title="Stockman")
server = app.server  # for gunicorn


# --- Layouts -------------------------------------------------------------

def portfolios_tab() -> html.Div:
    return html.Div([
        html.H3("Portfolios"),
        html.Div(id="portfolios-banner"),
        html.Details([
            html.Summary("➕ New portfolio", style={"cursor": "pointer", "fontWeight": "bold"}),
            html.Div([
                dcc.Input(id="new-pf-name", placeholder="Name", style={"marginRight": "8px"}),
                dcc.Input(id="new-pf-desc", placeholder="Description",
                          style={"marginRight": "8px", "width": "300px"}),
                dcc.Dropdown(id="new-pf-ccy", options=CURRENCY_OPTS, value="USD",
                             clearable=False, style={"width": "100px", "display": "inline-block",
                                                     "marginRight": "8px", "verticalAlign": "middle"}),
                dcc.Input(id="new-pf-cash", type="number", placeholder="Initial cash", value=10000,
                          style={"marginRight": "8px"}),
                html.Button("Create", id="new-pf-submit", n_clicks=0),
            ], style={"padding": "12px", "backgroundColor": "#fafafa",
                      "border": "1px solid #ddd", "borderRadius": "4px", "marginTop": "6px"}),
        ], style={"marginBottom": "16px"}),

        html.H4("Performance summary"),
        html.Div(id="performance-table-wrap"),

        html.H4("All portfolios (editable)", style={"marginTop": "24px"}),
        html.P("Edit name, description, base currency, initial cash, or active flag inline. "
               "Press Enter to commit. To delete: uncheck is_active (soft delete).",
               style={"color": "#666", "fontSize": "12px"}),
        html.Div(id="portfolios-table-wrap", children=[
            dash_table.DataTable(id="portfolios-table", data=[], columns=[],
                                 row_selectable="multi"),
        ]),
        html.Div([
            html.Button("🗑 Delete selected (hard delete + cascades trades)",
                        id="pf-delete-btn", n_clicks=0,
                        style={"backgroundColor": "#fee", "border": "1px solid #c44"}),
        ], style={"marginTop": "8px"}),
    ])


def trades_tab() -> html.Div:
    return html.Div([
        html.H3("Trades"),
        html.Div(id="trades-banner"),
        html.Div([
            html.Label("Filter by portfolio:", style={"marginRight": "8px"}),
            dcc.Dropdown(id="trades-pf-filter", options=[], placeholder="All portfolios",
                         style={"width": "280px", "display": "inline-block"}),
        ], style={"marginBottom": "12px"}),

        html.Details([
            html.Summary("➕ New trade", style={"cursor": "pointer", "fontWeight": "bold"}),
            html.Div([
                html.Div([
                    html.Label("Portfolio"),
                    dcc.Dropdown(id="new-tr-pf", options=[], style={"width": "260px"}),
                ], style={"display": "inline-block", "marginRight": "12px", "verticalAlign": "top"}),
                html.Div([
                    html.Label("Symbol"),
                    dcc.Dropdown(id="new-tr-symbol", options=[], placeholder="Type to search…",
                                 style={"width": "320px"}),
                ], style={"display": "inline-block", "marginRight": "12px", "verticalAlign": "top"}),
                html.Div([
                    html.Label("Side"),
                    dcc.Dropdown(id="new-tr-side", options=SIDE_OPTS, value="BUY",
                                 clearable=False, style={"width": "100px"}),
                ], style={"display": "inline-block", "marginRight": "12px", "verticalAlign": "top"}),
                html.Div([
                    html.Label("Date"),
                    dcc.DatePickerSingle(id="new-tr-date", date=pd.Timestamp.today().date()),
                ], style={"display": "inline-block", "marginRight": "12px", "verticalAlign": "top"}),
                html.Div([
                    html.Label("Quantity"),
                    dcc.Input(id="new-tr-qty", type="number", min=0, step=0.0001,
                              style={"width": "100px", "display": "block"}),
                ], style={"display": "inline-block", "marginRight": "12px", "verticalAlign": "top"}),
                html.Div([
                    html.Label("Price"),
                    dcc.Input(id="new-tr-price", type="number", min=0, step=0.0001,
                              style={"width": "100px", "display": "block"}),
                ], style={"display": "inline-block", "marginRight": "12px", "verticalAlign": "top"}),
                html.Div([
                    html.Label("Fees"),
                    dcc.Input(id="new-tr-fees", type="number", min=0, step=0.01, value=0,
                              style={"width": "80px", "display": "block"}),
                ], style={"display": "inline-block", "marginRight": "12px", "verticalAlign": "top"}),
                html.Div([
                    html.Label("Notes"),
                    dcc.Input(id="new-tr-notes", style={"width": "200px", "display": "block"}),
                ], style={"display": "inline-block", "marginRight": "12px", "verticalAlign": "top"}),
                html.Br(),
                html.Button("Record trade", id="new-tr-submit", n_clicks=0,
                            style={"marginTop": "10px"}),
            ], style={"padding": "12px", "backgroundColor": "#fafafa",
                      "border": "1px solid #ddd", "borderRadius": "4px", "marginTop": "6px"}),
        ], style={"marginBottom": "16px"}),

        html.H4("Trade history (editable)"),
        html.P("Edit trade_date, side, quantity, price, fees, or notes inline. "
               "Select rows to bulk-edit a field or delete.",
               style={"color": "#666", "fontSize": "12px"}),
        html.Div([
            html.Span("Bulk set field on selected: ",
                      style={"fontSize": "13px", "marginRight": "6px"}),
            dcc.Dropdown(id="tr-bulk-field",
                         options=[{"label": "side", "value": "side"},
                                  {"label": "currency", "value": "currency"},
                                  {"label": "fees", "value": "fees"},
                                  {"label": "notes", "value": "notes"}],
                         placeholder="Field",
                         style={"width": "140px", "display": "inline-block",
                                "verticalAlign": "middle", "marginRight": "6px"}),
            dcc.Input(id="tr-bulk-value", placeholder="New value",
                      style={"width": "200px", "marginRight": "6px"}),
            html.Button("Apply to selected", id="tr-bulk-apply", n_clicks=0),
        ], style={"padding": "8px", "backgroundColor": "#f8f8f8",
                  "border": "1px solid #e4e4e4", "borderRadius": "4px",
                  "marginBottom": "8px"}),
        html.Div(id="trades-table-wrap", children=[
            dash_table.DataTable(id="trades-table", data=[], columns=[],
                                 row_selectable="multi"),
        ]),
        html.Button("🗑 Delete selected", id="tr-delete-btn", n_clicks=0,
                    style={"marginTop": "8px", "backgroundColor": "#fee",
                           "border": "1px solid #c44"}),
    ])


def positions_tab() -> html.Div:
    return html.Div([
        html.H3("Open positions"),
        html.Div(id="positions-banner"),
        html.Div([
            html.Label("Portfolio:", style={"marginRight": "8px"}),
            dcc.Dropdown(id="pos-pf-filter", options=[], placeholder="All portfolios",
                         style={"width": "280px", "display": "inline-block"}),
        ], style={"marginBottom": "12px"}),
        html.P("Click a position row to see and edit the underlying trades.",
               style={"color": "#666", "fontSize": "12px"}),
        html.Div(id="positions-table-wrap", children=[
            # Placeholder so callbacks listening to positions-table have a target
            # at app-load time. Real table is injected by render_positions.
            dash_table.DataTable(id="positions-table", data=[], columns=[],
                                 row_selectable="single"),
        ]),
        html.Div(id="position-detail", style={"marginTop": "20px"}),
        dcc.ConfirmDialog(id="confirm-delete-pos-trade",
                          message="Delete selected trade(s)? This cannot be undone."),
    ])


def cash_tab() -> html.Div:
    return html.Div([
        html.H3("Cash transactions"),
        html.Div(id="cash-banner"),
        html.Div([
            html.Label("Filter by portfolio:", style={"marginRight": "8px"}),
            dcc.Dropdown(id="cash-pf-filter", options=[], placeholder="All portfolios",
                         style={"width": "280px", "display": "inline-block"}),
        ], style={"marginBottom": "12px"}),

        html.Details([
            html.Summary("➕ New cash transaction", style={"cursor": "pointer", "fontWeight": "bold"}),
            html.Div([
                dcc.Dropdown(id="new-ct-pf", options=[], placeholder="Portfolio",
                             style={"width": "240px", "display": "inline-block",
                                    "marginRight": "8px", "verticalAlign": "middle"}),
                dcc.Dropdown(id="new-ct-type", options=CASH_TYPE_OPTS, placeholder="Type",
                             style={"width": "150px", "display": "inline-block",
                                    "marginRight": "8px", "verticalAlign": "middle"}),
                dcc.DatePickerSingle(id="new-ct-date", date=pd.Timestamp.today().date()),
                dcc.Input(id="new-ct-amount", type="number", placeholder="Amount", step=0.01,
                          style={"marginLeft": "8px", "marginRight": "8px"}),
                dcc.Dropdown(id="new-ct-ccy", options=CURRENCY_OPTS, value="USD",
                             clearable=False, style={"width": "100px", "display": "inline-block",
                                                     "marginRight": "8px", "verticalAlign": "middle"}),
                dcc.Input(id="new-ct-notes", placeholder="Notes",
                          style={"marginRight": "8px", "width": "200px"}),
                html.Button("Record", id="new-ct-submit", n_clicks=0),
            ], style={"padding": "12px", "backgroundColor": "#fafafa",
                      "border": "1px solid #ddd", "borderRadius": "4px", "marginTop": "6px"}),
        ], style={"marginBottom": "16px"}),

        html.Div([
            html.Span("Bulk set field on selected: ",
                      style={"fontSize": "13px", "marginRight": "6px"}),
            dcc.Dropdown(id="ct-bulk-field",
                         options=[{"label": "type", "value": "type"},
                                  {"label": "currency", "value": "currency"},
                                  {"label": "notes", "value": "notes"}],
                         placeholder="Field",
                         style={"width": "140px", "display": "inline-block",
                                "verticalAlign": "middle", "marginRight": "6px"}),
            dcc.Input(id="ct-bulk-value", placeholder="New value",
                      style={"width": "200px", "marginRight": "6px"}),
            html.Button("Apply to selected", id="ct-bulk-apply", n_clicks=0),
        ], style={"padding": "8px", "backgroundColor": "#f8f8f8",
                  "border": "1px solid #e4e4e4", "borderRadius": "4px",
                  "marginBottom": "8px"}),
        html.Div(id="cash-table-wrap", children=[
            dash_table.DataTable(id="cash-table", data=[], columns=[],
                                 row_selectable="multi"),
        ]),
        html.Button("🗑 Delete selected", id="ct-delete-btn", n_clicks=0,
                    style={"marginTop": "8px", "backgroundColor": "#fee",
                           "border": "1px solid #c44"}),
    ])


def charts_tab() -> html.Div:
    return html.Div([
        html.H3("Symbol price chart"),
        html.P("Daily OHLC candles from symbol_quote. Optionally overlay your "
               "buy/sell markers from a selected portfolio.",
               style={"color": "#666", "fontSize": "13px"}),
        html.Div([
            html.Div([
                html.Label("Exchange"),
                dcc.Dropdown(id="chart-exchange", options=[],
                             placeholder="Pick an exchange…",
                             style={"width": "240px"}),
            ], style={"display": "inline-block", "marginRight": "12px",
                      "verticalAlign": "top"}),
            html.Div([
                html.Label("Symbol"),
                dcc.Dropdown(id="chart-symbol", options=[],
                             placeholder="Pick an exchange first",
                             disabled=True,
                             style={"width": "300px"}),
            ], style={"display": "inline-block", "marginRight": "12px",
                      "verticalAlign": "top"}),
            html.Div([
                html.Label("Date range"),
                dcc.DatePickerRange(
                    id="chart-date-range",
                    start_date=(pd.Timestamp.today() - pd.DateOffset(years=1)).date(),
                    end_date=pd.Timestamp.today().date(),
                ),
            ], style={"display": "inline-block", "marginRight": "12px",
                      "verticalAlign": "top"}),
            html.Div([
                html.Label("Overlay trades from"),
                dcc.Dropdown(id="chart-pf-overlay", options=[],
                             placeholder="(no overlay)",
                             style={"width": "260px"}),
            ], style={"display": "inline-block", "marginRight": "12px",
                      "verticalAlign": "top"}),
            html.Div([
                html.Label("Style"),
                dcc.RadioItems(id="chart-style",
                               options=[{"label": "Candles", "value": "candle"},
                                        {"label": "Line", "value": "line"}],
                               value="candle",
                               inline=True,
                               inputStyle={"marginRight": "4px",
                                           "marginLeft": "8px"}),
            ], style={"display": "inline-block", "verticalAlign": "top",
                      "marginRight": "12px"}),
            html.Div([
                html.Label("MA overlays"),
                dcc.Checklist(id="chart-ma-overlays",
                              options=[{"label": "MA50", "value": "ma50"},
                                       {"label": "MA200", "value": "ma200"}],
                              value=[],
                              inline=True,
                              inputStyle={"marginRight": "4px",
                                          "marginLeft": "8px"}),
            ], style={"display": "inline-block", "verticalAlign": "top"}),
        ], style={"marginBottom": "12px"}),
        dcc.Loading(dcc.Graph(id="price-chart", style={"height": "560px"}),
                    type="default"),
        html.Div(id="profile-panel"),
        html.Div(id="fundamental-panel"),
        html.Div(id="technical-panel"),
    ])


app.layout = html.Div([
    html.Div([
        html.H2("📈 Stockman", style={"display": "inline-block", "margin": 0}),
        html.Span("  Portfolio Simulator",
                  style={"color": "#666", "marginLeft": "8px"}),
    ], style={"borderBottom": "1px solid #ddd", "paddingBottom": "8px", "marginBottom": "16px"}),
    dcc.Tabs(id="tabs", value="charts", children=[
        dcc.Tab(label="Charts", value="charts", children=charts_tab()),
        dcc.Tab(label="Portfolios", value="portfolios", children=portfolios_tab()),
        dcc.Tab(label="Trades", value="trades", children=trades_tab()),
        dcc.Tab(label="Positions", value="positions", children=positions_tab()),
        dcc.Tab(label="Cash", value="cash", children=cash_tab()),
    ]),
    dcc.Store(id="refresh-trigger", data=0),
    dcc.ConfirmDialog(id="confirm-delete-pf",
                      message="Delete selected portfolio(s)? This cascades to all their trades and cash transactions and cannot be undone."),
    dcc.ConfirmDialog(id="confirm-delete-tr",
                      message="Delete selected trade(s)? This cannot be undone."),
    dcc.ConfirmDialog(id="confirm-delete-ct",
                      message="Delete selected cash transaction(s)? This cannot be undone."),
], style={"maxWidth": "1400px", "margin": "0 auto", "padding": "20px",
          "fontFamily": "system-ui, sans-serif"})


# ---------------------------------------------------------------------------
# Callbacks — Portfolios
# ---------------------------------------------------------------------------

@app.callback(
    Output("performance-table-wrap", "children"),
    Output("portfolios-table-wrap", "children"),
    Input("refresh-trigger", "data"),
    Input("tabs", "value"),
)
def render_portfolio_tables(_n: int, _tab: str):
    perf = fetch_performance()
    # Format money columns
    money_cols = ["initial_cash", "total_deposits", "total_withdrawals", "total_dividends",
                  "cash_balance", "market_value", "total_value", "realized_pnl",
                  "unrealized_pnl", "total_pnl"]
    for c in money_cols:
        if c in perf.columns:
            perf[c] = perf[c].apply(lambda v: f"{v:,.2f}" if pd.notna(v) else "")
    if "total_return_pct" in perf.columns:
        perf["total_return_pct"] = perf["total_return_pct"].apply(
            lambda v: f"{v:.2f}%" if pd.notna(v) else "")

    perf_table = df_to_table(perf, "performance-table")

    pf = fetch_portfolios(active_only=False)
    pf_table = dash_table.DataTable(
        id="portfolios-table",
        data=pf.to_dict("records"),
        columns=[
            {"name": "id", "id": "id", "editable": False},
            {"name": "name", "id": "name", "editable": True},
            {"name": "description", "id": "description", "editable": True},
            {"name": "base_currency", "id": "base_currency", "editable": True,
             "presentation": "dropdown"},
            {"name": "initial_cash", "id": "initial_cash", "editable": True, "type": "numeric"},
            {"name": "is_active", "id": "is_active", "editable": True,
             "presentation": "dropdown"},
            {"name": "created_at", "id": "created_at", "editable": False},
            {"name": "updated_at", "id": "updated_at", "editable": False},
        ],
        dropdown={
            "base_currency": {"options": CURRENCY_OPTS},
            "is_active": {"options": [{"label": "Yes", "value": True},
                                      {"label": "No", "value": False}]},
        },
        editable=True,
        row_selectable="multi",
        page_size=15,
        sort_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "system-ui, sans-serif", "fontSize": "13px", "padding": "6px"},
        style_header={"fontWeight": "bold", "backgroundColor": "#f4f4f4"},
    )
    return perf_table, pf_table


@app.callback(
    Output("portfolios-banner", "children"),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("new-pf-submit", "n_clicks"),
    State("new-pf-name", "value"),
    State("new-pf-desc", "value"),
    State("new-pf-ccy", "value"),
    State("new-pf-cash", "value"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def create_portfolio(n_clicks, name, desc, ccy, cash, trigger):
    if not n_clicks:
        return no_update, no_update
    err = validate_portfolio(name, ccy, cash)
    if err:
        return banner(err, "error"), no_update
    try:
        exec_sql("""
            INSERT INTO public.portfolios (name, description, base_currency, initial_cash)
            VALUES (:name, :desc, :ccy, :cash)
        """, name=str(name).strip(), desc=desc, ccy=ccy or "USD", cash=cash or 0)
        return banner(f"Created portfolio “{name}”.", "success"), trigger + 1
    except Exception as e:
        return banner(f"Database error: {e}", "error"), no_update


@app.callback(
    Output("portfolios-banner", "children", allow_duplicate=True),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("portfolios-table", "data"),
    State("portfolios-table", "data_previous"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def edit_portfolio(data, data_prev, trigger):
    if not data_prev or data == data_prev:
        return no_update, no_update
    by_id_prev = {r["id"]: r for r in data_prev}
    changed = [r for r in data if by_id_prev.get(r["id"]) and by_id_prev[r["id"]] != r]
    if not changed:
        return no_update, no_update
    errors = []
    valid_rows = []
    for row in changed:
        err = validate_portfolio(row.get("name"), row.get("base_currency"),
                                  row.get("initial_cash"))
        if err:
            errors.append(f"Portfolio #{row['id']}: {err}")
        else:
            valid_rows.append(row)
    try:
        for row in valid_rows:
            exec_sql("""
                UPDATE public.portfolios
                SET name = :name, description = :desc, base_currency = :ccy,
                    initial_cash = :cash, is_active = :active
                WHERE id = :id
            """, id=row["id"], name=str(row["name"]).strip(),
                desc=row.get("description"), ccy=row["base_currency"],
                cash=row["initial_cash"], active=bool(row["is_active"]))
    except Exception as e:
        errors.append(f"Database error: {e}")
    if errors:
        return banner(" • ".join(errors), "error"), trigger + 1
    return banner(f"Updated {len(valid_rows)} portfolio(s).", "success"), trigger + 1


@app.callback(
    Output("confirm-delete-pf", "displayed"),
    Output("confirm-delete-pf", "message"),
    Output("portfolios-banner", "children", allow_duplicate=True),
    Input("pf-delete-btn", "n_clicks"),
    State("portfolios-table", "selected_rows"),
    State("portfolios-table", "data"),
    prevent_initial_call=True,
)
def confirm_delete_portfolios(n_clicks, selected, data):
    if not n_clicks:
        return False, no_update, no_update
    if not selected:
        return False, no_update, banner("Select rows first.", "error")
    names = [data[i].get("name") or f"#{data[i]['id']}" for i in selected]
    msg = (f"Permanently delete {len(selected)} portfolio(s): "
           f"{', '.join(names[:5])}{'…' if len(names) > 5 else ''}? "
           f"This cascades to ALL their trades and cash transactions and cannot be undone.")
    return True, msg, no_update


@app.callback(
    Output("portfolios-banner", "children", allow_duplicate=True),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("confirm-delete-pf", "submit_n_clicks"),
    State("portfolios-table", "selected_rows"),
    State("portfolios-table", "data"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def delete_portfolios(submit_n, selected, data, trigger):
    if not submit_n or not selected:
        return no_update, no_update
    ids = [data[i]["id"] for i in selected]
    try:
        with conn() as c:
            for pid in ids:
                c.execute(text("DELETE FROM public.portfolios WHERE id = :id"), {"id": pid})
        return banner(f"Deleted {len(ids)} portfolio(s) and their trades.", "success"), trigger + 1
    except Exception as e:
        return banner(f"Database error: {e}", "error"), no_update


# ---------------------------------------------------------------------------
# Callbacks — Trades
# ---------------------------------------------------------------------------

@app.callback(
    Output("trades-pf-filter", "options"),
    Output("new-tr-pf", "options"),
    Output("new-tr-symbol", "options"),
    Output("pos-pf-filter", "options"),
    Output("cash-pf-filter", "options"),
    Output("new-ct-pf", "options"),
    Output("chart-exchange", "options"),
    Output("chart-pf-overlay", "options"),
    Input("refresh-trigger", "data"),
)
def populate_dropdowns(_n: int):
    pf_opts = fetch_portfolio_options(active_only=False)
    sym_opts = fetch_symbol_options()
    exch_opts = fetch_exchange_options()
    return pf_opts, pf_opts, sym_opts, pf_opts, pf_opts, pf_opts, exch_opts, pf_opts


@app.callback(
    Output("trades-table-wrap", "children"),
    Input("refresh-trigger", "data"),
    Input("trades-pf-filter", "value"),
    Input("tabs", "value"),
)
def render_trades(_n, pf_id, _tab):
    df = fetch_trades(pf_id) if pf_id else fetch_trades()
    table = dash_table.DataTable(
        id="trades-table",
        data=df.to_dict("records"),
        columns=[
            {"name": "id", "id": "id", "editable": False},
            {"name": "portfolio", "id": "portfolio", "editable": False},
            {"name": "exchange_code", "id": "exchange_code", "editable": False},
            {"name": "symbol_code", "id": "symbol_code", "editable": False},
            {"name": "trade_date", "id": "trade_date", "editable": True},
            {"name": "side", "id": "side", "editable": True, "presentation": "dropdown"},
            {"name": "quantity", "id": "quantity", "editable": True, "type": "numeric"},
            {"name": "price", "id": "price", "editable": True, "type": "numeric"},
            {"name": "fees", "id": "fees", "editable": True, "type": "numeric"},
            {"name": "currency", "id": "currency", "editable": True},
            {"name": "notes", "id": "notes", "editable": True},
            {"name": "updated_at", "id": "updated_at", "editable": False},
        ],
        dropdown={"side": {"options": SIDE_OPTS}},
        editable=True,
        row_selectable="multi",
        page_size=20,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "system-ui, sans-serif", "fontSize": "13px", "padding": "6px"},
        style_header={"fontWeight": "bold", "backgroundColor": "#f4f4f4"},
        style_data_conditional=[
            {"if": {"filter_query": "{side} = 'BUY'", "column_id": "side"},
             "color": "#0a0", "fontWeight": "bold"},
            {"if": {"filter_query": "{side} = 'SELL'", "column_id": "side"},
             "color": "#c00", "fontWeight": "bold"},
        ],
    )
    return table


@app.callback(
    Output("trades-banner", "children"),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("new-tr-submit", "n_clicks"),
    State("new-tr-pf", "value"),
    State("new-tr-symbol", "value"),
    State("new-tr-side", "value"),
    State("new-tr-date", "date"),
    State("new-tr-qty", "value"),
    State("new-tr-price", "value"),
    State("new-tr-fees", "value"),
    State("new-tr-notes", "value"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def create_trade(n, pf_id, sym_val, side, date, qty, price, fees, notes, trigger):
    if not n:
        return no_update, no_update
    err = validate_trade(pf_id, sym_val, side, date, qty, price, fees)
    if err:
        return banner(err, "error"), no_update
    try:
        exch, sym = sym_val.split("|", 1)
        exec_sql("""
            INSERT INTO public.trades
                (portfolio_id, exchange_code, symbol_code, trade_date, side,
                 quantity, price, fees, notes)
            VALUES (:pid, :exch, :sym, :dt, :side, :qty, :price, :fees, :notes)
        """, pid=pf_id, exch=exch, sym=sym, dt=date, side=side,
            qty=qty, price=price, fees=fees or 0, notes=notes)
        return banner(f"Recorded {side} {qty} {sym} @ {price}.", "success"), trigger + 1
    except Exception as e:
        return banner(f"Database error: {e}", "error"), no_update


@app.callback(
    Output("trades-banner", "children", allow_duplicate=True),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("trades-table", "data"),
    State("trades-table", "data_previous"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def edit_trade(data, data_prev, trigger):
    if not data_prev or data == data_prev:
        return no_update, no_update
    by_id_prev = {r["id"]: r for r in data_prev}
    changed = [r for r in data if by_id_prev.get(r["id"]) and by_id_prev[r["id"]] != r]
    if not changed:
        return no_update, no_update
    errors = []
    valid_rows = []
    for row in changed:
        sym_val = f"{row['exchange_code']}|{row['symbol_code']}"
        err = validate_trade(row["portfolio_id"], sym_val, row["side"],
                             row["trade_date"], row["quantity"], row["price"],
                             row.get("fees"), editing_trade_id=row["id"])
        if err:
            errors.append(f"Trade #{row['id']}: {err}")
        else:
            valid_rows.append(row)
    try:
        for row in valid_rows:
            exec_sql("""
                UPDATE public.trades
                SET trade_date = :dt, side = :side, quantity = :qty,
                    price = :price, fees = :fees, currency = :ccy, notes = :notes
                WHERE id = :id
            """, id=row["id"], dt=row["trade_date"], side=row["side"],
                qty=row["quantity"], price=row["price"], fees=row["fees"] or 0,
                ccy=row.get("currency"), notes=row.get("notes"))
    except Exception as e:
        errors.append(f"Database error: {e}")
    if errors:
        return banner(" • ".join(errors), "error"), trigger + 1
    return banner(f"Updated {len(valid_rows)} trade(s).", "success"), trigger + 1


@app.callback(
    Output("confirm-delete-tr", "displayed"),
    Output("confirm-delete-tr", "message"),
    Output("trades-banner", "children", allow_duplicate=True),
    Input("tr-delete-btn", "n_clicks"),
    State("trades-table", "selected_rows"),
    State("trades-table", "data"),
    prevent_initial_call=True,
)
def confirm_delete_trades(n, selected, data):
    if not n:
        return False, no_update, no_update
    if not selected:
        return False, no_update, banner("Select rows first.", "error")
    return True, (f"Delete {len(selected)} trade(s)? This cannot be undone "
                  "and will affect realized P&L and current positions."), no_update


@app.callback(
    Output("trades-banner", "children", allow_duplicate=True),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("confirm-delete-tr", "submit_n_clicks"),
    State("trades-table", "selected_rows"),
    State("trades-table", "data"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def delete_trades(submit_n, selected, data, trigger):
    if not submit_n or not selected:
        return no_update, no_update
    ids = [data[i]["id"] for i in selected]
    try:
        with conn() as c:
            for tid in ids:
                c.execute(text("DELETE FROM public.trades WHERE id = :id"), {"id": tid})
        return banner(f"Deleted {len(ids)} trade(s).", "success"), trigger + 1
    except Exception as e:
        return banner(f"Database error: {e}", "error"), no_update


@app.callback(
    Output("trades-banner", "children", allow_duplicate=True),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("tr-bulk-apply", "n_clicks"),
    State("trades-table", "selected_rows"),
    State("trades-table", "data"),
    State("tr-bulk-field", "value"),
    State("tr-bulk-value", "value"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def bulk_apply_trades(n, selected, data, field, value, trigger):
    if not n:
        return no_update, no_update
    if not selected:
        return banner("Select rows first.", "error"), no_update
    if not field:
        return banner("Pick a field to set.", "error"), no_update
    if value in (None, ""):
        return banner("Enter a value.", "error"), no_update
    # Validate field-specific values
    if field == "side" and value not in ("BUY", "SELL"):
        return banner("Side must be BUY or SELL.", "error"), no_update
    if field == "fees":
        try:
            if Decimal(str(value)) < 0:
                return banner("Fees cannot be negative.", "error"), no_update
        except Exception:
            return banner(f"Fees is not a number: {value!r}.", "error"), no_update
    if field == "currency" and len(str(value)) != 3:
        return banner("Currency must be a 3-letter code.", "error"), no_update

    ids = [data[i]["id"] for i in selected]
    column_sql = {"side": "side", "currency": "currency",
                  "fees": "fees", "notes": "notes"}[field]
    try:
        with conn() as c:
            for tid in ids:
                c.execute(text(
                    f"UPDATE public.trades SET {column_sql} = :val WHERE id = :id"),
                    {"val": value, "id": tid})
        return banner(f"Updated {field} on {len(ids)} trade(s).", "success"), trigger + 1
    except Exception as e:
        return banner(f"Database error: {e}", "error"), no_update


# ---------------------------------------------------------------------------
# Callbacks — Positions
# ---------------------------------------------------------------------------

@app.callback(
    Output("positions-table-wrap", "children"),
    Input("refresh-trigger", "data"),
    Input("pos-pf-filter", "value"),
    Input("tabs", "value"),
)
def render_positions(_n, pf_id, _tab):
    df = fetch_positions(pf_id) if pf_id else fetch_positions()
    money_cols = ["avg_buy_price", "current_price", "market_value", "unrealized_pnl", "total_fees"]
    for c in money_cols:
        if c in df.columns:
            df[c] = df[c].apply(lambda v: f"{v:,.4f}" if pd.notna(v) else "")
    return dash_table.DataTable(
        id="positions-table",
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        page_size=15,
        sort_action="native",
        filter_action="native",
        row_selectable="single",
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "system-ui, sans-serif", "fontSize": "13px",
                    "padding": "6px"},
        style_header={"fontWeight": "bold", "backgroundColor": "#f4f4f4"},
        style_data_conditional=[
            {"if": {"state": "selected"},
             "backgroundColor": "#e7f3ff",
             "border": "1px solid #6cf"},
        ],
    )


def _position_trades(portfolio_id: int, exchange_code: str, symbol_code: str) -> pd.DataFrame:
    return q("""
        SELECT id, trade_date, side, quantity, price, fees, currency, notes, updated_at
        FROM public.trades
        WHERE portfolio_id = :pid AND exchange_code = :exch AND symbol_code = :sym
        ORDER BY trade_date DESC, id DESC
    """, pid=portfolio_id, exch=exchange_code, sym=symbol_code)


@app.callback(
    Output("position-detail", "children"),
    Input("positions-table", "selected_rows"),
    Input("positions-table", "data"),
    Input("refresh-trigger", "data"),
)
def render_position_detail(selected, data, _trigger):
    if not selected or not data:
        return None
    row = data[selected[0]]
    pid = row["portfolio_id"]
    exch = row["exchange_code"]
    sym = row["symbol_code"]
    qty_held = row.get("quantity", 0)
    trades = _position_trades(pid, exch, sym)
    table = dash_table.DataTable(
        id="position-trades-table",
        data=trades.to_dict("records"),
        columns=[
            {"name": "id", "id": "id", "editable": False},
            {"name": "trade_date", "id": "trade_date", "editable": True},
            {"name": "side", "id": "side", "editable": True, "presentation": "dropdown"},
            {"name": "quantity", "id": "quantity", "editable": True, "type": "numeric"},
            {"name": "price", "id": "price", "editable": True, "type": "numeric"},
            {"name": "fees", "id": "fees", "editable": True, "type": "numeric"},
            {"name": "currency", "id": "currency", "editable": True},
            {"name": "notes", "id": "notes", "editable": True},
            {"name": "updated_at", "id": "updated_at", "editable": False},
        ],
        dropdown={"side": {"options": SIDE_OPTS}},
        editable=True,
        row_selectable="multi",
        page_size=10,
        sort_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "system-ui, sans-serif", "fontSize": "13px",
                    "padding": "6px"},
        style_header={"fontWeight": "bold", "backgroundColor": "#f4f4f4"},
        style_data_conditional=[
            {"if": {"filter_query": "{side} = 'BUY'", "column_id": "side"},
             "color": "#0a0", "fontWeight": "bold"},
            {"if": {"filter_query": "{side} = 'SELL'", "column_id": "side"},
             "color": "#c00", "fontWeight": "bold"},
        ],
    )
    return html.Div([
        html.H4(f"{exch}:{sym} — trades in “{row.get('portfolio_name', f'#{pid}')}”",
                style={"marginBottom": "4px"}),
        html.Div(f"Currently holding {qty_held} shares.",
                 style={"color": "#666", "marginBottom": "8px", "fontSize": "13px"}),
        html.Div([
            html.Button(f"📤 Close position (sell all {qty_held})",
                        id="pos-close-btn", n_clicks=0,
                        style={"marginRight": "8px"}),
            html.Button("🗑 Delete selected trades",
                        id="pos-trade-delete-btn", n_clicks=0,
                        style={"backgroundColor": "#fee", "border": "1px solid #c44"}),
        ], style={"marginBottom": "8px"}),
        # Hidden stores for the close-position context
        dcc.Store(id="pos-context",
                  data={"portfolio_id": pid, "exchange_code": exch,
                        "symbol_code": sym, "quantity": str(qty_held)}),
        table,
    ], style={"border": "1px solid #ddd", "borderRadius": "4px",
              "padding": "12px", "backgroundColor": "#fafafa"})


@app.callback(
    Output("positions-banner", "children", allow_duplicate=True),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("position-trades-table", "data"),
    State("position-trades-table", "data_previous"),
    State("pos-context", "data"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def edit_position_trades(data, data_prev, ctx, trigger):
    if not data_prev or data == data_prev or not ctx:
        return no_update, no_update
    by_id_prev = {r["id"]: r for r in data_prev}
    changed = [r for r in data if by_id_prev.get(r["id"]) and by_id_prev[r["id"]] != r]
    if not changed:
        return no_update, no_update
    pid = ctx["portfolio_id"]
    exch = ctx["exchange_code"]
    sym = ctx["symbol_code"]
    sym_val = f"{exch}|{sym}"
    errors = []
    valid_rows = []
    for row in changed:
        err = validate_trade(pid, sym_val, row["side"], row["trade_date"],
                             row["quantity"], row["price"], row.get("fees"),
                             editing_trade_id=row["id"])
        if err:
            errors.append(f"Trade #{row['id']}: {err}")
        else:
            valid_rows.append(row)
    try:
        for row in valid_rows:
            exec_sql("""
                UPDATE public.trades
                SET trade_date = :dt, side = :side, quantity = :qty,
                    price = :price, fees = :fees, currency = :ccy, notes = :notes
                WHERE id = :id
            """, id=row["id"], dt=row["trade_date"], side=row["side"],
                qty=row["quantity"], price=row["price"], fees=row["fees"] or 0,
                ccy=row.get("currency"), notes=row.get("notes"))
    except Exception as e:
        errors.append(f"Database error: {e}")
    if errors:
        return banner(" • ".join(errors), "error"), trigger + 1
    return banner(f"Updated {len(valid_rows)} trade(s).", "success"), trigger + 1


@app.callback(
    Output("confirm-delete-pos-trade", "displayed"),
    Output("confirm-delete-pos-trade", "message"),
    Output("positions-banner", "children", allow_duplicate=True),
    Input("pos-trade-delete-btn", "n_clicks"),
    State("position-trades-table", "selected_rows"),
    prevent_initial_call=True,
)
def confirm_delete_position_trades(n, selected):
    if not n:
        return False, no_update, no_update
    if not selected:
        return False, no_update, banner("Select trades first.", "error")
    return True, f"Delete {len(selected)} trade(s)? This cannot be undone.", no_update


@app.callback(
    Output("positions-banner", "children", allow_duplicate=True),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("confirm-delete-pos-trade", "submit_n_clicks"),
    State("position-trades-table", "selected_rows"),
    State("position-trades-table", "data"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def delete_position_trades(submit_n, selected, data, trigger):
    if not submit_n or not selected:
        return no_update, no_update
    ids = [data[i]["id"] for i in selected]
    try:
        with conn() as c:
            for tid in ids:
                c.execute(text("DELETE FROM public.trades WHERE id = :id"), {"id": tid})
        return banner(f"Deleted {len(ids)} trade(s).", "success"), trigger + 1
    except Exception as e:
        return banner(f"Database error: {e}", "error"), no_update


@app.callback(
    Output("positions-banner", "children", allow_duplicate=True),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("pos-close-btn", "n_clicks"),
    State("pos-context", "data"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def close_position(n, ctx, trigger):
    if not n or not ctx:
        return no_update, no_update
    pid = ctx["portfolio_id"]
    exch = ctx["exchange_code"]
    sym = ctx["symbol_code"]
    try:
        qty = Decimal(str(ctx["quantity"]))
    except Exception:
        return banner("Could not parse held quantity.", "error"), no_update
    if qty <= 0:
        return banner("Nothing to close — position is already flat.", "error"), no_update
    # Use latest close price from symbol if available
    px_df = q("""
        SELECT close_price FROM public.symbol
        WHERE exchange_code = :exch AND symbol_code = :sym
    """, exch=exch, sym=sym)
    if px_df.empty or pd.isna(px_df.iloc[0]["close_price"]):
        return banner(
            "No current price available for this symbol; can't auto-close. "
            "Record a SELL manually on the Trades tab.", "error"), no_update
    price = px_df.iloc[0]["close_price"]
    try:
        exec_sql("""
            INSERT INTO public.trades
                (portfolio_id, exchange_code, symbol_code, trade_date, side,
                 quantity, price, fees, notes)
            VALUES (:pid, :exch, :sym, CURRENT_DATE, 'SELL',
                    :qty, :price, 0, :note)
        """, pid=pid, exch=exch, sym=sym, qty=qty, price=price,
            note="Position closed via Positions tab")
        return banner(
            f"Closed position: SELL {qty} {sym} @ {price}.",
            "success"), trigger + 1
    except Exception as e:
        return banner(f"Database error: {e}", "error"), no_update


# ---------------------------------------------------------------------------
# Callbacks — Cash
# ---------------------------------------------------------------------------

@app.callback(
    Output("cash-table-wrap", "children"),
    Input("refresh-trigger", "data"),
    Input("cash-pf-filter", "value"),
    Input("tabs", "value"),
)
def render_cash(_n, pf_id, _tab):
    df = fetch_cash(pf_id) if pf_id else fetch_cash()
    table = dash_table.DataTable(
        id="cash-table",
        data=df.to_dict("records"),
        columns=[
            {"name": "id", "id": "id", "editable": False},
            {"name": "portfolio", "id": "portfolio", "editable": False},
            {"name": "txn_date", "id": "txn_date", "editable": True},
            {"name": "type", "id": "type", "editable": True, "presentation": "dropdown"},
            {"name": "amount", "id": "amount", "editable": True, "type": "numeric"},
            {"name": "currency", "id": "currency", "editable": True},
            {"name": "notes", "id": "notes", "editable": True},
            {"name": "updated_at", "id": "updated_at", "editable": False},
        ],
        dropdown={"type": {"options": CASH_TYPE_OPTS}},
        editable=True,
        row_selectable="multi",
        page_size=20,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "system-ui, sans-serif", "fontSize": "13px", "padding": "6px"},
        style_header={"fontWeight": "bold", "backgroundColor": "#f4f4f4"},
    )
    return table


@app.callback(
    Output("cash-banner", "children"),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("new-ct-submit", "n_clicks"),
    State("new-ct-pf", "value"),
    State("new-ct-type", "value"),
    State("new-ct-date", "date"),
    State("new-ct-amount", "value"),
    State("new-ct-ccy", "value"),
    State("new-ct-notes", "value"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def create_cash(n, pf_id, ttype, date, amount, ccy, notes, trigger):
    if not n:
        return no_update, no_update
    err = validate_cash(pf_id, ttype, date, amount)
    if err:
        return banner(err, "error"), no_update
    try:
        exec_sql("""
            INSERT INTO public.cash_transactions
                (portfolio_id, txn_date, type, amount, currency, notes)
            VALUES (:pid, :dt, :type, :amt, :ccy, :notes)
        """, pid=pf_id, dt=date, type=ttype, amt=amount, ccy=ccy, notes=notes)
        return banner(f"Recorded {ttype} of {amount} {ccy}.", "success"), trigger + 1
    except Exception as e:
        return banner(f"Database error: {e}", "error"), no_update


@app.callback(
    Output("cash-banner", "children", allow_duplicate=True),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("cash-table", "data"),
    State("cash-table", "data_previous"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def edit_cash(data, data_prev, trigger):
    if not data_prev or data == data_prev:
        return no_update, no_update
    by_id_prev = {r["id"]: r for r in data_prev}
    changed = [r for r in data if by_id_prev.get(r["id"]) and by_id_prev[r["id"]] != r]
    if not changed:
        return no_update, no_update
    errors = []
    valid_rows = []
    for row in changed:
        err = validate_cash(row["portfolio_id"], row["type"], row["txn_date"],
                            row["amount"])
        if err:
            errors.append(f"Cash txn #{row['id']}: {err}")
        else:
            valid_rows.append(row)
    try:
        for row in valid_rows:
            exec_sql("""
                UPDATE public.cash_transactions
                SET txn_date = :dt, type = :type, amount = :amt,
                    currency = :ccy, notes = :notes
                WHERE id = :id
            """, id=row["id"], dt=row["txn_date"], type=row["type"],
                amt=row["amount"], ccy=row.get("currency"), notes=row.get("notes"))
    except Exception as e:
        errors.append(f"Database error: {e}")
    if errors:
        return banner(" • ".join(errors), "error"), trigger + 1
    return banner(f"Updated {len(valid_rows)} transaction(s).", "success"), trigger + 1


@app.callback(
    Output("confirm-delete-ct", "displayed"),
    Output("confirm-delete-ct", "message"),
    Output("cash-banner", "children", allow_duplicate=True),
    Input("ct-delete-btn", "n_clicks"),
    State("cash-table", "selected_rows"),
    State("cash-table", "data"),
    prevent_initial_call=True,
)
def confirm_delete_cash(n, selected, data):
    if not n:
        return False, no_update, no_update
    if not selected:
        return False, no_update, banner("Select rows first.", "error")
    return True, f"Delete {len(selected)} cash transaction(s)? This cannot be undone.", no_update


@app.callback(
    Output("cash-banner", "children", allow_duplicate=True),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("confirm-delete-ct", "submit_n_clicks"),
    State("cash-table", "selected_rows"),
    State("cash-table", "data"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def delete_cash(submit_n, selected, data, trigger):
    if not submit_n or not selected:
        return no_update, no_update
    ids = [data[i]["id"] for i in selected]
    try:
        with conn() as c:
            for cid in ids:
                c.execute(text("DELETE FROM public.cash_transactions WHERE id = :id"),
                          {"id": cid})
        return banner(f"Deleted {len(ids)} transaction(s).", "success"), trigger + 1
    except Exception as e:
        return banner(f"Database error: {e}", "error"), no_update


@app.callback(
    Output("cash-banner", "children", allow_duplicate=True),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("ct-bulk-apply", "n_clicks"),
    State("cash-table", "selected_rows"),
    State("cash-table", "data"),
    State("ct-bulk-field", "value"),
    State("ct-bulk-value", "value"),
    State("refresh-trigger", "data"),
    prevent_initial_call=True,
)
def bulk_apply_cash(n, selected, data, field, value, trigger):
    if not n:
        return no_update, no_update
    if not selected:
        return banner("Select rows first.", "error"), no_update
    if not field:
        return banner("Pick a field to set.", "error"), no_update
    if value in (None, ""):
        return banner("Enter a value.", "error"), no_update
    if field == "type" and value not in ("DEPOSIT", "WITHDRAWAL", "DIVIDEND",
                                          "FEE", "INTEREST", "FX_ADJUST"):
        return banner(f"Invalid type: {value!r}.", "error"), no_update
    if field == "currency" and len(str(value)) != 3:
        return banner("Currency must be a 3-letter code.", "error"), no_update

    ids = [data[i]["id"] for i in selected]
    column_sql = {"type": "type", "currency": "currency", "notes": "notes"}[field]
    try:
        with conn() as c:
            for cid in ids:
                c.execute(text(
                    f"UPDATE public.cash_transactions SET {column_sql} = :val WHERE id = :id"),
                    {"val": value, "id": cid})
        return banner(f"Updated {field} on {len(ids)} transaction(s).", "success"), trigger + 1
    except Exception as e:
        return banner(f"Database error: {e}", "error"), no_update


# ---------------------------------------------------------------------------
# Callbacks — Charts
# ---------------------------------------------------------------------------

def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, xref="paper", yref="paper",
                       x=0.5, y=0.5, showarrow=False,
                       font={"size": 14, "color": "#888"})
    fig.update_layout(xaxis={"visible": False}, yaxis={"visible": False},
                      plot_bgcolor="white",
                      margin={"l": 40, "r": 20, "t": 30, "b": 40})
    return fig


@app.callback(
    Output("chart-symbol", "options", allow_duplicate=True),
    Output("chart-symbol", "disabled"),
    Output("chart-symbol", "value"),
    Output("chart-symbol", "placeholder"),
    Input("chart-exchange", "value"),
    prevent_initial_call=True,
)
def cascade_symbols(exchange_code):
    if not exchange_code:
        return [], True, None, "Pick an exchange first"
    opts = fetch_symbol_options_for_exchange(exchange_code)
    placeholder = f"Pick a symbol from {exchange_code}…" if opts \
        else f"No symbols found in {exchange_code}"
    return opts, False, None, placeholder


@app.callback(
    Output("price-chart", "figure"),
    Input("chart-exchange", "value"),
    Input("chart-symbol", "value"),
    Input("chart-date-range", "start_date"),
    Input("chart-date-range", "end_date"),
    Input("chart-pf-overlay", "value"),
    Input("chart-style", "value"),
    Input("chart-ma-overlays", "value"),
)
def render_chart(exch, sym, start_date, end_date, pf_overlay, style, ma_overlays):
    if not exch:
        return _empty_figure("Pick an exchange to begin.")
    if not sym:
        return _empty_figure(f"Pick a symbol from {exch}.")
    df = fetch_daily_quotes(exch, sym, start_date, end_date)
    if df.empty:
        return _empty_figure(
            f"No daily quotes for {exch}:{sym} in this date range. "
            "Make sure symbol_quote has rows with interval_code = 'd'."
        )

    fig = go.Figure()
    if style == "candle":
        fig.add_trace(go.Candlestick(
            x=df["as_of_date"],
            open=df["open_price"], high=df["high_price"],
            low=df["low_price"], close=df["close_price"],
            name=sym, showlegend=False,
        ))
    else:
        fig.add_trace(go.Scatter(
            x=df["as_of_date"], y=df["close_price"],
            mode="lines", name="Close", line={"width": 1.6},
        ))

    # Moving-average overlays (computed from the daily quotes in view)
    if ma_overlays:
        ma_specs = {"ma50": (50, "#1f77b4"), "ma200": (200, "#ff7f0e")}
        for key in ma_overlays:
            if key not in ma_specs:
                continue
            window, color = ma_specs[key]
            ma_series = df["close_price"].astype(float).rolling(window).mean()
            fig.add_trace(go.Scatter(
                x=df["as_of_date"], y=ma_series,
                mode="lines", name=key.upper(),
                line={"width": 1.2, "color": color},
                hovertemplate=f"{key.upper()}: %{{y:.2f}}<extra></extra>",
            ))

    # Overlay trade markers if a portfolio is picked
    if pf_overlay:
        trades = fetch_trade_markers(pf_overlay, exch, sym)
        if not trades.empty:
            buys = trades[trades["side"] == "BUY"]
            sells = trades[trades["side"] == "SELL"]
            if not buys.empty:
                fig.add_trace(go.Scatter(
                    x=buys["trade_date"], y=buys["price"],
                    mode="markers", name="Buy",
                    marker={"symbol": "triangle-up", "size": 12,
                            "color": "#0a0",
                            "line": {"width": 1, "color": "#040"}},
                    hovertemplate="BUY %{customdata} @ %{y}<br>%{x}<extra></extra>",
                    customdata=buys["quantity"],
                ))
            if not sells.empty:
                fig.add_trace(go.Scatter(
                    x=sells["trade_date"], y=sells["price"],
                    mode="markers", name="Sell",
                    marker={"symbol": "triangle-down", "size": 12,
                            "color": "#c00",
                            "line": {"width": 1, "color": "#400"}},
                    hovertemplate="SELL %{customdata} @ %{y}<br>%{x}<extra></extra>",
                    customdata=sells["quantity"],
                ))

    fig.update_layout(
        title=f"{exch}:{sym} — daily",
        xaxis_title=None, yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        plot_bgcolor="white",
        hovermode="x unified",
        margin={"l": 50, "r": 20, "t": 50, "b": 40},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02,
                "xanchor": "right", "x": 1},
    )
    fig.update_xaxes(showgrid=True, gridcolor="#eee")
    fig.update_yaxes(showgrid=True, gridcolor="#eee")
    return fig


@app.callback(
    Output("profile-panel", "children"),
    Output("fundamental-panel", "children"),
    Output("technical-panel", "children"),
    Input("chart-exchange", "value"),
    Input("chart-symbol", "value"),
)
def render_info_panels(exch, sym):
    if not exch or not sym:
        empty = html.Div()
        return empty, empty, empty
    profile = fetch_profile(exch, sym)
    fundamental = fetch_fundamental(exch, sym)
    technical = fetch_technical(exch, sym)
    return (render_profile_panel(profile),
            render_fundamental_panel(fundamental),
            render_technical_panel(technical))


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    debug = os.getenv("DASH_DEBUG", "true").lower() == "true"
    port = int(os.getenv("DASH_PORT", "8050"))
    app.run(debug=debug, port=port, host="0.0.0.0")
