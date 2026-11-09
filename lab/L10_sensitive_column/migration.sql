-- L10: row-level policy is correct, but the public rows expose an email column (sensitive column).
create table public.public_profiles (
  id uuid primary key,
  user_id uuid not null,
  display_name text,
  email text,
  is_public boolean not null default false
);
alter table public.public_profiles enable row level security;
grant select, insert, update, delete on public.public_profiles to anon, authenticated;

create policy pp_select on public.public_profiles for select to anon, authenticated
  using (is_public or user_id = auth.uid());
create policy pp_insert on public.public_profiles for insert to authenticated
  with check (user_id = auth.uid());
create policy pp_update on public.public_profiles for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy pp_delete on public.public_profiles for delete to authenticated
  using (user_id = auth.uid());
