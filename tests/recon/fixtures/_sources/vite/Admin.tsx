import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";
// mistake planted for the fixture: service_role key in a lazily loaded admin view
const admin = createClient(import.meta.env.VITE_SUPABASE_URL, import.meta.env.VITE_SUPABASE_SERVICE_ROLE_KEY);
export default function Admin() {
  const [rows, setRows] = useState<unknown[]>([]);
  useEffect(() => { admin.from("profiles").select("*").then(r => setRows(r.data ?? [])); }, []);
  return <pre>{JSON.stringify(rows)}</pre>;
}
