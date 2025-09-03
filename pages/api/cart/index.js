const { getServerSupabase } = require('../../../lib/supabaseServer');
const { verify, getTokenFromHeader } = require('../../../utils/auth');
module.exports = async (req, res) => {
  if(req.method !== 'GET') return res.status(405).end();
  const token = getTokenFromHeader(req); if(!token) return res.status(401).json({ error: 'auth required' });
  try{ const payload = verify(token); const supabase = getServerSupabase(); const userId = payload.sub;
    const { data: carts } = await supabase.from('carts').select('*').eq('user_id', userId).limit(1); const cart = carts && carts[0]; if(!cart) return res.json({ items: [] });
    const { data: items } = await supabase.from('cart_items').select('*, products(*)').eq('cart_id', cart.id); res.json({ cart, items });
  }catch(e){ res.status(401).json({ error: 'invalid token' }) }
}
