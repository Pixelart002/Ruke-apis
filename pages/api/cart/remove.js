const { getServerSupabase } = require('../../../lib/supabaseServer');
const { verify, getTokenFromHeader } = require('../../../utils/auth');
module.exports = async (req, res) => {
  if(req.method !== 'POST') return res.status(405).end();
  const token = getTokenFromHeader(req); if(!token) return res.status(401).json({ error: 'auth required' });
  try{ const payload = verify(token); const supabase = getServerSupabase();
    const { item_id } = req.body; if(!item_id) return res.status(400).json({ error: 'item_id required' });
    const { error } = await supabase.from('cart_items').delete().eq('id', item_id).select();
    if(error) return res.status(500).json({ error: error.message }); res.json({ removed: true });
  }catch(e){ res.status(401).json({ error: 'invalid token' }) }
}
