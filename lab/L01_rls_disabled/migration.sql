-- L01: RLS never enabled on public.customers (planted vulnerability).
CREATE TABLE public.customers (
  id uuid PRIMARY KEY,
  owner_id uuid NOT NULL,
  name text NOT NULL,
  email text NOT NULL
);
-- Intentionally NO "ALTER TABLE ... ENABLE ROW LEVEL SECURITY".
GRANT SELECT, INSERT, UPDATE, DELETE ON public.customers TO anon, authenticated;
