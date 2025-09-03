const { getServerSupabase } = require('../../../lib/supabaseServer');
const { verify, getTokenFromHeader } = require('../../../utils/auth');
module.exports = async (req, res) => {
  if(req.method !== 'POST') return res.status(405).end();
  const token = getTokenFromHeader(req); if(!token) return res.status(401).json({ error: 'auth required' });
  try{ const payload = verify(token); const supabase = getServerSupabase(); const userId = payload.sub; const { product_id, quantity } = req.body;
    const { data: carts } = await supabase.from('carts').select('*').eq('user_id', userId).limit(1); let cart = carts && carts[0];
    if(!cart){ const { data: newc } = await supabase.from('carts').insert([{ user_id: userId }]).select(); cart = newc[0]; }
    const { data, error } = await supabase.from('cart_items').insert([{ cart_id: cart.id, product_id, quantity: quantity || 1 }]).select();
    if(error) return res.status(500).json({ error: error.message }); res.json({ cart_id: cart.id, item: data[0] });
  }catch(e){ res.status(401).json({ error: 'invalid token' }) }
}
