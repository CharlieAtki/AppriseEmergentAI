# Centrifugo config notes

`config.json` holds the structural, non-secret config (engine, proxy endpoints).
Secrets and environment-specific values are passed via env vars in
`docker-compose.yml`, using Centrifugo's own env-var override convention
(`CENTRIFUGO_<DOTTED_PATH_UPPERCASE>` maps onto the equivalent JSON key):

- `CENTRIFUGO_HTTP_API_KEY` → `http_api.key`
- `CENTRIFUGO_CLIENT_ALLOWED_ORIGINS` → `client.allowed_origins`
- `CENTRIFUGO_CLIENT_PROXY_CONNECT_STATIC_HTTP_HEADERS` / equivalent → the
  `X-Centrifugo-Proxy-Secret` header value the connect/subscribe proxy calls
  attach, checked by `require_centrifugo_proxy_secret()` in `backend/api/api/deps.py`

**Unverified — confirm before first real deploy**, per the migration plan
(`C:\Users\juzat\.claude\plans\i-trhink-we-should-elegant-glade.md`):

- The exact env-var-to-config-key mapping syntax (dotted-path vs underscore
  convention) for nested keys like `client.proxy.connect.endpoint` and the
  static-header fields — verify against the Centrifugo version actually
  deployed via `centrifugo genconfig` or the config reference page for that
  version, since config schema has changed across major versions.
- Whether `static_http_headers` (or an equivalently-named field) is the
  correct way to attach a fixed shared-secret header to every proxy call, as
  opposed to some other mechanism (e.g. a query param or a different config
  key entirely).
- The exact `include_connection_meta` key path shown above — confirmed the
  *feature* exists (connect-time `meta` can forward into subscribe-proxy
  requests), but the precise config key nesting shown here is a best-effort
  reconstruction from docs, not copy-pasted from a working example.

None of this is required to be perfect before local dev testing — Centrifugo
will fail fast with a clear config error on an unrecognized key, which is the
first thing `docker-compose up`'s healthcheck will surface (see Verification
step 1 in the migration plan).
