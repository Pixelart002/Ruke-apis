const { getServerSupabase } = require('../../../lib/supabaseServer');
const { verify, getTokenFromHeader } = require('../../../utils/auth');
module.exports = async (req, res) => {
  if(req.method !== 'GET') return res.status(405).end();
  const token = getTokenFromHeader(req); if(!token) return res.status(401).json({ error: 'auth required' });
  try{ const payload = verify(token); const supabase = getServerSupabase(); const userId = payload.sub;
    const { data } = await supabase.from('orders').select('*, order_items(*)').eq('user_id', userId).order('created_at', { ascending: false }); res.json(data || []);
  }catch(e){ res.status(401).json({ error: 'invalid token' }) }
}
