-- L05: UPDATE policy has WITH CHECK (true), so owner_id can be transferred to someone else.
CREATE TABLE public.projects (
  id uuid PRIMARY KEY,
  owner_id uuid NOT NULL,
  created_by uuid NOT NULL,
  name text NOT NULL
);

ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.projects TO anon, authenticated;

CREATE POLICY projects_select ON public.projects FOR SELECT TO authenticated
  USING (owner_id = auth.uid() OR created_by = auth.uid());
CREATE POLICY projects_insert ON public.projects FOR INSERT TO authenticated
  WITH CHECK (owner_id = auth.uid() AND created_by = auth.uid());
-- planted flaw: WITH CHECK (true)
CREATE POLICY projects_update ON public.projects FOR UPDATE TO authenticated
  USING (owner_id = auth.uid()) WITH CHECK (true);
CREATE POLICY projects_delete ON public.projects FOR DELETE TO authenticated
  USING (owner_id = auth.uid());
