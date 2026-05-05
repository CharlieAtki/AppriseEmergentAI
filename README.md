# Apprise

## Project Structure

```
Apprise/
  pyproject.toml            ← uv workspace root (PyCharm uses this)
  uv.lock                   ← committed — pins exact dependency versions
  backend/
    core/
      alembic.ini           ← alembic config
      pyproject.toml        ← package: apprise-core (shared library)
      core/
        __init__.py
        migrations/         ← alembic migration scripts
          env.py
          versions/
    api/
      pyproject.toml        ← package: apprise-api (depends on apprise-core)
      api/
        __init__.py
      Dockerfile
    worker/
      pyproject.toml        ← package: apprise-worker (depends on apprise-core)
      worker/
        __init__.py
      Dockerfile
  frontend/
    Dockerfile
```

---

## Prerequisites

| Tool | Purpose | Install |
|---|---|---|
| Python 3.14+ | Runtime | https://www.python.org/downloads/ |
| uv | Package manager & virtual environments | https://docs.astral.sh/uv/getting-started/installation/ |
| Docker | Running services in containers | https://docs.docker.com/get-docker/ |

---

## Getting Started (First-Time Setup)

### 1. Clone the repo

```bash
git clone <repo-url>
cd Apprise
```

### 2. Install all Python packages

```bash
uv sync --all-packages
```

This creates a `.venv` at the project root and installs `apprise-core`, `apprise-api`, and `apprise-worker` into it.

### 3. Activate the virtual environment

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Your prompt will show `(apprise)` when the venv is active. Alternatively, skip activation entirely and prefix all commands with `uv run`.

### 4. PyCharm / IDE setup

PyCharm detects the root `pyproject.toml` automatically and prompts to configure the uv interpreter. Accept it — no manual setup needed.

---

## Backend — Python Packages

The backend is split into three Python packages:

| Package | Description |
|---|---|
| `apprise-core` | Shared library — models, database, migrations. Not a runnable service. |
| `apprise-api` | FastAPI HTTP service. Depends on `apprise-core`. |
| `apprise-worker` | Background worker. Depends on `apprise-core`. |

### Why this structure?

`core` is an **installable Python package**, not just a folder. `api` and `worker` import from it cleanly (`from core import ...`) with no `sys.path` hacks. Any shared code — database models, schemas, config — lives in `core`.

### Adding dependencies

```bash
# Shared (available to api and worker)
uv add sqlalchemy --package apprise-core

# API only
uv add fastapi --package apprise-api

# Worker only
uv add celery --package apprise-worker
```

---

## Database Migrations (Alembic)

Migrations live in `backend/core/core/migrations/` and are managed from `backend/core/`.

### Run migrations

```bash
cd backend/core

# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1
```

### Create a new migration

```bash
cd backend/core

# Auto-generate from model changes
alembic revision --autogenerate -m "description of change"

# Or create a blank migration
alembic revision -m "description of change"
```

### Check current state

```bash
cd backend/core
alembic current    # show applied revision
alembic history    # show all revisions
```

> **Note:** Always review auto-generated migrations before applying. Alembic can miss some changes (e.g. check constraints, custom types).

---

## uv Workspace

The project uses a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) so all packages share one virtual environment. The root `pyproject.toml` declares:

```toml
[tool.uv.workspace]
members = ["backend/core", "backend/api", "backend/worker"]

[tool.uv.sources]
apprise-core = { workspace = true }
```

`workspace = true` tells uv to resolve `apprise-core` from the local `backend/core/` directory rather than PyPI — no path hacks needed.

The `uv.lock` file is **committed to git** to ensure every developer and CI environment installs identical dependency versions.

---

## Docker — Building Services

`core` is a library, not a service — only `api` and `worker` have Dockerfiles.

Both Dockerfiles need access to `core/` at build time, so the build context must be the `backend/` directory:

```bash
# From the backend/ directory:
cd backend
docker build -f api/Dockerfile .
docker build -f worker/Dockerfile .
```

Each Dockerfile installs `core` first, then the service:

```dockerfile
COPY core/ ./core/
RUN pip install --no-cache-dir ./core

COPY api/ ./api/
RUN pip install --no-cache-dir ./api
```

---

## Quick Reference

| Task | Command |
|---|---|
| Install all packages | `uv sync --all-packages` (project root) |
| Activate venv (PowerShell) | `.venv\Scripts\Activate.ps1` |
| Run a command without activating | `uv run <command>` |
| Add a shared dependency | `uv add <pkg> --package apprise-core` |
| Add an api-only dependency | `uv add <pkg> --package apprise-api` |
| Add a worker-only dependency | `uv add <pkg> --package apprise-worker` |
| Apply migrations | `cd backend/core && alembic upgrade head` |
| Create a migration | `cd backend/core && alembic revision --autogenerate -m "msg"` |
| Build api Docker image | `cd backend && docker build -f api/Dockerfile .` |
| Build worker Docker image | `cd backend && docker build -f worker/Dockerfile .` |
