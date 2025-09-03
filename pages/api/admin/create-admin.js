// Utility: for initial setup only. Protect this route or delete after use.
const { getServerSupabase } = require('../../../lib/supabaseServer');
module.exports = async (req, res) => {
  if(req.method !== 'POST') return res.status(405).end();
  const { email } = req.body; if(!email) return res.status(400).json({ error: 'email required' });
  try{ const supabase = getServerSupabase(); const { data, error } = await supabase.from('users').update({ is_admin: true }).eq('email', email).select(); if(error) return res.status(500).json({ error: error.message }); res.json({ updated: data }); }catch(e){ res.status(500).json({ error: e.message }) }
}
