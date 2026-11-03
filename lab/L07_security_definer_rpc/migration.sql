-- L07: RLS-protected table plus a SECURITY DEFINER RPC that bypasses RLS.
CREATE TABLE public.accounts (
  id uuid PRIMARY KEY,
  owner_id uuid NOT NULL,
  balance numeric NOT NULL
);
ALTER TABLE public.accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY accounts_select ON public.accounts FOR SELECT TO authenticated
  USING (owner_id = auth.uid());
CREATE POLICY accounts_insert ON public.accounts FOR INSERT TO authenticated
  WITH CHECK (owner_id = auth.uid());
CREATE POLICY accounts_update ON public.accounts FOR UPDATE TO authenticated
  USING (owner_id = auth.uid()) WITH CHECK (owner_id = auth.uid());
CREATE POLICY accounts_delete ON public.accounts FOR DELETE TO authenticated
  USING (owner_id = auth.uid());

-- Planted: runs as owner postgres, returns every row regardless of RLS.
CREATE FUNCTION public.get_all_accounts() RETURNS SETOF public.accounts
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
  AS $$ SELECT * FROM public.accounts $$;

-- Control: executable by anon but returns no rows.
CREATE FUNCTION public.ping_definer() RETURNS integer
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
  AS $$ SELECT 1 $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.accounts TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_all_accounts() TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ping_definer() TO anon, authenticated;
