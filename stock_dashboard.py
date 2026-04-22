"""
Stock Dashboard - Streamlit app for visualizing stock data from PostgreSQL
Requirements: pip install streamlit plotly pandas sqlalchemy psycopg2-binary
Run with: streamlit run stock_dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import create_engine, text
import warnings
warnings.filterwarnings("ignore")

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=DM+Sans:wght@300;400;600&display=swap');

  html, body, [class*="css"] {
      font-family: 'DM Sans', sans-serif;
  }
  h1, h2, h3 { font-family: 'IBM Plex Mono', monospace; }

  .block-container { padding-top: 1.5rem; }

  /* Metric cards */
  [data-testid="metric-container"] {
      background: #0f1117;
      border: 1px solid #1e2530;
      border-radius: 8px;
      padding: 12px 16px;
  }
  [data-testid="metric-container"] label { color: #6b7a99 !important; font-size: 0.75rem; }
  [data-testid="metric-container"] [data-testid="stMetricValue"] { font-family: 'IBM Plex Mono', monospace; font-size: 1.3rem; }

  .stSelectbox label, .stMultiSelect label { color: #aab4cc; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; }

  .symbol-pill {
      display: inline-block; background: #1a2035; border: 1px solid #2a3550;
      border-radius: 4px; padding: 2px 10px; font-family: 'IBM Plex Mono', monospace;
      font-size: 0.85rem; color: #7eb8f7; margin-right: 6px;
  }
  .sector-tag {
      font-size: 0.75rem; color: #6b7a99; background: #0d1220;
      border-radius: 3px; padding: 2px 8px; display: inline-block;
  }
  .divider { border-top: 1px solid #1e2530; margin: 12px 0; }
  .stApp { background-color: #080c14; }
</style>
""", unsafe_allow_html=True)

# ─── DB Connection ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_engine(conn_str: str):
    return create_engine(conn_str)

# ─── Data Loaders ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_exchanges(_engine):
    return pd.read_sql("SELECT exchange_code, exchange_name FROM public.exchanges ORDER BY exchange_code", _engine)

@st.cache_data(ttl=300)
def load_symbols(_engine, exchange_code: str):
    q = text("""
        SELECT sp.symbol_code, sp.name, sp.sector, sp.industry
        FROM public.symbol_profile sp
        WHERE sp.exchange_code = :ex
        ORDER BY sp.symbol_code
    """)
    return pd.read_sql(q, _engine, params={"ex": exchange_code})

@st.cache_data(ttl=60)
def load_quote_data(_engine, exchange_code: str, symbol_code: str, interval_code: str, date_from, date_to):
    q = text("""
        SELECT as_of_date, open_price, high_price, low_price, close_price,
               adjusted_close, volume, bid_price, ask_price, change_amount
        FROM public.symbol_quote
        WHERE exchange_code = :ex
          AND symbol_code   = :sym
          AND interval_code = :ivl
          AND as_of_date BETWEEN :d1 AND :d2
        ORDER BY as_of_date ASC
    """)
    return pd.read_sql(q, _engine, params={"ex": exchange_code, "sym": symbol_code,
                                            "ivl": interval_code, "d1": date_from, "d2": date_to})

@st.cache_data(ttl=300)
def load_technicals(_engine, exchange_code: str, symbol_code: str, as_of_date):
    q = text("""
        SELECT * FROM public.symbol_technical
        WHERE exchange_code = :ex AND symbol_code = :sym AND as_of_date = :d
    """)
    df = pd.read_sql(q, _engine, params={"ex": exchange_code, "sym": symbol_code, "d": as_of_date})
    return df.iloc[0] if not df.empty else None

@st.cache_data(ttl=300)
def load_fundamentals(_engine, exchange_code: str, symbol_code: str):
    q = text("""
        SELECT * FROM public.symbol_fundamental
        WHERE exchange_code = :ex AND symbol_code = :sym
    """)
    df = pd.read_sql(q, _engine, params={"ex": exchange_code, "sym": symbol_code})
    return df.iloc[0] if not df.empty else None

