# Deployment

Checklist and configuration reference for deploying Apprise to a production environment.

---

## Secret management — Doppler

Apprise uses [Doppler](https://doppler.com) to manage secrets. No `.env` files are committed or maintained manually — Doppler injects all variables at runtime.

### Setup (first time)

```bash
# Install Doppler CLI
brew install dopplerhq/cli/doppler   # macOS
# or: https://docs.doppler.com/docs/install-cli

doppler login
doppler setup   # select the apprise project and dev config
```

### Running locally

```bash
doppler run -- docker compose up --build
```

That's it. Doppler injects all variables into the Docker Compose environment, replacing the need for a root `.env` file.

### Fallback (no Doppler)

Copy `.env.example` to `.env` and fill in real values. Docker Compose reads `.env` automatically.

```bash
cp .env.example .env
# fill in values, then:
docker compose up --build
```

---

## Environment variables

One Doppler project (`apprise`) with configs per environment: `dev`, `staging`, `prod`.

### Required for all environments

| Variable | Consumer | Description |
|---|---|---|
| `POSTGRES_DB` | postgres, api, worker | Database name |
| `POSTGRES_USER` | postgres, api, worker | Database user |
| `POSTGRES_PASSWORD` | postgres, api, worker | Database password |
| `ANTHROPIC__API_KEY` | api, worker | Anthropic API key |
| `CLERK__SECRET_KEY` | api, frontend (via compose rename) | Clerk secret key — stored once in Doppler; `docker-compose.yml` maps it to `CLERK_SECRET_KEY` for the frontend (`@clerk/nextjs` expects the single-underscore form) |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | frontend | Clerk publishable key — browser-safe, non-secret |

### CORS

`CORS_ORIGINS` (api) — comma-separated allowed browser origins, e.g. `https://app.apprise.io`.
Leave unset if CORS is handled at the reverse proxy / edge layer.

### Clerk webhook

`CLERK__WEBHOOK_SECRET` (api) — Svix signing secret from Clerk dashboard.
Required for human JWT auth to work — see Clerk setup below.

---

## Clerk setup

> **Reminder:** Human user authentication (Bearer JWT) will return 401 until these steps are complete.
> The Clerk webhook populates the `organisations` and `users` tables — without it,
> `validate_clerk_token` finds no rows and rejects every request.
> See `docs/backend/api/clerk-identity-sync.md` for the full design.

### 1. Create a Clerk application

1. Sign in to [clerk.com](https://clerk.com) and create an application.
2. Enable **Organizations** under Configure → Organizations.
3. Copy the **Publishable Key** → `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` in Doppler.
4. Copy the **Secret Key** → `CLERK__SECRET_KEY` in Doppler (stored once; compose handles the rename).

### 2. Register the webhook endpoint

1. In the Clerk dashboard go to **Configure → Webhooks → Add Endpoint**.
2. Set the URL to `https://your-domain.com/webhooks/clerk`.
3. Subscribe to these events:
   - `organization.created`
   - `organization.deleted`
   - `user.created`
   - `user.deleted`
   - `organizationMembership.created`
   - `organizationMembership.deleted`
4. Save the endpoint and copy the **Signing Secret** (`whsec_...`) → `CLERK__WEBHOOK_SECRET` in Doppler.

### 3. Local development (no public URL)

Clerk cannot deliver webhooks to `localhost`. Two options:

**Option A — ngrok tunnel (recommended for realistic testing):**
```bash
ngrok http 8000
# Register the https://xxxx.ngrok.io/webhooks/clerk URL in Clerk dashboard
```

**Option B — seed script (quick, no tunnel needed):**
```bash
# Find your Clerk org ID and user ID in the Clerk dashboard
docker exec apprise-api-1 python /app/scripts/seed_dev.py \
  --clerk-org-id org_xxxx \
  --clerk-user-id user_xxxx
```
The seed script is idempotent — re-running with the same IDs reuses existing rows.

---

## `NEXT_PUBLIC_*` build-time constraint

Next.js bakes `NEXT_PUBLIC_*` variables into the JavaScript bundle **at build time**, not at container startup. In local dev this is not an issue — the frontend runs as a volume-mounted dev server and reads vars from the process environment at startup.

In **production** (static image build), `NEXT_PUBLIC_*` vars must be passed as Docker build args:

```bash
doppler run -- docker build \
  --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="$(doppler secrets get NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY --plain)" \
  -f frontend/Dockerfile ./frontend
```
`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` is non-secret (designed to be public) so baking it into the image is safe.

---

## Infrastructure

### Databases

| Service | Port | Notes |
|---|---|---|
| PostgreSQL 16 | 5432 | Source of truth. Alembic migrations run automatically at API startup. |
| Redis 7 | 6379 | ARQ job queue + event streams + API key cache. Append-only persistence enabled. |
| Qdrant 1.18 | 6333 | Vector memory store. |

### Application processes

| Service | Port | Notes |
|---|---|---|
| API (FastAPI) | 8000 | Single HTTP entry point. Runs Alembic migrations on startup. |
| Worker (ARQ) | — | Consumes Redis job queue. No HTTP surface. |
| Frontend (Next.js) | 3000 | Connects to API at `NEXT_PUBLIC_API_URL`. |

---

## First deploy checklist

- [ ] Doppler project `apprise` created with `dev` config populated
- [ ] `CLERK__WEBHOOK_SECRET` set in Doppler (requires Clerk webhook endpoint registered first)
- [ ] `doppler run -- docker compose up --build`
- [ ] Verify API health: `curl http://localhost:8000/health` → `{"status": "ok"}`
- [ ] Sign up via the frontend — Clerk fires `organization.created` and `user.created`
- [ ] Verify rows created: check `organisations` and `users` tables in Postgres
- [ ] Sign in and confirm workspaces page loads without 401

---

## Production considerations

- **CORS:** Set `CORS_ORIGINS` only if the API is directly browser-accessible. If behind nginx/ALB/Cloudflare, handle CORS at the proxy layer and leave `CORS_ORIGINS` unset.
- **Alembic:** Migrations run automatically at API startup (`alembic upgrade head`). Ensure the DB is healthy before the API container starts — the `depends_on` healthcheck in `docker-compose.yml` handles this in local Docker, but verify your production orchestrator does the same.
- **Secrets:** Never bake secrets into Docker images. All secrets flow through Doppler at runtime.
- **Worker scaling:** Multiple worker replicas are safe — ARQ handles job deduplication via Redis. API replicas are also safe — no in-process state survives a restart.
