-- C01: control. Every operation is owner-scoped and limited to authenticated; anon has no policy.
create table public.todos (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  title text
);
alter table public.todos enable row level security;

grant select, insert, update, delete on public.todos to anon, authenticated;

create policy todos_select on public.todos for select to authenticated
  using (owner_id = auth.uid());
create policy todos_insert on public.todos for insert to authenticated
  with check (owner_id = auth.uid());
create policy todos_update on public.todos for update to authenticated
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy todos_delete on public.todos for delete to authenticated
  using (owner_id = auth.uid());
