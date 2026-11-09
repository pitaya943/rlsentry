import { lazy, Suspense, useEffect, useState } from "react";
import { supabase } from "./supabase";
const Admin = lazy(() => import("./Admin"));
export default function App() {
  const [show, setShow] = useState(false);
  const [n, setN] = useState<number | null>(null);
  useEffect(() => { supabase.from("todos").select("id", { count: "exact", head: true }).then(r => setN(r.count)); }, []);
  return <main><h1>Todos {n}</h1><button onClick={() => setShow(true)}>admin</button>
    {show && <Suspense fallback={null}><Admin /></Suspense>}</main>;
}