@st.cache_data(ttl=300)
def load_profile(_engine, exchange_code: str, symbol_code: str):
    q = text("""
        SELECT * FROM public.symbol_profile
        WHERE exchange_code = :ex AND symbol_code = :sym
    """)
    df = pd.read_sql(q, _engine, params={"ex": exchange_code, "sym": symbol_code})
    return df.iloc[0] if not df.empty else None

@st.cache_data(ttl=60)
def load_latest_price(_engine, exchange_code: str, symbol_code: str):
    q = text("""
        SELECT close_price, change_amount, as_of_date
        FROM public.symbol
        WHERE exchange_code = :ex AND symbol_code = :sym
    """)
    df = pd.read_sql(q, _engine, params={"ex": exchange_code, "sym": symbol_code})
    return df.iloc[0] if not df.empty else None

# ─── Chart Builder ─────────────────────────────────────────────────────────────
CHART_THEME = dict(
    paper_bgcolor="#080c14",
    plot_bgcolor="#080c14",
    font=dict(family="IBM Plex Mono, monospace", color="#8899bb", size=11),
    gridcolor="#111827",
    zerolinecolor="#1e2a3a",
)

def build_main_chart(df: pd.DataFrame, symbol: str, chart_type: str,
                     show_volume: bool, overlays: list, tech_row=None) -> go.Figure:
    rows = 2 if show_volume else 1
    row_heights = [0.75, 0.25] if show_volume else [1.0]
    specs = [[{"secondary_y": True}]] + ([[{"secondary_y": False}]] if show_volume else [])

    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03, row_heights=row_heights, specs=specs)

    color_up, color_dn = "#26c96f", "#ef4444"

    # Main price chart
    if chart_type == "Candlestick":
        fig.add_trace(go.Candlestick(
            x=df["as_of_date"],
            open=df["open_price"], high=df["high_price"],
            low=df["low_price"], close=df["close_price"],
            name=symbol,
            increasing_line_color=color_up, decreasing_line_color=color_dn,
            increasing_fillcolor=color_up, decreasing_fillcolor=color_dn,
        ), row=1, col=1)
    elif chart_type == "OHLC":
        fig.add_trace(go.Ohlc(
            x=df["as_of_date"],
            open=df["open_price"], high=df["high_price"],
            low=df["low_price"], close=df["close_price"],
            name=symbol,
            increasing_line_color=color_up, decreasing_line_color=color_dn,
        ), row=1, col=1)
    else:  # Line
        use_col = "adjusted_close" if "adjusted_close" in df.columns and df["adjusted_close"].notna().any() else "close_price"
        fig.add_trace(go.Scatter(
            x=df["as_of_date"], y=df[use_col],
            name=symbol, mode="lines",
            line=dict(color="#7eb8f7", width=2),
            fill="tozeroy", fillcolor="rgba(126,184,247,0.06)",
        ), row=1, col=1)

    # MA overlays from symbol_quote (computed on-the-fly if tech row not available)
    ma_colors = {"MA 20": "#f59e0b", "MA 50": "#a78bfa", "MA 200": "#34d399"}
    ma_windows = {"MA 20": 20, "MA 50": 50, "MA 200": 200}
    for label in overlays:
        if label in ma_windows:
            w = ma_windows[label]
            series = df["close_price"].rolling(w).mean()
            fig.add_trace(go.Scatter(
                x=df["as_of_date"], y=series, name=label, mode="lines",
                line=dict(color=ma_colors[label], width=1.2, dash="dot"),
            ), row=1, col=1)

    # Bollinger Bands (if requested and we have enough data)
    if "Bollinger Bands" in overlays and len(df) >= 20:
        mid = df["close_price"].rolling(20).mean()
        std = df["close_price"].rolling(20).std()
        upper, lower = mid + 2 * std, mid - 2 * std
        for y, name in [(upper, "BB Upper"), (lower, "BB Lower")]:
            fig.add_trace(go.Scatter(
                x=df["as_of_date"], y=y, name=name, mode="lines",
                line=dict(color="#64748b", width=1, dash="dash"),
            ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=list(df["as_of_date"]) + list(df["as_of_date"])[::-1],
            y=list(upper) + list(lower)[::-1],
            fill="toself", fillcolor="rgba(100,116,139,0.06)",
            line=dict(color="rgba(0,0,0,0)"), name="BB Band", showlegend=False,
        ), row=1, col=1)

    # Volume bars
    if show_volume:
        colors = [color_up if c >= o else color_dn
                  for c, o in zip(df["close_price"], df["open_price"])]
        fig.add_trace(go.Bar(
            x=df["as_of_date"], y=df["volume"], name="Volume",
            marker_color=colors, opacity=0.6, showlegend=False,
        ), row=2, col=1)

    fig.update_layout(
        paper_bgcolor=CHART_THEME["paper_bgcolor"],
        plot_bgcolor=CHART_THEME["plot_bgcolor"],
        font=CHART_THEME["font"],
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        margin=dict(l=0, r=0, t=10, b=0),
        hovermode="x unified",
    )
    for ax in ["xaxis", "xaxis2", "yaxis", "yaxis2"]:
        fig.update_layout(**{ax: dict(
            gridcolor=CHART_THEME["gridcolor"],
            zerolinecolor=CHART_THEME["zerolinecolor"],
            showgrid=True,
        )})
    return fig


