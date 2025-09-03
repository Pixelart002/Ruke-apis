const { createClient } = require('@supabase/supabase-js');
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY;
if(!SUPABASE_URL || !SUPABASE_SERVICE_KEY){
  // don't throw here to allow local readonly ops with anon key
}
let supabase = null;
function getServerSupabase(){
  if(supabase) return supabase;
  if(!SUPABASE_URL || !SUPABASE_SERVICE_KEY){
    // fallback to anon client if service key missing (not recommended in prod)
    const { createClient } = require('@supabase/supabase-js');
    supabase = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);
  } else {
    supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);
  }
  return supabase;
}
module.exports = { getServerSupabase };
