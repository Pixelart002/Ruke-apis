const bcrypt = require('bcryptjs');
const { getServerSupabase } = require('../../../lib/supabaseServer');
const { sign } = require('../../../utils/auth');
module.exports = async (req, res) => {
  if(req.method !== 'POST') return res.status(405).end();
  const supabase = getServerSupabase();
  const { email, password } = req.body;
  if(!email || !password) return res.status(400).json({ error: 'email and password required' });
  try{
    const { data } = await supabase.from('users').select('*').eq('email', email).limit(1);
    const user = data && data[0];
    if(!user) return res.status(401).json({ error: 'invalid credentials' });
    const ok = await bcrypt.compare(password, user.password);
    if(!ok) return res.status(401).json({ error: 'invalid credentials' });
    const token = sign({ sub: user.id, is_admin: user.is_admin });
    res.json({ token, user: { id: user.id, email: user.email, username: user.username, is_admin: user.is_admin } });
  }catch(e){ res.status(500).json({ error: e.message }) }
}
