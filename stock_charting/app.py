"""
Stock Charting Application
A Plotly Dash application for visualizing stock data from PostgreSQL database.
"""

import os
from datetime import date, timedelta

import dash
from dash import dcc, html, Input, Output, State, callback, dash_table, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from db import Database

# ---------------------------------------------------------------------------
# App initialization
# ---------------------------------------------------------------------------
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY, dbc.icons.BOOTSTRAP],
    suppress_callback_exceptions=True,
    title="Stock Charting",
)
server = app.server  # For deployment (gunicorn etc.)

db = Database()

# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------
INTERVAL_OPTIONS = [
    {"label": "Daily",     "value": "d"},
    {"label": "Weekly",    "value": "w"},
    {"label": "Monthly",   "value": "m"},
    {"label": "Quarterly", "value": "q"},
    {"label": "Yearly",    "value": "y"},
    {"label": "1 min",     "value": "1"},
    {"label": "5 min",     "value": "5"},
    {"label": "15 min",    "value": "15"},
    {"label": "30 min",    "value": "30"},
    {"label": "Hourly",    "value": "h"},
]

CHART_TYPE_OPTIONS = [
    {"label": "Candlestick", "value": "candlestick"},
    {"label": "OHLC",        "value": "ohlc"},
    {"label": "Line",        "value": "line"},
    {"label": "Area",        "value": "area"},
]

OVERLAY_INDICATORS = [
    {"label": "SMA 20",  "value": "ma20"},
    {"label": "SMA 50",  "value": "ma50"},
    {"label": "SMA 200", "value": "ma200"},
    {"label": "EMA 20",  "value": "ema20"},
    {"label": "EMA 50",  "value": "ema50"},
    {"label": "Bollinger Bands (20)", "value": "bb20"},
    {"label": "Parabolic SAR", "value": "sar"},
]

OSCILLATORS = [
    {"label": "RSI (14)",  "value": "rsi14"},
    {"label": "MACD",      "value": "macd"},
    {"label": "Stochastic (14, full)", "value": "sto14_full"},
    {"label": "CCI",       "value": "cci"},
    {"label": "Williams %R (14)", "value": "wpr14"},
]


def build_sidebar():
    """Left-side control panel."""
    return dbc.Card(
        [
            dbc.CardHeader(html.H5([html.I(className="bi bi-sliders me-2"), "Controls"])),
            dbc.CardBody(
                [
                    html.Label("Exchange", className="fw-bold"),
                    dcc.Dropdown(
                        id="exchange-dropdown",
                        placeholder="Select exchange...",
                        clearable=False,
                    ),
                    html.Br(),

                    html.Label("Symbol", className="fw-bold"),
                    dcc.Dropdown(
                        id="symbol-dropdown",
                        placeholder="Select symbol...",
                        clearable=False,
                    ),
                    html.Br(),

                    html.Label("Interval", className="fw-bold"),
                    dcc.Dropdown(
                        id="interval-dropdown",
                        options=INTERVAL_OPTIONS,
                        value="d",
                        clearable=False,
                    ),
                    html.Br(),

                    html.Label("Date Range", className="fw-bold"),
                    dcc.DatePickerRange(
                        id="date-range",
                        start_date=date.today() - timedelta(days=365),
                        end_date=date.today(),
                        display_format="YYYY-MM-DD",
                        className="w-100",
                    ),
                    html.Br(), html.Br(),

                    html.Label("Chart Type", className="fw-bold"),
                    dcc.Dropdown(
                        id="chart-type",
                        options=CHART_TYPE_OPTIONS,
                        value="candlestick",
                        clearable=False,
                    ),
                    html.Br(),

                    html.Label("Overlay Indicators", className="fw-bold"),
                    dcc.Dropdown(
                        id="overlay-indicators",
                        options=OVERLAY_INDICATORS,
                        multi=True,
                        placeholder="Add moving averages, bands...",
                    ),
                    html.Br(),

                    html.Label("Oscillator", className="fw-bold"),
                    dcc.Dropdown(
                        id="oscillator",
                        options=OSCILLATORS,
                        placeholder="Add an oscillator panel...",
                    ),
                    html.Br(),

                    dbc.Checklist(
                        id="volume-toggle",
                        options=[{"label": "Show Volume", "value": "show"}],
                        value=["show"],
                        switch=True,
                    ),
                    html.Br(),

                    dbc.Checklist(
                        id="log-toggle",
                        options=[{"label": "Log Scale", "value": "log"}],
                        value=[],
                        switch=True,
                    ),
                    html.Br(),

                    dbc.Button(
                        [html.I(className="bi bi-arrow-clockwise me-2"), "Refresh"],
                        id="refresh-btn",
                        color="primary",
                        className="w-100",
                    ),
                ]
            ),
        ],
        className="h-100",
    )