def build_indicator_chart(df: pd.DataFrame, indicator: str) -> go.Figure:
    fig = go.Figure()
    color = "#7eb8f7"

    if indicator == "RSI (14)":
        rsi = df["close_price"].ewm(com=13, adjust=False).mean()  # simplified
        # Use actual RSI if available in technical table
        fig.add_hline(y=70, line_color="#ef4444", line_dash="dash", line_width=1)
        fig.add_hline(y=30, line_color="#26c96f", line_dash="dash", line_width=1)
        fig.add_trace(go.Scatter(x=df["as_of_date"], y=df["close_price"].diff().clip(lower=0).rolling(14).mean()
                                 / (df["close_price"].diff().abs().rolling(14).mean() + 1e-9) * 100,
                                 name="RSI 14", line=dict(color=color, width=1.5)))
        fig.update_layout(yaxis=dict(range=[0, 100]))

    elif indicator == "MACD":
        ema12 = df["close_price"].ewm(span=12, adjust=False).mean()
        ema26 = df["close_price"].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal
        fig.add_trace(go.Bar(x=df["as_of_date"], y=hist, name="Histogram",
                             marker_color=["#26c96f" if v >= 0 else "#ef4444" for v in hist]))
        fig.add_trace(go.Scatter(x=df["as_of_date"], y=macd, name="MACD", line=dict(color="#7eb8f7", width=1.5)))
        fig.add_trace(go.Scatter(x=df["as_of_date"], y=signal, name="Signal", line=dict(color="#f59e0b", width=1.5)))

    elif indicator == "Volume":
        colors = ["#26c96f" if c >= o else "#ef4444"
                  for c, o in zip(df["close_price"], df["open_price"])]
        fig.add_trace(go.Bar(x=df["as_of_date"], y=df["volume"], name="Volume",
                             marker_color=colors, opacity=0.8))

    fig.update_layout(
        paper_bgcolor=CHART_THEME["paper_bgcolor"],
        plot_bgcolor=CHART_THEME["plot_bgcolor"],
        font=CHART_THEME["font"],
        margin=dict(l=0, r=0, t=8, b=0), height=180,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, bgcolor="rgba(0,0,0,0)", font=dict(size=9)),
        xaxis=dict(gridcolor=CHART_THEME["gridcolor"]),
        yaxis=dict(gridcolor=CHART_THEME["gridcolor"]),
    )
    return fig

