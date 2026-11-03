// Hand-written imitation of a bundled supabase-js app (lab only).
const supabase = createClient("http://127.0.0.1:54321", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0");

async function load() {
  const { data } = await supabase.from('todos').select('*');
  document.getElementById("app").textContent = JSON.stringify(data);
}
load();
