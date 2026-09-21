# Every target is a line from CONTRIBUTING.md. `make check` is what CI runs, in CI's order.
.PHONY: help sync fix lint types test test-docker test-e2b docs actions check

help:  ## list the targets
	@grep -hE '^[a-z0-9-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | expand -t 16

sync:  ## dev environment: core + every adapter + dev tools
	uv sync --all-extras

fix:  ## apply what ruff can fix
	uv run ruff check --fix .
	uv run ruff format .

lint:  ## ruff, and the lockfile against pyproject
	uv run ruff check .
	uv run ruff format --check .
	uv lock --check

types:  ## mypy and pyright, both strict
	uv run mypy
	uv run pyright

test:  ## unit and gates; no Docker, no network
	uv run pytest

test-docker:  ## the Docker contract suite, against a real daemon
	uv run pytest -m docker -p no:cacheprovider

test-e2b:  ## the E2B contract suite; needs E2B_API_KEY in a git-ignored .env
	uv run --env-file .env pytest -m e2b -p no:cacheprovider

docs:  ## regenerate the error catalogue and llms-full.txt, then check every link
	uv run python scripts/gen_error_catalog.py
	uv run python scripts/gen_llms_full.py
	uv run python scripts/check_doc_links.py

actions:  ## the Actions security lint
	uvx zizmor@1.30.1 --offline .github/workflows/

check: lint types test test-docker actions  ## everything CI runs except the nightly E2B suite
	uv run python scripts/check_doc_links.py
