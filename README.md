# Ruke Next.js Beast — Full Next.js (frontend + serverless APIs) using Supabase

Overview:
- Single Next.js app (pages router) with server-side API routes (pages/api/*) suitable for Vercel.
- Supabase JS for client & server. Use service role key only in server env vars on Vercel.

Quick start (local):
1. Copy `.env.local.example` -> `.env.local` and add your Supabase keys and JWT secret.
2. npm install
3. npm run dev
4. Open http://localhost:3000

Deploy to Vercel:
- Push repo to GitHub and import in Vercel. Add env vars in Vercel project settings:
  - NEXT_PUBLIC_SUPABASE_URL
  - NEXT_PUBLIC_SUPABASE_ANON_KEY
  - SUPABASE_SERVICE_KEY  (server only)
  - JWT_SECRET
  - STRIPE_SECRET_KEY  (optional)
