-- C03: control. Empty table; SELECT owner-scoped; no write policies (backend-only writes).
create table public.announcements (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  body text
);
alter table public.announcements enable row level security;

grant select, insert, update, delete on public.announcements to anon, authenticated;

create policy announcements_select on public.announcements for select to authenticated
  using (owner_id = auth.uid());
