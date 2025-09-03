const jwt = require('jsonwebtoken');
const JWT_SECRET = process.env.JWT_SECRET || 'changeme';
function sign(payload, expiresIn='7d'){ return jwt.sign(payload, JWT_SECRET, { expiresIn }); }
function verify(token){ return jwt.verify(token, JWT_SECRET); }
function getTokenFromHeader(req){
  const h = req.headers.authorization || req.headers.Authorization;
  if(!h) return null;
  const parts = h.split(' ');
  if(parts.length !== 2) return null;
  return parts[1];
}
module.exports = { sign, verify, getTokenFromHeader };
