-- Row-Level Security. Not enforced yet in Phase 1 (the app writes through the
-- service-role/direct Postgres connection, which bypasses RLS) -- this is set
-- up now so Phase 3 (real Supabase Auth + PostgREST from the React app) works
-- without a schema change. Idempotent: safe to re-run.

alter table profiles enable row level security;
alter table stock_predictions enable row level security;
alter table run_attempts enable row level security;

drop policy if exists profiles_select_own on profiles;
create policy profiles_select_own on profiles
  for select using (auth.uid() = id);

drop policy if exists profiles_update_own on profiles;
create policy profiles_update_own on profiles
  for update using (auth.uid() = id);

drop policy if exists stock_predictions_select_team on stock_predictions;
create policy stock_predictions_select_team on stock_predictions
  for select using (auth.role() = 'authenticated');

drop policy if exists stock_predictions_insert_own on stock_predictions;
create policy stock_predictions_insert_own on stock_predictions
  for insert with check (auth.uid() = user_id);

drop policy if exists run_attempts_select_team on run_attempts;
create policy run_attempts_select_team on run_attempts
  for select using (auth.role() = 'authenticated');

drop policy if exists run_attempts_insert_own on run_attempts;
create policy run_attempts_insert_own on run_attempts
  for insert with check (auth.uid() = user_id);

-- resolver_runs and UPDATEs on stock_predictions are service-role/admin only --
-- no end-user policy is added for them, so they stay inaccessible via
-- PostgREST to anon/authenticated roles by default once RLS is enabled.
