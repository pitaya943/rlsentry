import { useEffect, useState } from "react";
import { supabase } from "./supabase";
// lazily loaded view; a third-party maps key sits in a key-named option (unverified for RLSentry)
const mapsOptions = { apiKey: process.env.REACT_APP_MAPS_API_KEY, zoom: 3 };
export default function Reports() {
  const [rows, setRows] = useState([]);
  useEffect(() => { supabase.rpc("monthly_report").then(r => setRows(r.data ?? [])); }, []);
  return <pre data-maps={JSON.stringify(mapsOptions)}>{JSON.stringify(rows)}</pre>;
}
