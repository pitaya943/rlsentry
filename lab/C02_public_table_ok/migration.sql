-- C02: correct public table. Published rows are world-readable; writes are owner-scoped.
create table public.articles (
  id uuid primary key default gen_random_uuid(),
  author_id uuid not null,
  title text,
  is_published boolean not null default false
);
alter table public.articles enable row level security;

grant select, insert, update, delete on public.articles to anon, authenticated;

create policy articles_select on public.articles for select
  using (is_published or author_id = auth.uid());
create policy articles_insert on public.articles for insert to authenticated
  with check (author_id = auth.uid());
create policy articles_update on public.articles for update to authenticated
  using (author_id = auth.uid()) with check (author_id = auth.uid());
create policy articles_delete on public.articles for delete to authenticated
  using (author_id = auth.uid());
