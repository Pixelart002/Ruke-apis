const { getServerSupabase } = require('../../../lib/supabaseServer');
const { verify, getTokenFromHeader } = require('../../../utils/auth');
module.exports = async (req, res) => {
  if(req.method !== 'GET') return res.status(405).end();
  const token = getTokenFromHeader(req); if(!token) return res.status(401).json({ error: 'auth required' });
  try{ const payload = verify(token); if(!payload.is_admin) return res.status(403).json({ error: 'admin required' }); const supabase = getServerSupabase(); const { data } = await supabase.from('orders').select('*, order_items(*)').order('created_at', { ascending: false }); res.json(data || []); }catch(e){ res.status(401).json({ error: 'invalid token' }) }
}
