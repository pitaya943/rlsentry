-- C04: control. Owner-scoped SELECT only; user_b has no rows.
CREATE TABLE public.subscriptions (
  id uuid PRIMARY KEY,
  owner_id uuid NOT NULL,
  plan text NOT NULL
);
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.subscriptions TO anon, authenticated;
CREATE POLICY subscriptions_select_own ON public.subscriptions
  FOR SELECT TO authenticated USING (owner_id = auth.uid());
