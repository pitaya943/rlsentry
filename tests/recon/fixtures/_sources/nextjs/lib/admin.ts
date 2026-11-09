import { createClient } from "@supabase/supabase-js";
// mistake planted for the fixture: service_role key exposed through NEXT_PUBLIC_
export const admin = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_SERVICE_KEY!);
