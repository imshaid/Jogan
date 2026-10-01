# Jogan web app

Next.js (App Router) front end for Jogan. It signs users in with Supabase Auth and talks to the
Jogan API with the user's token; the API and the database decide what each role may do.

```bash
npm ci
cp ../.env.example .env.local   # keep only the NEXT_PUBLIC_* lines and fill them in
npm run dev                     # http://localhost:3000
npm run lint
npm run build
```

Environment variables (all public, baked in at build time):

| Name | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Jogan API, e.g. the Cloud Run URL or `http://localhost:8000` |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase publishable key (browser-safe, RLS applies) |
| `NEXT_PUBLIC_DEMO_PASSWORD` | Optional: shows one-click demo sign-in buttons |

On Vercel the project's root directory is `web/`.
