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
-- PostgreSQL database dump complete
--

\unrestrict Iwkvob9NYaRsehLSLb7CX5ou00TMadFlBB5z9T0tM7VizaHTaGqYd4TyerQn6mQ

