-- L02: SELECT policy is USING (true); write policies are owner-scoped.
create table public.messages (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  body text
);
alter table public.messages enable row level security;

grant select, insert, update, delete on public.messages to anon, authenticated;

create policy messages_select on public.messages for select using (true);
create policy messages_insert on public.messages for insert to authenticated
  with check (owner_id = auth.uid());
create policy messages_update on public.messages for update to authenticated
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy messages_delete on public.messages for delete to authenticated
  using (owner_id = auth.uid());
