import { lazy, Suspense, useEffect, useState } from "react";
import { supabase } from "./supabase";
const Reports = lazy(() => import("./Reports"));
export default function App() {
  const [show, setShow] = useState(false);
  const [n, setN] = useState(null);
  useEffect(() => { supabase.from("invoices").select("id", { count: "exact", head: true }).then(r => setN(r.count)); }, []);
  return <main><h1>Invoices {n}</h1><button onClick={() => setShow(true)}>reports</button>
    {show && <Suspense fallback={null}><Reports /></Suspense>}</main>;
}