def build_header_stats():
    """Price-at-a-glance header strip (populated by callbacks)."""
    return dbc.Card(
        dbc.CardBody(id="header-stats", children=[
            html.H5("Select an exchange and symbol to begin.", className="text-muted mb-0")
        ]),
        className="mb-3",
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
app.layout = dbc.Container(
    [
        dbc.Row(
            dbc.Col(
                html.Div(
                    [
                        html.H2(
                            [html.I(className="bi bi-graph-up-arrow me-2"), "Stock Charting"],
                            className="d-inline-block",
                        ),
                        html.Span(
                            "Plotly Dash + PostgreSQL",
                            className="text-muted ms-3",
                        ),
                    ],
                    className="py-3 border-bottom mb-3",
                )
            )
        ),
        dbc.Row(
            [
                dbc.Col(build_sidebar(), width=12, lg=3),
                dbc.Col(
                    [
                        build_header_stats(),
                        dbc.Tabs(
                            [
                                dbc.Tab(
                                    dcc.Loading(dcc.Graph(id="price-chart", style={"height": "700px"})),
                                    label="Chart",
                                    tab_id="tab-chart",
                                ),
                                dbc.Tab(
                                    dcc.Loading(html.Div(id="fundamentals-panel", className="p-3")),
                                    label="Fundamentals",
                                    tab_id="tab-fundamentals",
                                ),
                                dbc.Tab(
                                    dcc.Loading(html.Div(id="profile-panel", className="p-3")),
                                    label="Profile",
                                    tab_id="tab-profile",
                                ),
                                dbc.Tab(
                                    dcc.Loading(html.Div(id="data-panel", className="p-3")),
                                    label="Data",
                                    tab_id="tab-data",
                                ),
                            ],
                            id="tabs",
                            active_tab="tab-chart",
                        ),
                    ],
                    width=12, lg=9,
                ),
            ]
        ),
        html.Footer(
            html.P(
                "Data source: PostgreSQL (public schema). Built with Plotly Dash.",
                className="text-muted text-center small mt-4",
            )
        ),
    ],
    fluid=True,
    className="px-4",
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@callback(
    Output("exchange-dropdown", "options"),
    Output("exchange-dropdown", "value"),
    Input("refresh-btn", "n_clicks"),
)
def populate_exchanges(_n):
    """Populate the exchange dropdown on initial load / refresh."""
    exchanges = db.list_exchanges()
    if not exchanges:
        return [], None
    options = [
        {"label": f"{row['exchange_code']} — {row['exchange_name']}", "value": row["exchange_code"]}
        for row in exchanges
    ]
    return options, options[0]["value"]


@callback(
    Output("symbol-dropdown", "options"),
    Output("symbol-dropdown", "value"),
    Input("exchange-dropdown", "value"),
)
def populate_symbols(exchange_code):
    if not exchange_code:
        return [], None
    symbols = db.list_symbols(exchange_code)
    options = [
        {"label": f"{row['symbol_code']} — {row['name']}", "value": row["symbol_code"]}
        for row in symbols
    ]
    default = options[0]["value"] if options else None
    return options, default


@callback(
    Output("header-stats", "children"),
    Input("exchange-dropdown", "value"),
    Input("symbol-dropdown", "value"),
)
def update_header_stats(exchange, symbol):
    if not (exchange and symbol):
        return html.H5("Select an exchange and symbol to begin.", className="text-muted mb-0")

    snap = db.get_symbol_snapshot(exchange, symbol)
    if not snap:
        return html.H5(f"{symbol} — no snapshot data.", className="text-muted mb-0")

    change = snap.get("change_amount")
    close = snap.get("close_price")
    prev = snap.get("previous_price")
    pct = None
    if change is not None and prev not in (None, 0):
        pct = float(change) / float(prev) * 100.0

    change_color = "text-success" if (change is not None and float(change) >= 0) else "text-danger"
    arrow = "bi-caret-up-fill" if (change is not None and float(change) >= 0) else "bi-caret-down-fill"

    def stat(label, value):
        return dbc.Col(
            html.Div([
                html.Div(label, className="text-muted small"),
                html.Div(value, className="fw-bold fs-5"),
            ]),
            xs=6, md=3, lg=2,
        )

    return dbc.Row(
        [
            dbc.Col(
                html.Div([
                    html.Div(snap.get("name") or symbol, className="fw-bold fs-4"),
                    html.Div(f"{exchange}:{symbol}", className="text-muted small"),
                ]),
                xs=12, md=4,
            ),
            stat("Close", f"{close:.4f}" if close is not None else "—"),
            stat(
                "Change",
                html.Span(
                    [
                        html.I(className=f"bi {arrow} me-1"),
                        f"{float(change):.4f}" + (f" ({pct:+.2f}%)" if pct is not None else ""),
                    ],
                    className=change_color,
                ) if change is not None else "—",
            ),
            stat("Volume", f"{int(snap['volume']):,}" if snap.get("volume") is not None else "—"),
            stat("Bid / Ask",
                 f"{snap['bid_price']:.4f} / {snap['ask_price']:.4f}"
                 if snap.get("bid_price") is not None and snap.get("ask_price") is not None else "—"),
            stat("As of", str(snap.get("as_of_date")) if snap.get("as_of_date") else "—"),
        ],
        align="center",
    )


@callback(
    Output("price-chart", "figure"),
    Input("exchange-dropdown", "value"),
    Input("symbol-dropdown", "value"),
    Input("interval-dropdown", "value"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
    Input("chart-type", "value"),
    Input("overlay-indicators", "value"),
    Input("oscillator", "value"),
    Input("volume-toggle", "value"),
    Input("log-toggle", "value"),
)
def update_chart(exchange, symbol, interval, start_date, end_date,
                 chart_type, overlays, oscillator, volume_toggle, log_toggle):
    if not (exchange and symbol):
        return _empty_figure("Select an exchange and symbol to load a chart.")

    df = db.get_quotes(exchange, symbol, interval, start_date, end_date)
    if df.empty:
        return _empty_figure(f"No quote data for {symbol} on {exchange} in the selected range.")

    tech_df = db.get_technicals(exchange, symbol, start_date, end_date)

    show_volume = "show" in (volume_toggle or [])
    show_oscillator = bool(oscillator)

    # Determine row layout.
    rows = 1
    row_heights = [1.0]
    if show_volume:
        rows += 1
        row_heights = [0.7, 0.3] if rows == 2 else row_heights
    if show_oscillator:
        rows += 1
        if rows == 2:
            row_heights = [0.7, 0.3]
        elif rows == 3:
            row_heights = [0.6, 0.2, 0.2]

    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
    )

    # --- Price pane ---
    price_row = 1
    _add_price_trace(fig, df, chart_type, row=price_row)
    _add_overlays(fig, df, tech_df, overlays or [], row=price_row)

    # --- Volume pane ---
    if show_volume:
        vol_row = 2
        colors = [
            "rgba(38,166,154,0.6)" if c >= o else "rgba(239,83,80,0.6)"
            for o, c in zip(df["open_price"].fillna(0), df["close_price"].fillna(0))
        ]
        fig.add_trace(
            go.Bar(x=df["as_of_date"], y=df["volume"], name="Volume",
                   marker_color=colors, showlegend=False),
            row=vol_row, col=1,
        )
        fig.update_yaxes(title_text="Volume", row=vol_row, col=1)

    # --- Oscillator pane ---
    if show_oscillator:
        osc_row = rows
        _add_oscillator(fig, tech_df, oscillator, row=osc_row)

    # Log scale toggle (price pane only)
    if "log" in (log_toggle or []):
        fig.update_yaxes(type="log", row=price_row, col=1)

    fig.update_layout(
        template="plotly_white",
        margin=dict(l=40, r=20, t=30, b=40),
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=700,
    )
    fig.update_yaxes(title_text="Price", row=price_row, col=1)
    fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor")

    return fig


def _add_price_trace(fig, df, chart_type, row):
    if chart_type == "candlestick":
        fig.add_trace(
            go.Candlestick(
                x=df["as_of_date"],
                open=df["open_price"], high=df["high_price"],
                low=df["low_price"], close=df["close_price"],
                name="Price",
                increasing_line_color="#26a69a",
                decreasing_line_color="#ef5350",
            ),
            row=row, col=1,
        )
    elif chart_type == "ohlc":
        fig.add_trace(
            go.Ohlc(
                x=df["as_of_date"],
                open=df["open_price"], high=df["high_price"],
                low=df["low_price"], close=df["close_price"],
                name="Price",
            ),
            row=row, col=1,
        )
    elif chart_type == "area":
        fig.add_trace(
            go.Scatter(
                x=df["as_of_date"], y=df["close_price"],
                mode="lines", name="Close",
                fill="tozeroy",
                line=dict(color="#1f77b4", width=2),
            ),
            row=row, col=1,
        )
    else:  # line
        fig.add_trace(
            go.Scatter(
                x=df["as_of_date"], y=df["close_price"],
                mode="lines", name="Close",
                line=dict(color="#1f77b4", width=2),
            ),
            row=row, col=1,
        )


def _add_overlays(fig, df, tech_df, overlays, row):
    if tech_df.empty or not overlays:
        return

    line_defs = {
        "ma20":  ("SMA 20",  "ma20",  "#ff9800"),
        "ma50":  ("SMA 50",  "ma50",  "#9c27b0"),
        "ma200": ("SMA 200", "ma200", "#607d8b"),
        "ema20": ("EMA 20",  "ema20", "#2196f3"),
        "ema50": ("EMA 50",  "ema50", "#009688"),
        "sar":   ("SAR",     "sar",   "#795548"),
    }

    for key in overlays:
        if key in line_defs:
            label, col, color = line_defs[key]
            if col in tech_df.columns:
                mode = "markers" if key == "sar" else "lines"
                fig.add_trace(
                    go.Scatter(
                        x=tech_df["as_of_date"], y=tech_df[col],
                        mode=mode, name=label,
                        line=dict(color=color, width=1.5),
                        marker=dict(size=3),
                    ),
                    row=row, col=1,
                )
        elif key == "bb20":
            if {"upper_bb20", "lower_bb20"}.issubset(tech_df.columns):
                fig.add_trace(
                    go.Scatter(
                        x=tech_df["as_of_date"], y=tech_df["upper_bb20"],
                        mode="lines", name="BB Upper",
                        line=dict(color="rgba(100,100,100,0.6)", width=1, dash="dot"),
                    ),
                    row=row, col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=tech_df["as_of_date"], y=tech_df["lower_bb20"],
                        mode="lines", name="BB Lower",
                        line=dict(color="rgba(100,100,100,0.6)", width=1, dash="dot"),
                        fill="tonexty",
                        fillcolor="rgba(100,100,100,0.08)",
                    ),
                    row=row, col=1,
                )


def _add_oscillator(fig, tech_df, oscillator, row):
    if tech_df.empty:
        return

    if oscillator == "rsi14" and "rsi14" in tech_df.columns:
        fig.add_trace(
            go.Scatter(x=tech_df["as_of_date"], y=tech_df["rsi14"],
                       mode="lines", name="RSI(14)",
                       line=dict(color="#8e24aa", width=1.5)),
            row=row, col=1,
        )
        fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5, row=row, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, row=row, col=1)
        fig.update_yaxes(title_text="RSI", range=[0, 100], row=row, col=1)

    elif oscillator == "macd" and "macd" in tech_df.columns:
        fig.add_trace(
            go.Scatter(x=tech_df["as_of_date"], y=tech_df["macd"],
                       mode="lines", name="MACD",
                       line=dict(color="#3f51b5", width=1.5)),
            row=row, col=1,
        )
        fig.add_hline(y=0, line_color="gray", opacity=0.5, row=row, col=1)
        fig.update_yaxes(title_text="MACD", row=row, col=1)

    elif oscillator == "sto14_full" and "sto14_full" in tech_df.columns:
        fig.add_trace(
            go.Scatter(x=tech_df["as_of_date"], y=tech_df["sto14_full"],
                       mode="lines", name="Stoch %D",
                       line=dict(color="#00897b", width=1.5)),
            row=row, col=1,
        )
        fig.add_hline(y=80, line_dash="dash", line_color="red", opacity=0.5, row=row, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color="green", opacity=0.5, row=row, col=1)
        fig.update_yaxes(title_text="Stoch", range=[0, 100], row=row, col=1)

    elif oscillator == "cci" and "cci" in tech_df.columns:
        fig.add_trace(
            go.Scatter(x=tech_df["as_of_date"], y=tech_df["cci"],
                       mode="lines", name="CCI",
                       line=dict(color="#e53935", width=1.5)),
            row=row, col=1,
        )
        fig.add_hline(y=100, line_dash="dash", line_color="red", opacity=0.5, row=row, col=1)
        fig.add_hline(y=-100, line_dash="dash", line_color="green", opacity=0.5, row=row, col=1)
        fig.update_yaxes(title_text="CCI", row=row, col=1)

    elif oscillator == "wpr14" and "wpr14" in tech_df.columns:
        fig.add_trace(
            go.Scatter(x=tech_df["as_of_date"], y=tech_df["wpr14"],
                       mode="lines", name="Williams %R",
                       line=dict(color="#fb8c00", width=1.5)),
            row=row, col=1,
        )
        fig.add_hline(y=-20, line_dash="dash", line_color="red", opacity=0.5, row=row, col=1)
        fig.add_hline(y=-80, line_dash="dash", line_color="green", opacity=0.5, row=row, col=1)
        fig.update_yaxes(title_text="W%R", range=[-100, 0], row=row, col=1)


