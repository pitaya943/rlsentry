-- L09: INSERT policy WITH CHECK (true) for anon and authenticated; table is insert-only.
CREATE TABLE public.feedback (
  id uuid PRIMARY KEY,
  owner_id uuid,
  body text
);

ALTER TABLE public.feedback ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.feedback TO anon, authenticated;

CREATE POLICY feedback_select ON public.feedback FOR SELECT TO authenticated
  USING (owner_id = auth.uid());
-- planted flaw: anyone may insert any row
CREATE POLICY feedback_insert ON public.feedback FOR INSERT TO anon, authenticated
  WITH CHECK (true);
