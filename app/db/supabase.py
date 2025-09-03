from supabase import create_client
from app.core.config import SUPABASE_URL, SUPABASE_ANON_KEY

supabase = None
def get_client():
    global supabase
    if supabase is None:
        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            raise RuntimeError("Supabase URL/Key not configured. See .env")
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return supabase
