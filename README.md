# Legacy Records Viewer

Read-only web viewer for the retired Allscripts EHR (EMR, practice management and pre-2010 records).
See `CLAUDE.md` for the full specification and `BUILD_PROMPTS.md` for the build phases.

## Local development (Phase 0: fake data)

Requires [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 for you).

```sh
uv sync                                   # create .venv and install dependencies
cp .env.example .env                      # optional in Phase 0; USE_FAKE_DATA=true is the default
uv run uvicorn app.main:app --reload      # http://127.0.0.1:8000  (or: make dev)
```

In Phase 0 any email/password signs in (fake mode). All patients are obviously fake ("Sample, Patient A").

## Checks

```sh
uv run ruff check . && uv run ruff format --check . && uv run pytest -m "not integration"
```
