const { getServerSupabase } = require('../../../lib/supabaseServer');
module.exports = async (req, res) => {
  const supabase = getServerSupabase();
  if(req.method === 'GET'){
    try{ const { data, error } = await supabase.from('products').select('*').order('created_at', { ascending: false }); if(error) return res.status(500).json({ error: error.message }); res.json(data || []); }catch(e){ res.status(500).json({ error: e.message }) }
  } else if(req.method === 'POST'){
    // require admin via token
    const token = (req.headers.authorization || '').split(' ')[1];
    const { verify } = require('../../../utils/auth');
    try{ const payload = verify(token); if(!payload.is_admin) return res.status(403).json({ error: 'admin required' }); }catch(e){ return res.status(401).json({ error: 'invalid token' }); }
    const body = req.body;
    try{ const { data, error } = await supabase.from('products').insert([body]).select(); if(error) return res.status(500).json({ error: error.message }); res.json(data[0]); }catch(e){ res.status(500).json({ error: e.message }) }
  } else { res.status(405).end(); }
}
