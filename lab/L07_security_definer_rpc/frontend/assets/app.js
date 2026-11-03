import { createClient } from "@supabase/supabase-js";

const supabase = createClient("http://127.0.0.1:54321", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0");

async function load() {
  const all = await supabase.rpc('get_all_accounts');
  const ping = await supabase.rpc('ping_definer');
  const mine = await supabase.from('accounts').select('id, owner_id, balance');
  document.getElementById("root").textContent = JSON.stringify([all.data, ping.data, mine.data]);
}
load();