def _empty_figure(message):
    fig = go.Figure()
    fig.update_layout(
        template="plotly_white",
        height=700,
        annotations=[dict(
            text=message, x=0.5, y=0.5, xref="paper", yref="paper",
            showarrow=False, font=dict(size=16, color="gray"),
        )],
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


# --- Fundamentals tab --------------------------------------------------------
@callback(
    Output("fundamentals-panel", "children"),
    Input("exchange-dropdown", "value"),
    Input("symbol-dropdown", "value"),
)
def update_fundamentals(exchange, symbol):
    if not (exchange and symbol):
        return dbc.Alert("Select an exchange and symbol to view fundamentals.", color="secondary")

    data = db.get_fundamentals(exchange, symbol)
    if not data:
        return dbc.Alert(f"No fundamentals available for {symbol}.", color="warning")

    # Curated groupings
    groups = {
        "Valuation": [
            ("Market Cap", "market_capitalization"),
            ("P/E (Trailing)", "trailing_pe"),
            ("P/E (Forward)", "forward_pe"),
            ("PEG", "peg"),
            ("P/S", "price_to_sales"),
            ("P/B", "price_to_book"),
            ("Beta", "beta"),
        ],
        "Per Share": [
            ("EPS", "earnings_per_share"),
            ("Revenue / Share", "revenue_per_share"),
            ("Book Value / Share", "book_value_per_share"),
            ("Dividend / Share", "dividend_per_share"),
            ("Dividend Yield", "dividend_yield"),
            ("Total Cash / Share", "total_cash_per_share"),
        ],
        "Profitability": [
            ("Gross Margin", "gross_margin"),
            ("Operating Margin", "operating_margin"),
            ("Profit Margin", "profit_margin"),
            ("Return on Assets", "return_on_assets"),
            ("Return on Equity", "return_on_equity"),
            ("EBITDA", "ebitda"),
        ],
        "Balance Sheet": [
            ("Revenue", "revenue"),
            ("Gross Profit", "gross_profit"),
            ("Total Cash", "total_cash"),
            ("Total Debt", "total_debt"),
            ("Debt / Equity", "total_debt_to_equity"),
            ("Book Value", "book_value"),
            ("Shares Outstanding", "shares_outstanding"),
            ("Dividend Date", "dividend_date"),
        ],
    }

    cards = []
    for group_name, items in groups.items():
        rows = []
        for label, key in items:
            val = data.get(key)
            rows.append(
                html.Tr([
                    html.Td(label, className="text-muted"),
                    html.Td(_fmt(val), className="text-end fw-semibold"),
                ])
            )
        cards.append(
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader(html.Strong(group_name)),
                    dbc.CardBody(dbc.Table(html.Tbody(rows), borderless=True, size="sm", className="mb-0")),
                ], className="mb-3 h-100"),
                xs=12, md=6, lg=6,
            )
        )

    return dbc.Row(cards)


