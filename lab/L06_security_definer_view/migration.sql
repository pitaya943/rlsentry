-- L06: RLS-protected table plus a view that runs with its owner's rights (bypasses RLS).
CREATE TABLE public.invoices (
  id uuid PRIMARY KEY,
  owner_id uuid NOT NULL,
  amount numeric NOT NULL
);
ALTER TABLE public.invoices ENABLE ROW LEVEL SECURITY;

CREATE POLICY invoices_select ON public.invoices FOR SELECT TO authenticated
  USING (owner_id = auth.uid());
CREATE POLICY invoices_insert ON public.invoices FOR INSERT TO authenticated
  WITH CHECK (owner_id = auth.uid());
CREATE POLICY invoices_update ON public.invoices FOR UPDATE TO authenticated
  USING (owner_id = auth.uid()) WITH CHECK (owner_id = auth.uid());
CREATE POLICY invoices_delete ON public.invoices FOR DELETE TO authenticated
  USING (owner_id = auth.uid());

-- Planted: no security_invoker, so the view executes as its creator (postgres, bypasses RLS).
CREATE VIEW public.invoice_summary AS
  SELECT id, owner_id, amount FROM public.invoices;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.invoices TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.invoice_summary TO anon, authenticated;
