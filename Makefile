.PHONY: up down logs install test fmt lint typecheck ingest chat-test

install:
	uv sync

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

test:
	uv run pytest -v

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .

typecheck:
	uv run mypy app

ingest:
	uv run python scripts/ingest_cli.py

chat-test:
	curl -s -X POST http://localhost:8000/chat \
		-H 'Content-Type: application/json' \
		-d '{"question":"Quelles tendances reviennent cette semaine ?","topics":["Python","AI/ML"]}' \
		| python -m json.tool
