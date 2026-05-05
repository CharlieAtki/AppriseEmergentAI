# Apprise

## Project Structure

```
Apprise/
  pyproject.toml          ← uv workspace root (PyCharm uses this)
  backend/
    core/
      pyproject.toml      ← package: apprise-core (shared library)
      core/
        __init__.py
    api/
      pyproject.toml      ← package: apprise-api (depends on apprise-core)
      Dockerfile
    worker/
      pyproject.toml      ← package: apprise-worker (depends on apprise-core)
      Dockerfile
  frontend/
    Dockerfile
```

---

## Backend — Python Packages

The backend is split into three Python packages:

| Package | Description |
|---|---|
| `apprise-core` | Shared library — models, database, utilities. Not a runnable service. |
| `apprise-api` | FastAPI HTTP service. Depends on `apprise-core`. |
| `apprise-worker` | Background worker/task runner. Depends on `apprise-core`. |

### Why this structure?

`core` is an **installable Python package**, not just a folder. This means `api` and `worker` can import from it cleanly (`from core import ...`) without any `sys.path` hacks. Any shared code (database models, schemas, config) lives in `core` and is available to both services.

---

## Local Development — uv Workspace

The backend uses a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) so all three packages share a single virtual environment and uv resolves them together.

### First-time setup

1. Install uv: https://docs.astral.sh/uv/getting-started/installation/
2. From the **project root**, install all packages:

```bash
uv sync --all-packages
```

This creates a `.venv` at the project root and installs `apprise-core`, `apprise-api`, and `apprise-worker` (plus all their dependencies) into it.

### How the workspace resolves `apprise-core`

The root `pyproject.toml` declares:

```toml
[tool.uv.sources]
apprise-core = { workspace = true }
```

This tells uv that when `api` or `worker` list `apprise-core` as a dependency, use the **local `backend/core/` directory** instead of looking on PyPI. No path manipulation needed.

### PyCharm / IDE setup

PyCharm detects the root `pyproject.toml` automatically and configures the uv interpreter from there. No extra setup needed.

### Adding dependencies

To add a dependency to a specific package:

```bash
# Add to api
uv add fastapi --package apprise-api

# Add to worker
uv add celery --package apprise-worker

# Add to core (shared — available to all)
uv add sqlalchemy --package apprise-core
```

---

## Docker — Building Services

`core` is a **library, not a service** — it has no Dockerfile and is never run directly. Only `api` and `worker` have Dockerfiles.

### Build context

Both Dockerfiles live inside `backend/api/` and `backend/worker/`, but they need access to `core/` at build time. The build context must therefore be set to the `backend/` directory:

```bash
# From the backend/ directory:
docker build -f api/Dockerfile .
docker build -f worker/Dockerfile .
```

### How the Dockerfiles install core

Each Dockerfile copies and installs `core` first, then the service:

```dockerfile
COPY core/ ./core/
RUN pip install --no-cache-dir ./core

COPY api/ ./api/
RUN pip install --no-cache-dir ./api
```

This mirrors the local uv workspace setup — `core` is installed as a real package, so imports work identically in Docker and locally.

---

## Quick Reference

| Task | Command |
|---|---|
| Install all packages locally | `uv sync --all-packages` (from project root) |
| Build api image | `cd backend && docker build -f api/Dockerfile .` |
| Build worker image | `cd backend && docker build -f worker/Dockerfile .` |
| Add a shared dependency | `uv add <pkg> --package apprise-core` |
| Add an api-only dependency | `uv add <pkg> --package apprise-api` |
