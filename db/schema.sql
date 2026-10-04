-- Phase 1 schema: central accuracy ledger for the live Stock Price Validation
-- path (stock_prediction_app.py). See C:\Users\nithi\.claude\plans\glowing-rolling-globe.md
-- for the full design rationale. Idempotent: safe to re-run.

create extension if not exists pgcrypto;

-- Phase 1 note: id has no FK to auth.users yet because there is no real login
-- in Phase 1 (attribution bridges off the CURRENT_USER env var instead, per
-- the plan). Phase 3 (Supabase Auth) will either backfill this FK or insert
-- new profiles with id = auth.uid() directly so the two line up.
create table if not exists profiles (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  display_name text,
  team text not null default 'default',
  role text not null default 'member' check (role in ('member','admin')),
  created_at timestamptz not null default now(),
  unique (email)
);

create table if not exists stock_predictions (
  id uuid primary key default gen_random_uuid(),
  run_id text not null,
  user_id uuid references profiles(id),
  model_version text not null,

  symbol text not null,
  historical_context_start_date date,
  prediction_origin_date date not null,
  decision_horizon_days int not null,
  target_date date not null,
  initial_capital numeric,
  benchmark text,
  validation_mode text,
  price_basis text,

  stock_prediction_input jsonb not null,
  stock_prediction_input_hash text not null,

  predicted_target_price numeric,
  predicted_return_pct numeric,
  predicted_final_capital numeric,
  predicted_total_pl numeric,
  decision text,
  confidence_score numeric,
  risk_score numeric,
  -- Full AI prediction dict verbatim (origin_price_used, effective_origin_date,
  -- features_used, data_quality_score, model_version, etc.) -- the resolver
  -- needs this complete shape to re-run run_stock_validation() later; the
  -- promoted columns above are only what the dashboard filters/aggregates on.
  ai_prediction_raw jsonb,

  status text not null default 'pending'
    check (status in ('pending','resolving','validated','invalid')),
  validity_reason text,

  actual_origin_price numeric,
  actual_target_price numeric,
  effective_origin_date date,
  effective_target_date date,
  actual_return_pct numeric,
  actual_final_capital numeric,
  actual_total_pl numeric,
  actual_decision text,

  decision_match boolean,
  directional_match boolean,
  abs_return_error_pct numeric,
  abs_price_error numeric,
  abs_capital_error numeric,
  comparison_raw jsonb,

  created_at timestamptz not null default now(),
  resolved_at timestamptz,
  updated_at timestamptz not null default now(),

  constraint stock_predictions_dedup_key
    unique (symbol, prediction_origin_date, decision_horizon_days, target_date)
);
create index if not exists idx_stock_predictions_status_target on stock_predictions (status, target_date);
create index if not exists idx_stock_predictions_symbol on stock_predictions (symbol);
create index if not exists idx_stock_predictions_user on stock_predictions (user_id);
create index if not exists idx_stock_predictions_created on stock_predictions (created_at desc);

create table if not exists run_attempts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id),
  run_id text not null,
  mode text not null check (mode in ('stock_price_validation','options_strategy_validation')),
  submitted_at timestamptz not null default now(),
  input_hash text not null,
  outcome text not null check (outcome in ('stored_pending','stored_validated','duplicate_ignored','invalid')),
  linked_prediction_id uuid references stock_predictions(id)
);
create index if not exists idx_run_attempts_user_submitted on run_attempts (user_id, submitted_at desc);

create table if not exists resolver_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  candidates_count int,
  resolved_count int,
  invalid_count int,
  skipped_count int,
  error text
);
