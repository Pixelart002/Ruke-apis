# Deploy to Koyeb (Docker)
1. Build locally to test:
   docker build -t ruke-store-backend:latest .
   docker run -e SUPABASE_URL=... -e SUPABASE_ANON_KEY=... -e SECRET_KEY=... -p 8000:8000 ruke-store-backend:latest
2. Push to a container registry (Docker Hub / GitHub Container Registry)
3. In Koyeb, create a new App using the pushed image. Set environment variables in the Koyeb dashboard (SUPABASE_URL, SUPABASE_ANON_KEY, SECRET_KEY).
4. Optional: Configure a startup command (default CMD is fine). Use HTTP health checks on /.
