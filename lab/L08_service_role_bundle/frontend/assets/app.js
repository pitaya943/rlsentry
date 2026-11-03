import { createClient } from "@supabase/supabase-js";

// admin client (src/admin.ts): service_role demo key bundled by mistake
const admin = createClient("http://127.0.0.1:54321", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU");
// public client (src/client.ts): anon key
const supabase = createClient("http://127.0.0.1:54321", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0");

async function load() {
  const { data } = await supabase.from('orders').select('*');
  const { count } = await admin.from('orders').select('id', { count: 'exact', head: true });
  document.getElementById("app").textContent = JSON.stringify({ data, count });
}
load();
