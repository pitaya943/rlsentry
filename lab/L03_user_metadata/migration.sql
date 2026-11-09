-- L03: authorization based on user_metadata (user-editable). Planted vulnerability.
CREATE TABLE public.reports (
  id uuid PRIMARY KEY,
  owner_id uuid NOT NULL,
  title text NOT NULL
);
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;

CREATE POLICY reports_select ON public.reports
  FOR SELECT TO authenticated
  USING (owner_id = auth.uid()
         OR (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin');
