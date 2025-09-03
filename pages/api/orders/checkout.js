const { getServerSupabase } = require('../../../lib/supabaseServer');
const { verify, getTokenFromHeader } = require('../../../utils/auth');
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY || '');
module.exports = async (req, res) => {
  if(req.method !== 'POST') return res.status(405).end();
  const token = getTokenFromHeader(req); if(!token) return res.status(401).json({ error: 'auth required' });
  try{
    const payload = verify(token); const supabase = getServerSupabase(); const userId = payload.sub;
    const { data: carts } = await supabase.from('carts').select('*').eq('user_id', userId).limit(1); const cart = carts && carts[0]; if(!cart) return res.status(400).json({ error: 'Cart empty' });
    const { data: items } = await supabase.from('cart_items').select('*, products(*)').eq('cart_id', cart.id);
    let total = 0; const orderItems = [];
    for(const it of items){ const prod = it.products; const price = parseFloat(prod.price); const qty = parseInt(it.quantity||1); total += price*qty; orderItems.push({ product_id: prod.id, quantity: qty, price }); }
    const { data: orderData, error: orderErr } = await supabase.from('orders').insert([{ user_id: userId, total, status: 'pending' }]).select();
    if(orderErr) return res.status(500).json({ error: orderErr.message });
    const order = orderData[0];
    for(const oi of orderItems){ await supabase.from('order_items').insert([{ order_id: order.id, product_id: oi.product_id, quantity: oi.quantity, price: oi.price }]); }
    await supabase.from('cart_items').delete().eq('cart_id', cart.id);
    let paymentIntent = null;
    if(process.env.STRIPE_SECRET_KEY){ paymentIntent = await stripe.paymentIntents.create({ amount: Math.round(total*100), currency: 'usd', metadata: { order_id: order.id } }); }
    const status = process.env.STRIPE_SECRET_KEY ? 'pending' : 'paid';
    await supabase.from('orders').update({ status }).eq('id', order.id);
    res.json({ order_id: order.id, total, payment: paymentIntent ? { client_secret: paymentIntent.client_secret } : null });
  }catch(e){ res.status(401).json({ error: 'invalid token' }) }
}
