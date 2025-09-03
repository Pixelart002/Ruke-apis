const bcrypt = require('bcryptjs');
const { getServerSupabase } = require('../../../lib/supabaseServer');
const { sign } = require('../../../utils/auth');
module.exports = async (req, res) => {
  if(req.method !== 'POST') return res.status(405).end();
  const supabase = getServerSupabase();
  const { username, email, password } = req.body;
  if(!email || !password) return res.status(400).json({ error: 'email and password required' });
  try{
    const { data: existing } = await supabase.from('users').select('id').eq('email', email).limit(1);
    if(existing && existing.length) return res.status(400).json({ error: 'email exists' });
    const hashed = await bcrypt.hash(password, 10);
    const { data, error } = await supabase.from('users').insert([{ username, email, password: hashed, is_admin:false }]).select();
    if(error) return res.status(500).json({ error: error.message });
    const user = data[0];
    const token = sign({ sub: user.id, is_admin: user.is_admin });
    res.json({ token, user: { id: user.id, email: user.email, username: user.username, is_admin: user.is_admin } });
  }catch(e){ res.status(500).json({ error: e.message }) }
}
