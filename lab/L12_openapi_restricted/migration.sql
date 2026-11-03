-- L12: OpenAPI disabled; diary_entries has a correct authenticated policy plus a leaky anon policy.
create table public.diary_entries (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  body text
);
alter table public.diary_entries enable row level security;
grant select, insert, update, delete on public.diary_entries to anon, authenticated;

create policy diary_select_own on public.diary_entries for select to authenticated
  using (owner_id = auth.uid());
create policy diary_select_anon on public.diary_entries for select to anon using (true);

-- RLS on, no policy at all: nobody can read it.
create table public.audit_log (
  id uuid primary key default gen_random_uuid(),
  actor_id uuid,
  action text
);
alter table public.audit_log enable row level security;
grant select, insert, update, delete on public.audit_log to anon, authenticated;

alter role authenticator set pgrst.openapi_mode = 'disabled';
notify pgrst, 'reload config';
notify pgrst, 'reload schema';
