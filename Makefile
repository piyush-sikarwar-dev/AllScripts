.PHONY: dev test lint format

dev:
	uv run uvicorn app.main:app --reload

test:
	uv run pytest -m "not integration"

lint:
	uv run ruff check . && uv run ruff format --check .

format:
	uv run ruff format . && uv run ruff check --fix .