def _fmt(val):
    if val is None:
        return "—"
    if isinstance(val, (int,)):
        return f"{val:,}"
    if isinstance(val, float):
        # Avoid scientific notation for normal numbers.
        if abs(val) >= 1000:
            return f"{val:,.2f}"
        return f"{val:.4f}".rstrip("0").rstrip(".")
    return str(val)


# --- Profile tab -------------------------------------------------------------
@callback(
    Output("profile-panel", "children"),
    Input("exchange-dropdown", "value"),
    Input("symbol-dropdown", "value"),
)
def update_profile(exchange, symbol):
    if not (exchange and symbol):
        return dbc.Alert("Select an exchange and symbol to view the profile.", color="secondary")

    prof = db.get_profile(exchange, symbol)
    if not prof:
        return dbc.Alert(f"No profile data for {symbol}.", color="warning")

    def row(label, value):
        if not value:
            return None
        return html.Tr([
            html.Td(label, className="text-muted", style={"width": "180px"}),
            html.Td(value),
        ])

    meta_rows = [r for r in [
        row("Name",     prof.get("name")),
        row("Type",     prof.get("type")),
        row("Sector",   prof.get("sector")),
        row("Industry", prof.get("industry")),
        row("Country",  prof.get("country")),
        row("Currency", prof.get("currency")),
        row("ISIN",     prof.get("isin")),
        row("CUSIP",    prof.get("cusip")),
        row("CIK",      prof.get("cik")),
        row("LEI",      prof.get("lei")),
        row("FIGI",     prof.get("figi")),
    ] if r is not None]

    contact_rows = [r for r in [
        row("Address", prof.get("address")),
        row("Phone",   prof.get("phone")),
        row("Website",
            html.A(prof["website"], href=prof["website"], target="_blank") if prof.get("website") else None),
    ] if r is not None]

    description = prof.get("description") or prof.get("about")

    return html.Div([
        html.H4(f"{prof.get('name', symbol)} ({exchange}:{symbol})"),
        html.Hr(),
        dbc.Row([
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader(html.Strong("Identity")),
                    dbc.CardBody(dbc.Table(html.Tbody(meta_rows), borderless=True, size="sm", className="mb-0")),
                ]),
                xs=12, md=6,
            ),
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader(html.Strong("Contact")),
                    dbc.CardBody(dbc.Table(html.Tbody(contact_rows), borderless=True, size="sm", className="mb-0")
                                 if contact_rows else html.Span("—", className="text-muted")),
                ]),
                xs=12, md=6,
            ),
        ], className="mb-3"),
        dbc.Card([
            dbc.CardHeader(html.Strong("Description")),
            dbc.CardBody(html.P(description) if description else html.Span("No description available.",
                                                                           className="text-muted")),
        ]),
    ])


