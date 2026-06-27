# Clerk Identity Sync

## Why this exists

Apprise uses Clerk for human user authentication but deliberately decouples its data model
from Clerk's string IDs. Every internal table (`workspaces`, `tasks`, `agents`, `api_keys`)
uses UUID foreign keys that point to `organisations.id` and `users.id` — Apprise's own
primary keys. Clerk's identifiers (`org_3Fj...`, `user_2abc...`) are stored only in
`organisations.external_id` and `users.external_id`.

This means:
- Swapping Clerk for another auth provider only changes the auth layer, not the data model.
- No migrations on workspaces, tasks, or agents if the identity provider changes.
- All access control compares internal UUIDs (`ws.organisation_id == auth.org_id`), never
  provider strings.

The trade-off is that Apprise must maintain a local copy of Clerk's identity data.
The Clerk webhook handler is the sync mechanism that keeps them in line.

---

## Two-step Bearer JWT auth flow

Every request with `Authorization: Bearer <jwt>` goes through two steps in `AuthMiddleware`:

```
1. JWT signature check
   └─ clerk.authenticate_request_async() verifies the token locally against
      Clerk's cached public JWKS. No network call per request. Fast.
      Extracts: org_id ("org_3Fj..."), sub ("user_2abc...") from claims.

2. ID resolution  ← this is what breaks without the webhook handler
   └─ validate_clerk_token() queries:
        organisations WHERE identity_provider='clerk' AND external_id='org_3Fj...'
        users           WHERE identity_provider='clerk' AND external_id='user_2abc...'
      Returns: UserPayload(org_id=<internal UUID>, user_id=<internal UUID>)
      Sets:    request.state.auth = UserPayload(...)
```

Step 2 fails with 401 if the org or user row doesn't exist. Nothing creates these rows
except the webhook handler (or `scripts/seed_dev.py` for local dev without a public URL).

---

## Webhook handler — `POST /webhooks/clerk`

Receives Clerk lifecycle events via Svix. Exempt from `AuthMiddleware` (uses Svix HMAC
inbound verification instead of bearer/API-key outbound auth).

### Svix verification

Every Clerk webhook delivery is signed by Svix with three headers:
- `svix-id` — unique delivery ID
- `svix-timestamp` — delivery time (used to reject replays older than 5 minutes)
- `svix-signature` — HMAC-SHA256 of `"{svix-id}.{svix-timestamp}.{body}"`

The `svix` SDK `Webhook(secret).verify(body_bytes, headers)` checks both the signature
and the timestamp window. Configure the secret (`whsec_...`) in the Clerk dashboard under
**Webhooks → your endpoint → Signing Secret** and set `CLERK__WEBHOOK_SECRET` in `.env`.

Without this verification, anyone could POST a fabricated `organization.created` event
and create arbitrary org rows in the DB.

### Events handled

| Event | Apprise action |
|---|---|
| `organization.created` | Upsert `Organisation(identity_provider='clerk', external_id=data.id, name=data.name)` |
| `organization.deleted` | Delete `Organisation WHERE external_id=data.id` (cascades to workspaces, members, tasks) |
| `user.created` | Upsert `User(identity_provider='clerk', external_id=data.id, email=data.email_addresses[0].email_address, name=data.first_name + last_name)` |
| `user.deleted` | Delete `User WHERE external_id=data.id` |
| `organizationMembership.created` | Upsert `OrganisationMember(organisation_id=..., user_id=..., role=data.role)` |
| `organizationMembership.deleted` | Delete `OrganisationMember WHERE organisation_id=... AND user_id=...` |

Unknown event types return `200` silently — Clerk sends many event types we don't care
about (`session.created`, `email.created`, etc.) and returning non-2xx causes Svix to retry.

### Payload structure

Clerk webhooks share a common envelope:
```json
{ "type": "organization.created", "data": { ... }, "object": "event" }
```

The handler parses only the `type` and the specific fields it needs from `data`. We do not
model Clerk's full payload schema — that would couple us to Clerk's versioning. The
`data` field is treated as `dict[str, Any]` and mined selectively per event type.

---

## Membership rows

`OrganisationMember` rows are not currently used for access control — `require_workspace`
checks `ws.organisation_id == auth.org_id`, not membership. They are synced because:
1. The model exists with FK constraints and must not drift from Clerk.
2. Role-based access (gap #12) will use them when implemented.

---

## Local dev without a public webhook URL

Clerk cannot deliver webhooks to `localhost`. Use `scripts/seed_dev.py` to manually create
the org/user/workspace rows:

```bash
docker exec apprise-api-1 python /app/scripts/seed_dev.py \
  --clerk-org-id org_3Fj...   \
  --clerk-user-id user_2abc...
```

Find the IDs in the Clerk dashboard under **Organizations** and **Users**. The script is
idempotent — re-running with the same IDs reuses existing rows and only creates a new API key.

For a public webhook URL in dev, use `ngrok http 8000` and register the tunnel URL in the
Clerk dashboard under **Webhooks**.
