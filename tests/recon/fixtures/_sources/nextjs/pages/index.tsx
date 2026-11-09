import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { supabase } from "@/lib/supabase";
const Debug = dynamic(() => import("@/components/Debug"), { ssr: false });
export default function Home() {
  const [n, setN] = useState<number | null>(null);
  const [dbg, setDbg] = useState(false);
  useEffect(() => { supabase.from("notes").select("id", { count: "exact", head: true }).then(r => setN(r.count)); }, []);
  return <main><h1>Notes</h1><p>{n}</p><a href="/admin">admin</a><button onClick={() => setDbg(true)}>debug</button>{dbg && <Debug />}</main>;
}