# ─── Main App ─────────────────────────────────────────────────────────────────
def fmt(val, prefix="", suffix="", decimals=2):
    if val is None or pd.isna(val):
        return "—"
    return f"{prefix}{val:,.{decimals}f}{suffix}"

def pct_color(val):
    if val is None or pd.isna(val):
        return "#8899bb"
    return "#26c96f" if float(val) >= 0 else "#ef4444"


def main():
    # ── Sidebar: Connection ──
    with st.sidebar:
        st.markdown("## ⚙️ Connection")
        host = st.text_input("Host", value="localhost")
        port = st.text_input("Port", value="5432")
        dbname = st.text_input("Database", value="stocks")
        user = st.text_input("User", value="postgres")
        password = st.text_input("Password", type="password")

        if st.button("🔌 Connect", width='stretch'):
            conn_str = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
            try:
                engine = get_engine(conn_str)
                with engine.connect() as c:
                    c.execute(text("SELECT 1"))
                st.session_state["conn_str"] = conn_str
                st.session_state["connected"] = True
                st.success("Connected!")
            except Exception as e:
                st.error(f"Connection failed: {e}")
                st.session_state["connected"] = False

    if not st.session_state.get("connected"):
        st.markdown("""
        <div style='text-align:center; padding: 80px 20px;'>
            <h1 style='font-family: IBM Plex Mono, monospace; color:#7eb8f7; font-size: 2.5rem;'>📈 Stock Dashboard</h1>
            <p style='color:#6b7a99; font-size: 1.1rem;'>Enter your PostgreSQL credentials in the sidebar to begin.</p>
        </div>
        """, unsafe_allow_html=True)
        return

    engine = get_engine(st.session_state["conn_str"])

    # ── Sidebar: Symbol Selection ──
    with st.sidebar:
        st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
        st.markdown("## 🔍 Symbol")

        try:
            exchanges_df = load_exchanges(engine)
        except Exception as e:
            st.error(f"Could not load exchanges: {e}")
            return

        exchange_options = dict(zip(exchanges_df["exchange_name"], exchanges_df["exchange_code"]))
        if not exchange_options:
            # Fallback: load distinct exchanges from symbol_profile
            ex_df = pd.read_sql("SELECT DISTINCT exchange_code FROM public.symbol_profile ORDER BY exchange_code", engine)
            exchange_options = {r: r for r in ex_df["exchange_code"]}

        selected_exchange_name = st.selectbox("Exchange", list(exchange_options.keys()))
        exchange_code = exchange_options[selected_exchange_name]

        symbols_df = load_symbols(engine, exchange_code)
        if symbols_df.empty:
            st.warning("No symbols found for this exchange.")
            return

        sym_options = {f"{r['symbol_code']}  —  {r['name'][:30]}": r['symbol_code']
                       for _, r in symbols_df.iterrows()}
        selected_sym_label = st.selectbox("Symbol", list(sym_options.keys()))
        symbol_code = sym_options[selected_sym_label]

        st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
        st.markdown("## 📊 Chart Options")

        interval_map = {"Daily": "d", "Weekly": "w", "Monthly": "m",
                        "1 min": "1", "5 min": "5", "15 min": "15", "30 min": "30", "Hourly": "h"}
        interval_label = st.selectbox("Interval", list(interval_map.keys()))
        interval_code = interval_map[interval_label]

        chart_type = st.selectbox("Chart Type", ["Candlestick", "OHLC", "Line"])

        import datetime
        col1, col2 = st.columns(2)
        with col1:
            date_from = st.date_input("From", value=datetime.date.today() - datetime.timedelta(days=365))
        with col2:
            date_to = st.date_input("To", value=datetime.date.today())

        st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
        st.markdown("## 🎚️ Overlays")
        show_volume = st.toggle("Volume", value=True)
        overlays = st.multiselect("Price Overlays",
                                  ["MA 20", "MA 50", "MA 200", "Bollinger Bands"],
                                  default=["MA 20", "MA 50"])
        indicators = st.multiselect("Sub-Indicators", ["MACD", "RSI (14)", "Volume"],
                                    default=["MACD"])

    # ── Load Data ──
    try:
        df = load_quote_data(engine, exchange_code, symbol_code, interval_code, date_from, date_to)
    except Exception as e:
        st.error(f"Error loading quote data: {e}")
        return

    profile = load_profile(engine, exchange_code, symbol_code)
    latest = load_latest_price(engine, exchange_code, symbol_code)
    fund = load_fundamentals(engine, exchange_code, symbol_code)

    # ── Header ──
    name = profile["name"] if profile is not None else symbol_code
    sector = profile["sector"] if profile is not None and pd.notna(profile.get("sector", None)) else ""
    industry = profile["industry"] if profile is not None and pd.notna(profile.get("industry", None)) else ""

    tags = f"`{exchange_code}:{symbol_code}`"
    if sector:
        tags += f"  `{sector}`"
    if industry:
        tags += f"  `{industry}`"
    st.markdown(tags)
    st.subheader(name, divider=False)

    # ── KPI Row ──
    close = latest["close_price"] if latest is not None else (df["close_price"].iloc[-1] if not df.empty else None)
    change = latest["change_amount"] if latest is not None else (df["change_amount"].iloc[-1] if not df.empty and "change_amount" in df.columns else None)
    chg_pct = (float(change) / (float(close) - float(change)) * 100) if close and change and float(close) - float(change) != 0 else None

    cols = st.columns(6)
    metrics = [
        ("Price", fmt(close, prefix="$"), fmt(change, prefix="+" if change and float(change) >= 0 else "", suffix="")),
        ("Change %", f"{chg_pct:+.2f}%" if chg_pct is not None else "—", None),
        ("P/E (TTM)", fmt(fund["trailing_pe"] if fund is not None else None), None),
        ("EPS", fmt(fund["earnings_per_share"] if fund is not None else None, prefix="$"), None),
        ("Div Yield", fmt(fund["dividend_yield"] if fund is not None else None, suffix="%"), None),
        ("Beta", fmt(fund["beta"] if fund is not None else None), None),
    ]
    for col, (label, value, delta) in zip(cols, metrics):
        col.metric(label, value, delta)

    # ── Main Chart ──
    if df.empty:
        st.warning(f"No quote data found for {symbol_code} ({interval_label}) in the selected date range.")
    else:
        fig = build_main_chart(df, symbol_code, chart_type, show_volume, overlays)
        st.plotly_chart(fig, width='stretch', config={"displayModeBar": True})

        # ── Sub-indicators ──
        for ind in indicators:
            st.markdown(f"<p style='font-family:IBM Plex Mono,monospace; color:#6b7a99; font-size:0.75rem; margin-bottom:2px; text-transform:uppercase;'>{ind}</p>", unsafe_allow_html=True)
            ind_fig = build_indicator_chart(df, ind)
            st.plotly_chart(ind_fig, width='stretch', config={"displayModeBar": False})

    # ── Tabs: Fundamentals / Technicals / Profile ──
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    tab1, tab2, tab3 = st.tabs(["📋 Fundamentals", "📐 Technicals", "🏢 Company"])

    with tab1:
        if fund is None:
            st.info("No fundamental data available for this symbol.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Valuation**")
                st.write(pd.DataFrame({
                    "Metric": ["Market Cap", "P/E (TTM)", "Forward P/E", "PEG", "P/S", "P/B", "EV/EBITDA"],
                    "Value": [fmt(fund.get("market_capitalization")), fmt(fund.get("trailing_pe")),
                              fmt(fund.get("forward_pe")), fmt(fund.get("peg")),
                              fmt(fund.get("price_to_sales")), fmt(fund.get("price_to_book")),
                              fmt(fund.get("ebitda"))]
                }).set_index("Metric"))
            with c2:
                st.markdown("**Profitability**")
                st.write(pd.DataFrame({
                    "Metric": ["Gross Margin", "Profit Margin", "Op. Margin", "ROA", "ROE"],
                    "Value": [fmt(fund.get("gross_margin"), suffix="%"), fmt(fund.get("profit_margin"), suffix="%"),
                              fmt(fund.get("operating_margin"), suffix="%"), fmt(fund.get("return_on_assets"), suffix="%"),
                              fmt(fund.get("return_on_equity"), suffix="%")]
                }).set_index("Metric"))
            with c3:
                st.markdown("**Per Share**")
                st.write(pd.DataFrame({
                    "Metric": ["EPS", "Revenue/Share", "Cash/Share", "Book Value/Share", "Dividend/Share"],
                    "Value": [fmt(fund.get("earnings_per_share"), prefix="$"), fmt(fund.get("revenue_per_share"), prefix="$"),
                              fmt(fund.get("total_cash_per_share"), prefix="$"), fmt(fund.get("book_value_per_share"), prefix="$"),
                              fmt(fund.get("dividend_per_share"), prefix="$")]
                }).set_index("Metric"))

    with tab2:
        latest_date = df["as_of_date"].max() if not df.empty else None
        tech = load_technicals(engine, exchange_code, symbol_code, latest_date) if latest_date else None
        if tech is None:
            st.info("No technical data available.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Moving Averages (SMA)**")
                st.write(pd.DataFrame({
                    "Period": ["MA5", "MA10", "MA20", "MA50", "MA100", "MA200"],
                    "Value": [fmt(tech.get(f"ma{p}"), prefix="$") for p in [5, 10, 20, 50, 100, 200]]
                }).set_index("Period"))
            with c2:
                st.markdown("**Oscillators**")
                st.write(pd.DataFrame({
                    "Indicator": ["RSI 9", "RSI 14", "MACD", "CCI", "ATR", "WPR 14"],
                    "Value": [fmt(tech.get("rsi9")), fmt(tech.get("rsi14")), fmt(tech.get("macd")),
                              fmt(tech.get("cci")), fmt(tech.get("atr")), fmt(tech.get("wpr14"))]
                }).set_index("Indicator"))
            with c3:
                st.markdown("**Bollinger Bands (20)**")
                st.write(pd.DataFrame({
                    "Band": ["Upper", "Lower", "Bandwidth"],
                    "Value": [fmt(tech.get("upper_bb20"), prefix="$"), fmt(tech.get("lower_bb20"), prefix="$"),
                              fmt(tech.get("bandwidth_bb20"))]
                }).set_index("Band"))
                st.markdown("**Performance**")
                st.write(pd.DataFrame({
                    "Period": ["Week", "Month", "YTD", "Year"],
                    "Change": [fmt(tech.get("week_change"), suffix="%"), fmt(tech.get("month_change"), suffix="%"),
                               fmt(tech.get("ytd_change"), suffix="%"), fmt(tech.get("year_change"), suffix="%")]
                }).set_index("Period"))

    with tab3:
        if profile is None:
            st.info("No profile data available.")
        else:
            c1, c2 = st.columns([2, 1])
            with c1:
                about = profile.get("about") or profile.get("description") or ""
                if about and not pd.isna(about):
                    st.markdown("**About**")
                    st.markdown(f"<p style='color:#a0aec0; line-height:1.7;'>{about[:800]}{'...' if len(about) > 800 else ''}</p>",
                                unsafe_allow_html=True)
            with c2:
                st.markdown("**Details**")
                for label, key in [("Country", "country"), ("Sector", "sector"), ("Industry", "industry"),
                                    ("Currency", "currency"), ("Website", "website"), ("Exchange", "exchange_code"),
                                    ("CIK","cik"), ("ISIN", "isin"), ("CUSIP", "cusip"), ("FIGI", "figi")]:
                    val = profile.get(key)
                    if val and not pd.isna(val):
                        if key == "website":
                            st.markdown(f"**{label}**: [{val}]({val})")
                        else:
                            st.markdown(f"**{label}**: {val}")


if __name__ == "__main__":
    main()
