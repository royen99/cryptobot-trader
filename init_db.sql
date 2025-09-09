--
-- PostgreSQL database dump
--

-- Dumped from database version 14.15 (Ubuntu 14.15-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 14.15 (Ubuntu 14.15-0ubuntu0.22.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
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
-- Name: balances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.balances (
  exchange TEXT NOT NULL,
  currency TEXT NOT NULL,
  available_balance NUMERIC NOT NULL,
  PRIMARY KEY (exchange, currency)
);


--
-- Name: bot_status; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_status (
    id integer NOT NULL,
    last_trade text DEFAULT 'No trades yet'::text,
    active boolean DEFAULT false
);


--
-- Name: bot_status_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bot_status_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bot_status_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bot_status_id_seq OWNED BY public.bot_status.id;


--
-- Name: manual_commands; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manual_commands (
    id integer NOT NULL,
    symbol text NOT NULL,
    action text NOT NULL,
    amount real,
    "timestamp" timestamp without time zone DEFAULT now(),
    executed boolean DEFAULT false,
    CONSTRAINT manual_commands_action_check CHECK ((action = ANY (ARRAY['BUY'::text, 'SELL'::text])))
);


--
-- Name: manual_commands_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.manual_commands_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: manual_commands_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.manual_commands_id_seq OWNED BY public.manual_commands.id;


--
-- Name: price_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.price_history (
    symbol text NOT NULL,
    "timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    price numeric(18,12)
);


--
-- Name: trades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trades (
    id integer NOT NULL,
    symbol text,
    side text,
    amount real,
    price real,
    "timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: trades_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.trades_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trades_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.trades_id_seq OWNED BY public.trades.id;


--
-- Name: trading_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trading_state (
    symbol text NOT NULL,
    initial_price numeric,
    total_trades integer,
    total_profit numeric
);


--
-- Name: bot_status id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_status ALTER COLUMN id SET DEFAULT nextval('public.bot_status_id_seq'::regclass);


--
-- Name: manual_commands id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manual_commands ALTER COLUMN id SET DEFAULT nextval('public.manual_commands_id_seq'::regclass);


--
-- Name: trades id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trades ALTER COLUMN id SET DEFAULT nextval('public.trades_id_seq'::regclass);


--
-- Name: balances balances_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.balances
    ADD CONSTRAINT balances_pkey PRIMARY KEY (currency);


--
-- Name: bot_status bot_status_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_status
    ADD CONSTRAINT bot_status_pkey PRIMARY KEY (id);


--
-- Name: manual_commands manual_commands_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manual_commands
    ADD CONSTRAINT manual_commands_pkey PRIMARY KEY (id);


--
-- Name: price_history price_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.price_history
    ADD CONSTRAINT price_history_pkey PRIMARY KEY (symbol, "timestamp");


--
-- Name: trades trades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trades
    ADD CONSTRAINT trades_pkey PRIMARY KEY (id);


--
-- Name: trading_state trading_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trading_state
    ADD CONSTRAINT trading_state_pkey PRIMARY KEY (symbol);


--
-- Name: idx_price_history_symbol_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_price_history_symbol_ts ON public.price_history USING btree (symbol, "timestamp" DESC);


--
-- Name: idx_symbol_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_symbol_timestamp ON public.price_history USING btree (symbol, "timestamp");


--
-- Name: idx_trades_ts_desc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trades_ts_desc ON public.trades USING btree ("timestamp" DESC);


--
-- PostgreSQL database dump complete
--
