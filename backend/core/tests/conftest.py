from __future__ import annotations

# Set required env vars before any core.config import resolves Settings().
# Must be module-level (not inside a fixture) — core.database builds its
# engine eagerly at import time, so this has to run before pytest collects
# any test file that imports core.database (directly or transitively).
import os

os.environ.setdefault("DATABASE__URL", "postgresql+asyncpg://test:test@localhost/test")
