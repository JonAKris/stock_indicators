--
-- PostgreSQL database dump
--

\restrict Iwkvob9NYaRsehLSLb7CX5ou00TMadFlBB5z9T0tM7VizaHTaGqYd4TyerQn6mQ

-- Dumped from database version 16.13 (Ubuntu 16.13-1.pgdg24.04+1)
-- Dumped by pg_dump version 18.3 (Ubuntu 18.3-1.pgdg24.04+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: countries; Type: TABLE; Schema: public; Owner: stockman
--

CREATE TABLE public.countries (
    id integer NOT NULL,
    country_code character varying(10) NOT NULL,
    country_name character varying(100) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.countries OWNER TO stockman;

--
-- Name: countries_id_seq; Type: SEQUENCE; Schema: public; Owner: stockman
--

CREATE SEQUENCE public.countries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.countries_id_seq OWNER TO stockman;

--
-- Name: countries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: stockman
--

ALTER SEQUENCE public.countries_id_seq OWNED BY public.countries.id;


--
-- Name: currencies; Type: TABLE; Schema: public; Owner: stockman
--

CREATE TABLE public.currencies (
    id integer NOT NULL,
    currency_code character varying(10) NOT NULL,
    currency_name character varying(100) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.currencies OWNER TO stockman;

--
-- Name: currencies_id_seq; Type: SEQUENCE; Schema: public; Owner: stockman
--

CREATE SEQUENCE public.currencies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.currencies_id_seq OWNER TO stockman;

--
-- Name: currencies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: stockman
--

ALTER SEQUENCE public.currencies_id_seq OWNED BY public.currencies.id;


--
-- Name: exchanges; Type: TABLE; Schema: public; Owner: stockman
--

CREATE TABLE public.exchanges (
    id integer NOT NULL,
    exchange_code character varying(10) NOT NULL,
    exchange_name character varying(100) NOT NULL,
    country_code character varying(10),
    currency_code character varying(10),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.exchanges OWNER TO stockman;

--
-- Name: exchanges_id_seq; Type: SEQUENCE; Schema: public; Owner: stockman
--

CREATE SEQUENCE public.exchanges_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.exchanges_id_seq OWNER TO stockman;

--
-- Name: exchanges_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: stockman
--

ALTER SEQUENCE public.exchanges_id_seq OWNED BY public.exchanges.id;


--
-- Name: symbol; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.symbol (
    exchange_code text NOT NULL,
    symbol_code text NOT NULL,
    name text NOT NULL,
    type text,
    currency character(3),
    figi text,
    as_of_date date NOT NULL,
    open_price numeric(10,4),
    high_price numeric(10,4),
    low_price numeric(10,4),
    close_price numeric(10,4),
    volume bigint,
    open_interest bigint,
    previous_price numeric(10,4),
    change_amount numeric(10,4),
    bid_price numeric(10,4),
    ask_price numeric(10,4)
);


ALTER TABLE public.symbol OWNER TO postgres;

--
-- Name: symbol_fundamental; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.symbol_fundamental (
    exchange_code text NOT NULL,
    symbol_code text NOT NULL,
    market_capitalization numeric(10,4),
    ebitda numeric(10,4),
    peg numeric(10,4),
    book_value numeric(10,4),
    dividend_per_share numeric(10,4),
    dividend_yield numeric(10,4),
    earnings_per_share numeric(10,4),
    revenue_per_share numeric(10,4),
    price_to_sales numeric(10,4),
    price_to_book numeric(10,4),
    beta numeric(10,4),
    shares_outstanding bigint,
    dividend_date date,
    gross_margin numeric(10,4),
    profit_margin numeric(10,4),
    operating_margin numeric(10,4),
    return_on_assets numeric(10,4),
    return_on_equity numeric(10,4),
    revenue numeric(10,4),
    gross_profit numeric(10,4),
    trailing_pe numeric(10,4),
    forward_pe numeric(10,4),
    total_cash numeric(10,4),
    total_cash_per_share numeric(10,4),
    total_debt numeric(10,4),
    total_debt_to_equity numeric(10,4),
    book_value_per_share numeric(10,4)
);


ALTER TABLE public.symbol_fundamental OWNER TO postgres;

--
-- Name: symbol_profile; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.symbol_profile (
    exchange_code text NOT NULL,
    symbol_code text NOT NULL,
    name text NOT NULL,
    description text,
    type text,
    currency character(3),
    country text,
    figi text,
    isin text,
    cusip text,
    cik text,
    lei text,
    sector text,
    industry text,
    about text,
    address text,
    phone text,
    website text
);


ALTER TABLE public.symbol_profile OWNER TO postgres;

--
-- Name: symbol_quote; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.symbol_quote (
    exchange_code text NOT NULL,
    symbol_code text NOT NULL,
    interval_code text NOT NULL,
    as_of_date date NOT NULL,
    name text,
    open_price numeric(10,4),
    high_price numeric(10,4),
    low_price numeric(10,4),
    close_price numeric(10,4),
    adjusted_close numeric(10,4),
    volume bigint NOT NULL,
    open_interest bigint,
    bid_price numeric(10,4),
    ask_price numeric(10,4),
    previous_price numeric(10,4),
    change_amount numeric(10,4),
    currency character(3),
    CONSTRAINT ck_symbol_quote_high_low CHECK (((high_price)::double precision >= (low_price)::double precision)),
    CONSTRAINT ck_symbol_quote_interval CHECK ((interval_code = ANY (ARRAY['d'::text, 'w'::text, 'm'::text, 'q'::text, 'y'::text, '1'::text, '5'::text, '10'::text, '15'::text, '30'::text, 'h'::text])))
);


ALTER TABLE public.symbol_quote OWNER TO postgres;

--
-- Name: symbol_technical; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.symbol_technical (
    exchange_code text NOT NULL,
    symbol_code text NOT NULL,
    as_of_date date NOT NULL,
    quarter_change numeric(10,4),
    biannual_change numeric(10,4),
    ytd_change numeric(10,4),
    week_low numeric(10,4),
    week_high numeric(10,4),
    week_change numeric(10,4),
    week_volume bigint,
    week_avg_volume bigint,
    week_avg_change numeric(10,4),
    week_yield numeric(10,4),
    month_low numeric(10,4),
    month_high numeric(10,4),
    month_change numeric(10,4),
    month_volume bigint,
    month_avg_volume bigint,
    month_avg_change numeric(10,4),
    month_yield numeric(10,4),
    year_low numeric(10,4),
    year_high numeric(10,4),
    year_change numeric(10,4),
    year_volume bigint,
    year_avg_volume bigint,
    year_avg_change numeric(10,4),
    year_yield numeric(10,4),
    ma5 numeric(10,4),
    ma10 numeric(10,4),
    ma20 numeric(10,4),
    ma50 numeric(10,4),
    ma100 numeric(10,4),
    ma200 numeric(10,4),
    wma5 numeric(10,4),
    wma10 numeric(10,4),
    wma20 numeric(10,4),
    wma50 numeric(10,4),
    wma100 numeric(10,4),
    wma200 numeric(10,4),
    ema5 numeric(10,4),
    ema10 numeric(10,4),
    ema20 numeric(10,4),
    ema50 numeric(10,4),
    ema100 numeric(10,4),
    ema200 numeric(10,4),
    macd numeric(10,4),
    sto9_fast numeric(10,4),
    sto9_slow numeric(10,4),
    sto9_full numeric(10,4),
    sto14_fast numeric(10,4),
    sto14_slow numeric(10,4),
    sto14_full numeric(10,4),
    rsi9 numeric(10,4),
    rsi14 numeric(10,4),
    wpr14 numeric(10,4),
    mtm14 numeric(10,4),
    roc14 numeric(10,4),
    upper_bb20 numeric(10,4),
    lower_bb20 numeric(10,4),
    bandwidth_bb20 numeric(10,4),
    obv20 bigint,
    ad20 numeric(10,4),
    aroon20 numeric(10,4),
    dmi_positive numeric(10,4),
    dmi_negative numeric(10,4),
    dmi_average numeric(10,4),
    atr numeric(10,4),
    cci numeric(10,4),
    sar numeric(10,4),
    volatility numeric(10,4),
    liquidity numeric(10,4)
);


ALTER TABLE public.symbol_technical OWNER TO postgres;

--
-- Name: countries id; Type: DEFAULT; Schema: public; Owner: stockman
--

ALTER TABLE ONLY public.countries ALTER COLUMN id SET DEFAULT nextval('public.countries_id_seq'::regclass);


--
-- Name: currencies id; Type: DEFAULT; Schema: public; Owner: stockman
--

ALTER TABLE ONLY public.currencies ALTER COLUMN id SET DEFAULT nextval('public.currencies_id_seq'::regclass);


--
-- Name: exchanges id; Type: DEFAULT; Schema: public; Owner: stockman
--

ALTER TABLE ONLY public.exchanges ALTER COLUMN id SET DEFAULT nextval('public.exchanges_id_seq'::regclass);


--
-- Name: countries countries_country_code_key; Type: CONSTRAINT; Schema: public; Owner: stockman
--

ALTER TABLE ONLY public.countries
    ADD CONSTRAINT countries_country_code_key UNIQUE (country_code);


--
-- Name: countries countries_pkey; Type: CONSTRAINT; Schema: public; Owner: stockman
--

ALTER TABLE ONLY public.countries
    ADD CONSTRAINT countries_pkey PRIMARY KEY (id);


--
-- Name: currencies currencies_currency_code_key; Type: CONSTRAINT; Schema: public; Owner: stockman
--

ALTER TABLE ONLY public.currencies
    ADD CONSTRAINT currencies_currency_code_key UNIQUE (currency_code);


--
-- Name: currencies currencies_pkey; Type: CONSTRAINT; Schema: public; Owner: stockman
--

ALTER TABLE ONLY public.currencies
    ADD CONSTRAINT currencies_pkey PRIMARY KEY (id);


--
-- Name: exchanges exchanges_exchange_code_key; Type: CONSTRAINT; Schema: public; Owner: stockman
--

ALTER TABLE ONLY public.exchanges
    ADD CONSTRAINT exchanges_exchange_code_key UNIQUE (exchange_code);


--
-- Name: exchanges exchanges_pkey; Type: CONSTRAINT; Schema: public; Owner: stockman
--

ALTER TABLE ONLY public.exchanges
    ADD CONSTRAINT exchanges_pkey PRIMARY KEY (id);


--
-- Name: symbol pk_symbol; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.symbol
    ADD CONSTRAINT pk_symbol PRIMARY KEY (exchange_code, symbol_code);


--
-- Name: symbol_fundamental pk_symbol_fundamental; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.symbol_fundamental
    ADD CONSTRAINT pk_symbol_fundamental PRIMARY KEY (exchange_code, symbol_code);


--
-- Name: symbol_profile pk_symbol_profile; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.symbol_profile
    ADD CONSTRAINT pk_symbol_profile PRIMARY KEY (exchange_code, symbol_code);


--
-- Name: symbol_quote pk_symbol_quote; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.symbol_quote
    ADD CONSTRAINT pk_symbol_quote PRIMARY KEY (exchange_code, symbol_code, interval_code, as_of_date);


--
-- Name: symbol_technical pk_symbol_technical; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.symbol_technical
    ADD CONSTRAINT pk_symbol_technical PRIMARY KEY (exchange_code, symbol_code, as_of_date);


--
-- Name: exchanges exchanges_country_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: stockman
--

ALTER TABLE ONLY public.exchanges
    ADD CONSTRAINT exchanges_country_code_fkey FOREIGN KEY (country_code) REFERENCES public.countries(country_code);


--
-- Name: exchanges exchanges_currency_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: stockman
--

ALTER TABLE ONLY public.exchanges
    ADD CONSTRAINT exchanges_currency_code_fkey FOREIGN KEY (currency_code) REFERENCES public.currencies(currency_code);


--
-- =============================================================================
-- PORTFOLIO SIMULATION EXTENSIONS
-- =============================================================================
-- Adds: portfolios, trades, cash_transactions, splits, dividends
-- Plus: views for positions, realized P&L (FIFO), and performance summary
-- =============================================================================

--
-- Name: portfolios; Type: TABLE; Schema: public; Owner: stockman
--

CREATE TABLE public.portfolios (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    base_currency character(3) NOT NULL DEFAULT 'USD',
    initial_cash numeric(18,4) NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_portfolios_initial_cash CHECK (initial_cash >= 0)
);

ALTER TABLE public.portfolios OWNER TO stockman;

CREATE SEQUENCE public.portfolios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.portfolios_id_seq OWNER TO stockman;
ALTER SEQUENCE public.portfolios_id_seq OWNED BY public.portfolios.id;
ALTER TABLE ONLY public.portfolios ALTER COLUMN id SET DEFAULT nextval('public.portfolios_id_seq'::regclass);

ALTER TABLE ONLY public.portfolios
    ADD CONSTRAINT portfolios_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.portfolios
    ADD CONSTRAINT portfolios_name_key UNIQUE (name);


--
-- Name: trades; Type: TABLE; Schema: public; Owner: stockman
--
-- One row per executed buy/sell. Joins to symbol via (exchange_code, symbol_code).
-- Quantity is always positive; direction is determined by `side`.
--

CREATE TABLE public.trades (
    id bigint NOT NULL,
    portfolio_id integer NOT NULL,
    exchange_code text NOT NULL,
    symbol_code text NOT NULL,
    trade_date date NOT NULL,
    side character varying(4) NOT NULL,
    quantity numeric(18,6) NOT NULL,
    price numeric(18,6) NOT NULL,
    fees numeric(18,4) NOT NULL DEFAULT 0,
    currency character(3),
    notes text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_trades_side CHECK (side IN ('BUY', 'SELL')),
    CONSTRAINT ck_trades_quantity CHECK (quantity > 0),
    CONSTRAINT ck_trades_price CHECK (price >= 0),
    CONSTRAINT ck_trades_fees CHECK (fees >= 0)
);

ALTER TABLE public.trades OWNER TO stockman;

CREATE SEQUENCE public.trades_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.trades_id_seq OWNER TO stockman;
ALTER SEQUENCE public.trades_id_seq OWNED BY public.trades.id;
ALTER TABLE ONLY public.trades ALTER COLUMN id SET DEFAULT nextval('public.trades_id_seq'::regclass);

ALTER TABLE ONLY public.trades
    ADD CONSTRAINT trades_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.trades
    ADD CONSTRAINT trades_portfolio_fkey FOREIGN KEY (portfolio_id)
    REFERENCES public.portfolios(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.trades
    ADD CONSTRAINT trades_symbol_fkey FOREIGN KEY (exchange_code, symbol_code)
    REFERENCES public.symbol(exchange_code, symbol_code);

CREATE INDEX idx_trades_portfolio ON public.trades (portfolio_id);
CREATE INDEX idx_trades_symbol ON public.trades (exchange_code, symbol_code);
CREATE INDEX idx_trades_date ON public.trades (trade_date);
CREATE INDEX idx_trades_portfolio_symbol_date
    ON public.trades (portfolio_id, exchange_code, symbol_code, trade_date, id);


--
-- Name: cash_transactions; Type: TABLE; Schema: public; Owner: stockman
--
-- Non-trade cash movements: deposits, withdrawals, dividends received,
-- standalone fees, FX adjustments.
--

CREATE TABLE public.cash_transactions (
    id bigint NOT NULL,
    portfolio_id integer NOT NULL,
    txn_date date NOT NULL,
    type character varying(20) NOT NULL,
    amount numeric(18,4) NOT NULL,
    currency character(3),
    related_exchange_code text,
    related_symbol_code text,
    notes text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_cash_txn_type CHECK (type IN ('DEPOSIT', 'WITHDRAWAL', 'DIVIDEND', 'FEE', 'INTEREST', 'FX_ADJUST'))
);

ALTER TABLE public.cash_transactions OWNER TO stockman;

CREATE SEQUENCE public.cash_transactions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.cash_transactions_id_seq OWNER TO stockman;
ALTER SEQUENCE public.cash_transactions_id_seq OWNED BY public.cash_transactions.id;
ALTER TABLE ONLY public.cash_transactions
    ALTER COLUMN id SET DEFAULT nextval('public.cash_transactions_id_seq'::regclass);

ALTER TABLE ONLY public.cash_transactions
    ADD CONSTRAINT cash_transactions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.cash_transactions
    ADD CONSTRAINT cash_transactions_portfolio_fkey FOREIGN KEY (portfolio_id)
    REFERENCES public.portfolios(id) ON DELETE CASCADE;

CREATE INDEX idx_cash_txn_portfolio ON public.cash_transactions (portfolio_id);
CREATE INDEX idx_cash_txn_date ON public.cash_transactions (txn_date);


--
-- Name: splits; Type: TABLE; Schema: public; Owner: stockman
--
-- Mirrors the EODData /Splits endpoint. Used to adjust historical positions.
-- multiplier = new_shares / old_shares (e.g., 2.0 for a 2:1 forward split).
--

CREATE TABLE public.splits (
    id bigint NOT NULL,
    exchange_code text NOT NULL,
    symbol_code text NOT NULL,
    split_date date NOT NULL,
    ratio text NOT NULL,
    multiplier numeric(18,8) NOT NULL,
    source text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_splits_multiplier CHECK (multiplier > 0)
);

ALTER TABLE public.splits OWNER TO stockman;

CREATE SEQUENCE public.splits_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.splits_id_seq OWNER TO stockman;
ALTER SEQUENCE public.splits_id_seq OWNED BY public.splits.id;
ALTER TABLE ONLY public.splits ALTER COLUMN id SET DEFAULT nextval('public.splits_id_seq'::regclass);

ALTER TABLE ONLY public.splits
    ADD CONSTRAINT splits_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.splits
    ADD CONSTRAINT splits_unique UNIQUE (exchange_code, symbol_code, split_date);

ALTER TABLE ONLY public.splits
    ADD CONSTRAINT splits_symbol_fkey FOREIGN KEY (exchange_code, symbol_code)
    REFERENCES public.symbol(exchange_code, symbol_code);

CREATE INDEX idx_splits_symbol ON public.splits (exchange_code, symbol_code);


--
-- Name: dividends; Type: TABLE; Schema: public; Owner: stockman
--
-- Mirrors the EODData /Dividends endpoint. Per-share amounts on ex-date.
-- Cash actually received by a portfolio is recorded in cash_transactions.
--

CREATE TABLE public.dividends (
    id bigint NOT NULL,
    exchange_code text NOT NULL,
    symbol_code text NOT NULL,
    ex_date date NOT NULL,
    payment_date date,
    amount numeric(18,6) NOT NULL,
    currency character(3),
    source text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_dividends_amount CHECK (amount >= 0)
);

ALTER TABLE public.dividends OWNER TO stockman;

CREATE SEQUENCE public.dividends_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.dividends_id_seq OWNER TO stockman;
ALTER SEQUENCE public.dividends_id_seq OWNED BY public.dividends.id;
ALTER TABLE ONLY public.dividends ALTER COLUMN id SET DEFAULT nextval('public.dividends_id_seq'::regclass);

ALTER TABLE ONLY public.dividends
    ADD CONSTRAINT dividends_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.dividends
    ADD CONSTRAINT dividends_unique UNIQUE (exchange_code, symbol_code, ex_date);

ALTER TABLE ONLY public.dividends
    ADD CONSTRAINT dividends_symbol_fkey FOREIGN KEY (exchange_code, symbol_code)
    REFERENCES public.symbol(exchange_code, symbol_code);

CREATE INDEX idx_dividends_symbol ON public.dividends (exchange_code, symbol_code);


--
-- updated_at triggers
--

CREATE OR REPLACE FUNCTION public.set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

ALTER FUNCTION public.set_updated_at() OWNER TO stockman;

CREATE TRIGGER trg_portfolios_updated_at BEFORE UPDATE ON public.portfolios
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_trades_updated_at BEFORE UPDATE ON public.trades
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_cash_txn_updated_at BEFORE UPDATE ON public.cash_transactions
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- =============================================================================
-- VIEWS
-- =============================================================================

--
-- View: split_adjusted_trades
-- Applies all splits AFTER a trade's date to adjust historical quantity/price.
-- A 2:1 split after a buy: quantity *= 2, price /= 2 (cost basis preserved).
--

CREATE OR REPLACE VIEW public.split_adjusted_trades AS
SELECT
    t.id,
    t.portfolio_id,
    t.exchange_code,
    t.symbol_code,
    t.trade_date,
    t.side,
    t.quantity * COALESCE((
        SELECT EXP(SUM(LN(s.multiplier)))
        FROM public.splits s
        WHERE s.exchange_code = t.exchange_code
          AND s.symbol_code = t.symbol_code
          AND s.split_date > t.trade_date
    ), 1) AS adj_quantity,
    t.price / COALESCE((
        SELECT EXP(SUM(LN(s.multiplier)))
        FROM public.splits s
        WHERE s.exchange_code = t.exchange_code
          AND s.symbol_code = t.symbol_code
          AND s.split_date > t.trade_date
    ), 1) AS adj_price,
    t.fees,
    t.currency
FROM public.trades t;

ALTER VIEW public.split_adjusted_trades OWNER TO stockman;


--
-- View: portfolio_positions
-- Current open holdings per portfolio with market value and unrealized P&L.
-- Cost basis here is average cost on the *remaining* shares; for FIFO realized
-- P&L see portfolio_realized_pnl.
--

CREATE OR REPLACE VIEW public.portfolio_positions AS
WITH agg AS (
    SELECT
        sat.portfolio_id,
        sat.exchange_code,
        sat.symbol_code,
        SUM(CASE WHEN sat.side = 'BUY' THEN sat.adj_quantity ELSE -sat.adj_quantity END) AS quantity,
        SUM(CASE WHEN sat.side = 'BUY' THEN sat.adj_quantity * sat.adj_price ELSE 0 END) AS total_buy_cost,
        SUM(CASE WHEN sat.side = 'BUY' THEN sat.adj_quantity ELSE 0 END) AS total_buy_qty,
        SUM(sat.fees) AS total_fees
    FROM public.split_adjusted_trades sat
    GROUP BY sat.portfolio_id, sat.exchange_code, sat.symbol_code
)
SELECT
    a.portfolio_id,
    p.name AS portfolio_name,
    a.exchange_code,
    a.symbol_code,
    sp.name AS symbol_name,
    a.quantity,
    CASE WHEN a.total_buy_qty > 0 THEN a.total_buy_cost / a.total_buy_qty ELSE NULL END AS avg_buy_price,
    s.close_price AS current_price,
    a.quantity * s.close_price AS market_value,
    (a.quantity * s.close_price)
        - CASE WHEN a.total_buy_qty > 0 THEN a.quantity * (a.total_buy_cost / a.total_buy_qty) ELSE 0 END
        AS unrealized_pnl,
    a.total_fees,
    s.as_of_date AS price_as_of
FROM agg a
JOIN public.portfolios p ON p.id = a.portfolio_id
LEFT JOIN public.symbol s
    ON s.exchange_code = a.exchange_code AND s.symbol_code = a.symbol_code
LEFT JOIN public.symbol_profile sp
    ON sp.exchange_code = a.exchange_code AND sp.symbol_code = a.symbol_code
WHERE a.quantity > 0;

ALTER VIEW public.portfolio_positions OWNER TO stockman;


--
-- View: portfolio_realized_pnl
-- FIFO realized P&L. Walks trades in (date, id) order and matches each SELL
-- against the oldest unmatched BUYs.
--

CREATE OR REPLACE VIEW public.portfolio_realized_pnl AS
WITH ordered AS (
    SELECT
        sat.*,
        ROW_NUMBER() OVER (
            PARTITION BY sat.portfolio_id, sat.exchange_code, sat.symbol_code
            ORDER BY sat.trade_date, sat.id
        ) AS rn
    FROM public.split_adjusted_trades sat
),
buys AS (
    SELECT
        portfolio_id, exchange_code, symbol_code,
        trade_date, id, adj_quantity AS qty, adj_price AS price, rn
    FROM ordered WHERE side = 'BUY'
),
sells AS (
    SELECT
        portfolio_id, exchange_code, symbol_code,
        trade_date, id, adj_quantity AS qty, adj_price AS price, rn
    FROM ordered WHERE side = 'SELL'
),
-- For each (portfolio, symbol), build cumulative buy-quantity windows so we
-- can match sells against them in FIFO order.
buy_lots AS (
    SELECT
        b.*,
        COALESCE(SUM(b.qty) OVER (
            PARTITION BY b.portfolio_id, b.exchange_code, b.symbol_code
            ORDER BY b.trade_date, b.id
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ), 0) AS cum_qty_before,
        SUM(b.qty) OVER (
            PARTITION BY b.portfolio_id, b.exchange_code, b.symbol_code
            ORDER BY b.trade_date, b.id
        ) AS cum_qty_after
    FROM buys b
),
sell_lots AS (
    SELECT
        s.*,
        COALESCE(SUM(s.qty) OVER (
            PARTITION BY s.portfolio_id, s.exchange_code, s.symbol_code
            ORDER BY s.trade_date, s.id
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ), 0) AS cum_qty_before,
        SUM(s.qty) OVER (
            PARTITION BY s.portfolio_id, s.exchange_code, s.symbol_code
            ORDER BY s.trade_date, s.id
        ) AS cum_qty_after
    FROM sells s
),
-- Match each sell to overlapping buy ranges on the cumulative-quantity number line.
matches AS (
    SELECT
        s.portfolio_id, s.exchange_code, s.symbol_code,
        s.id AS sell_id, s.trade_date AS sell_date, s.price AS sell_price,
        b.id AS buy_id, b.trade_date AS buy_date, b.price AS buy_price,
        GREATEST(
            LEAST(s.cum_qty_after, b.cum_qty_after)
            - GREATEST(s.cum_qty_before, b.cum_qty_before),
            0
        ) AS matched_qty
    FROM sell_lots s
    JOIN buy_lots b
      ON b.portfolio_id = s.portfolio_id
     AND b.exchange_code = s.exchange_code
     AND b.symbol_code = s.symbol_code
     AND b.cum_qty_before < s.cum_qty_after
     AND b.cum_qty_after  > s.cum_qty_before
)
SELECT
    portfolio_id,
    exchange_code,
    symbol_code,
    SUM(matched_qty) AS qty_closed,
    SUM(matched_qty * (sell_price - buy_price)) AS realized_pnl
FROM matches
GROUP BY portfolio_id, exchange_code, symbol_code;

ALTER VIEW public.portfolio_realized_pnl OWNER TO stockman;


--
-- View: portfolio_performance
-- One row per portfolio. Cash balance, market value, realized + unrealized P&L,
-- and total return %. This is the headline view for the Dash dashboard.
--

CREATE OR REPLACE VIEW public.portfolio_performance AS
WITH cash AS (
    SELECT
        p.id AS portfolio_id,
        p.initial_cash
        + COALESCE((SELECT SUM(CASE
                WHEN ct.type IN ('DEPOSIT', 'DIVIDEND', 'INTEREST') THEN ct.amount
                WHEN ct.type IN ('WITHDRAWAL', 'FEE') THEN -ct.amount
                ELSE ct.amount
            END)
            FROM public.cash_transactions ct WHERE ct.portfolio_id = p.id), 0)
        - COALESCE((SELECT SUM(
              CASE WHEN t.side = 'BUY' THEN t.quantity * t.price + t.fees
                   ELSE -(t.quantity * t.price) + t.fees END)
            FROM public.trades t WHERE t.portfolio_id = p.id), 0)
        AS cash_balance,
        COALESCE((SELECT SUM(ct.amount) FROM public.cash_transactions ct
                  WHERE ct.portfolio_id = p.id AND ct.type = 'DEPOSIT'), 0) AS total_deposits,
        COALESCE((SELECT SUM(ct.amount) FROM public.cash_transactions ct
                  WHERE ct.portfolio_id = p.id AND ct.type = 'WITHDRAWAL'), 0) AS total_withdrawals,
        COALESCE((SELECT SUM(ct.amount) FROM public.cash_transactions ct
                  WHERE ct.portfolio_id = p.id AND ct.type = 'DIVIDEND'), 0) AS total_dividends
    FROM public.portfolios p
),
mv AS (
    SELECT portfolio_id,
           SUM(market_value) AS market_value,
           SUM(unrealized_pnl) AS unrealized_pnl
    FROM public.portfolio_positions
    GROUP BY portfolio_id
),
rp AS (
    SELECT portfolio_id, SUM(realized_pnl) AS realized_pnl
    FROM public.portfolio_realized_pnl
    GROUP BY portfolio_id
)
SELECT
    p.id AS portfolio_id,
    p.name,
    p.base_currency,
    p.is_active,
    p.initial_cash,
    cash.total_deposits,
    cash.total_withdrawals,
    cash.total_dividends,
    cash.cash_balance,
    COALESCE(mv.market_value, 0) AS market_value,
    cash.cash_balance + COALESCE(mv.market_value, 0) AS total_value,
    COALESCE(rp.realized_pnl, 0) AS realized_pnl,
    COALESCE(mv.unrealized_pnl, 0) AS unrealized_pnl,
    COALESCE(rp.realized_pnl, 0) + COALESCE(mv.unrealized_pnl, 0) AS total_pnl,
    CASE
        WHEN (p.initial_cash + cash.total_deposits) > 0
        THEN (cash.cash_balance + COALESCE(mv.market_value, 0)
              - p.initial_cash - cash.total_deposits + cash.total_withdrawals)
             / (p.initial_cash + cash.total_deposits) * 100
        ELSE NULL
    END AS total_return_pct
FROM public.portfolios p
LEFT JOIN cash ON cash.portfolio_id = p.id
LEFT JOIN mv   ON mv.portfolio_id = p.id
LEFT JOIN rp   ON rp.portfolio_id = p.id;

ALTER VIEW public.portfolio_performance OWNER TO stockman;


--
-- PostgreSQL database dump complete
--

\unrestrict Iwkvob9NYaRsehLSLb7CX5ou00TMadFlBB5z9T0tM7VizaHTaGqYd4TyerQn6mQ