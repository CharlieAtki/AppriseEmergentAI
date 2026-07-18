.PHONY: help setup lint lint-fix format format-check typecheck arch test test-api test-core test-worker check fix

help:
	@echo "make setup         - uv sync with dev+test extras for all workspace packages"
	@echo "make lint          - ruff check (backend/)"
	@echo "make format-check  - ruff format --check (backend/)"
	@echo "make fix           - ruff --fix + ruff format (backend/)"
	@echo "make typecheck     - mypy per package (api, core, worker)"
	@echo "make arch          - import-linter: enforce CLAUDE.md's process/layer boundaries"
	@echo "make test          - pytest across api, core, worker"
	@echo "make test-api      - pytest for backend/api only"
	@echo "make test-core     - pytest for backend/core only"
	@echo "make test-worker   - pytest for backend/worker only"
	@echo "make check         - lint + format-check + typecheck + arch + test (what CI/pre-push runs)"

# `uv sync --all-packages` alone drops the dev/test extras from the shared
# workspace venv (backend/.venv) — every target below needs this to have run
# at least once, or after new dev/test dependencies are added.
setup:
	uv sync --all-packages --extra dev --extra test

lint:
	uv run ruff check backend/

format-check:
	uv run ruff format --check backend/

fix:
	uv run ruff check --fix backend/
	uv run ruff format backend/

typecheck:
	uv run mypy backend/api/api --config-file backend/api/pyproject.toml
	uv run mypy backend/core/core --config-file backend/core/pyproject.toml
	uv run mypy backend/worker/worker --config-file backend/worker/pyproject.toml

arch:
	uv run lint-imports

test-api:
	uv run pytest backend/api/tests

test-core:
	uv run pytest backend/core/tests

test-worker:
	uv run pytest backend/worker/tests

test: test-api test-core test-worker

check: lint format-check typecheck arch test
