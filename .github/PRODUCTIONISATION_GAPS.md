# Productionisation Gaps

Items explicitly deferred during hardening and CI setup. Each entry records what was decided, why it was deferred, and what completing it requires.

---

## Tooling & CI

### 1. mypy / static type checking

**Status:** Done. Permissive config (`ignore_missing_imports = true`, `check_untyped_defs = false`) added to all three `pyproject.toml` files. Three mypy steps added to the `lint` job in `ci.yml`. Next step: tighten per-module — coordination and eventing are clean enough for strict now.

---

### 2. ANN ruff rules (annotation completeness enforcement)

**Status:** Done. `ANN` added to `ruff.toml` with `ANN401` suppressed and per-file ignores for `models/` and `tests/`. All 25 violations fixed across `api/`, `core/`, and `worker/` in a single pass.

---

### 3. Security scanning

**Status:** Done. Bandit SAST in pre-commit and `ci.yml`; Trivy image scans in `build.yml` after each image push. HIGH/CRITICAL block the build; results upload to GitHub Security tab as SARIF.

---

### 4. E2E / docker-compose tests in CI

**Status:** Not configured. Only unit and in-process integration tests run in CI.

**Why deferred:** Running Postgres + Redis + Qdrant as GitHub Actions service containers adds meaningful complexity and significantly increases CI runtime.

**What completing it requires:**
- Add service containers to `ci.yml` for postgres (16-alpine), redis (7-alpine), and qdrant (v1.18.1)
- Write a `tests/e2e/` directory in `worker/` that tests full job flows against real infrastructure
- The env vars in `conftest.py` already point at localhost — the service containers expose the same ports, so no code changes are needed for the test client setup
- Separate job in CI (e.g. `e2e`) that only runs on PRs targeting `main`, not on every push to a feature branch

---

### 5. Deployment workflow

**Status:** Not configured. `build.yml` builds and pushes images to GHCR but nothing deploys them.

**Why deferred:** Target infrastructure (ECS, Kubernetes, Fly.io, etc.) is unknown.

**What completing it requires:**
- A `deploy.yml` workflow triggered after `build.yml` succeeds on `main`
- Deployment strategy depends on infra: `kubectl set image` for Kubernetes, `aws ecs update-service` for ECS, etc.
- Secrets for the target platform stored in GitHub Actions environment secrets (not repo secrets — use environment-scoped secrets for staging vs prod separation)
- Consider a staging deploy on every merge to main, prod deploy gated on a manual approval step

---

### 6. Branch protection rules

**Status:** Not configured — must be set in GitHub repo settings, not via files.

**Why deferred:** Cannot be automated via committed files.

**What completing it requires:**
Enforce in GitHub → Settings → Branches → `main`:
- Require status checks: `lint`, `test` (from `ci.yml`) must pass before merge
- Require branches to be up to date before merging
- Require at least 1 PR review approval
- Dismiss stale reviews on new commits
- Do not allow bypassing the above checks (disable admin override)

---

## Code Quality

### 7. Tests for `core/` and `api/`

**Status:** Only `worker/` has a test suite. `core/` and `api/` have no tests at all.

**Why deferred:** Test coverage was not the focus of the hardening sessions.

**What completing it requires:**
- `core/` pure functions are the easiest wins: `compute_bid_score`, `apply_skill_delta`, `compute_influence_ema`, `TaskStateMachine.transition` are all pure and testable with zero mocking
- `api/` routers need a FastAPI `TestClient` fixture and a mock or test database session
- Add `pytest.ini_options` and test dependencies to `core/pyproject.toml` and `api/pyproject.toml`
- CI `test` job already runs `worker/tests/` — extend `testpaths` or add parallel jobs for the other packages

---

### 8. CFP stream has no subscriber

**Status:** `CfpIssuedStreamEvent` is published to `stream:cfp` but no handler consumes it.

**Why deferred:** The WARNING comment referencing this was removed during core hardening (it was a task note that violated the no-TODO-comments rule) but the underlying gap remains.

**What completing it requires:**
- Implement `CfpHandler` in `worker/handlers/cfp.py` (or confirm the existing stub is wired up)
- Register it as a subscriber in `worker/subscriber.py` against `stream:cfp`
- The handler should run targeted bidding among agents other than the `initiating_agent_id` from the `CfpIssuedStreamEvent` payload
- Until this exists, the CFP path in `execute_task` calls `stream_logger.cfp_issued()` and immediately releases the task back to open bidding via `_release_to_pool()` — bidding happens via `stream:task`, not `stream:cfp`

---

### 9. RedisBus not wired in production paths

**Status:** The codebase has `RedisBus` implemented but a TODO (now removed) noted it was not yet wired. Confirm the worker startup hook connects the real `RedisBus` rather than `InMemoryBus`.

**What completing it requires:**
- Verify `worker/settings.py` or `worker/context.py` instantiates `RedisBus` (not `InMemoryBus`) for the cross-process stream bus
- `InMemoryBus` is correct for the in-process `EventBus` — only the stream bus (`wctx.bus`) needs to be `RedisBus`
- Add an integration test that publishes a `TaskCreatedStreamEvent` via `RedisBus` and asserts a consumer group receives it

---

## Tracking

Open a GitHub issue for each item above when it becomes the next priority. Do not add TODOs referencing these gaps back into source code — this document is the single tracking location.
