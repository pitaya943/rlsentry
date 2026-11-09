-- L08: RLS on orders is correct; the planted issue is a service_role key in the frontend bundle.
create table public.orders (
  id uuid primary key,
  owner_id uuid not null,
  item text
);
alter table public.orders enable row level security;
grant select, insert, update, delete on public.orders to anon, authenticated;

create policy orders_select on public.orders for select to authenticated
  using (owner_id = auth.uid());
create policy orders_insert on public.orders for insert to authenticated
  with check (owner_id = auth.uid());
create policy orders_update on public.orders for update to authenticated
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy orders_delete on public.orders for delete to authenticated
  using (owner_id = auth.uid());
