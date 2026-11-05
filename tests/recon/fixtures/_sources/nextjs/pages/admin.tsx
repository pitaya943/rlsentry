import { useEffect, useState } from "react";
import { admin } from "@/lib/admin";
export default function Admin() {
  const [rows, setRows] = useState<unknown[]>([]);
  useEffect(() => { admin.rpc("list_all_users").then(r => setRows(r.data ?? [])); }, []);
  return <pre>{JSON.stringify(rows)}</pre>;
}