# --- Data tab ----------------------------------------------------------------
@callback(
    Output("data-panel", "children"),
    Input("exchange-dropdown", "value"),
    Input("symbol-dropdown", "value"),
    Input("interval-dropdown", "value"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
)
def update_data_table(exchange, symbol, interval, start_date, end_date):
    if not (exchange and symbol):
        return dbc.Alert("Select an exchange and symbol to view data.", color="secondary")

    df = db.get_quotes(exchange, symbol, interval, start_date, end_date)
    if df.empty:
        return dbc.Alert("No data in this range.", color="warning")

    display_df = df.copy().sort_values("as_of_date", ascending=False)
    display_df["as_of_date"] = display_df["as_of_date"].astype(str)

    columns = [
        {"name": "Date",      "id": "as_of_date"},
        {"name": "Open",      "id": "open_price",  "type": "numeric", "format": {"specifier": ",.4f"}},
        {"name": "High",      "id": "high_price",  "type": "numeric", "format": {"specifier": ",.4f"}},
        {"name": "Low",       "id": "low_price",   "type": "numeric", "format": {"specifier": ",.4f"}},
        {"name": "Close",     "id": "close_price", "type": "numeric", "format": {"specifier": ",.4f"}},
        {"name": "Adj Close", "id": "adjusted_close", "type": "numeric", "format": {"specifier": ",.4f"}},
        {"name": "Volume",    "id": "volume",      "type": "numeric", "format": {"specifier": ","}},
        {"name": "Change",    "id": "change_amount", "type": "numeric", "format": {"specifier": ",.4f"}},
    ]
    columns = [c for c in columns if c["id"] in display_df.columns]

    return dash_table.DataTable(
        data=display_df.to_dict("records"),
        columns=columns,
        page_size=25,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_header={"backgroundColor": "#f8f9fa", "fontWeight": "bold"},
        style_cell={"padding": "6px 10px", "fontFamily": "system-ui, sans-serif"},
        style_data_conditional=[
            {"if": {"filter_query": "{change_amount} > 0", "column_id": "change_amount"},
             "color": "#2e7d32"},
            {"if": {"filter_query": "{change_amount} < 0", "column_id": "change_amount"},
             "color": "#c62828"},
        ],
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(
        debug=os.getenv("DASH_DEBUG", "True").lower() == "true",
        host=os.getenv("DASH_HOST", "127.0.0.1"),
        port=int(os.getenv("DASH_PORT", "8050")),
    )
