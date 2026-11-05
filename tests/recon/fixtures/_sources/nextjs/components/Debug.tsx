// lazily loaded debug panel; a developer pasted their own session token here (unverified key)
const DEBUG_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ4dHJuZXh0anNmaXh0dXJlMDAwMSIsInJvbGUiOiJhdXRoZW50aWNhdGVkIiwic3ViIjoiMDAwMDAwMDAtMDAwMC00MDAwLTgwMDAtMDAwMDAwMDBmMDAxIiwiZXhwIjoyMDAwMDAwMDAwfQ.j1aVW5Z4Umm3JXQqbf3yyueXJqZVOkxkEAB7r3si2bY";
export default function Debug() { return <code title={DEBUG_TOKEN}>debug</code>; }
