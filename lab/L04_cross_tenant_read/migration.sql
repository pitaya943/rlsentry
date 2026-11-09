-- L04: SELECT policy only checks login, not ownership (planted vulnerability).
create table public.notes (
  id uuid primary key,
  owner_id uuid not null,
  body text
);
alter table public.notes enable row level security;
grant select, insert, update, delete on public.notes to anon, authenticated;

create policy notes_select on public.notes for select to authenticated
  using (auth.uid() is not null);
create policy notes_insert on public.notes for insert to authenticated
  with check (owner_id = auth.uid());
create policy notes_update on public.notes for update to authenticated
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy notes_delete on public.notes for delete to authenticated
  using (owner_id = auth.uid());
