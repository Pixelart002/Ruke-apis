const { getServerSupabase } = require('../../../lib/supabaseServer');
module.exports = async (req, res) => {
  const supabase = getServerSupabase();
  const id = req.query.id;
  if(req.method === 'GET'){
    const { data } = await supabase.from('products').select('*').eq('id', id).limit(1); if(!data || !data[0]) return res.status(404).json({ error: 'Not found' }); res.json(data[0]);
  } else if(req.method === 'DELETE'){
    const token = (req.headers.authorization || '').split(' ')[1];
    const { verify } = require('../../../utils/auth');
    try{ const payload = verify(token); if(!payload.is_admin) return res.status(403).json({ error: 'admin required' }); }catch(e){ return res.status(401).json({ error: 'invalid token' }); }
    const { data, error } = await supabase.from('products').delete().eq('id', id).select();
    if(error) return res.status(500).json({ error: error.message }); res.json({ deleted: true });
  } else res.status(405).end();
}
