COMPOSE := docker compose -f infra/compose/docker-compose.yml
SERVICES := business ai_runtime integration_runtime
BUSINESS_MIGRATIONS_DATABASE_URL ?= postgresql+asyncpg://business_owner:business_owner_dev@localhost:55432/business
export BUSINESS_MIGRATIONS_DATABASE_URL

.PHONY: up down reset sync migrate dev check test test-unit test-integration test-repo lint

up:            ## Platformani ko‘tarish (Postgres, RabbitMQ, Redis, MinIO)
	$(COMPOSE) up -d --wait postgres rabbitmq redis minio

down:
	$(COMPOSE) down

reset:         ## Ma’lumotlar bilan birga o‘chirish
	$(COMPOSE) down -v

sync:
	@for s in $(SERVICES); do (cd services/$$s && uv sync -q) || exit 1; done

migrate:
	cd services/business && uv run alembic upgrade head

dev:           ## Business API’ni lokal ishga tushirish (.env kerak)
	cd services/business && uv run --env-file ../../.env uvicorn business.bootstrap.app:create_app --factory --reload --port 8000

lint:          ## ruff + mypy + import-linter har servisda
	@for s in $(SERVICES); do \
		echo "== $$s"; \
		(cd services/$$s && uv run ruff check . && uv run mypy && uv run lint-imports --no-cache) || exit 1; \
	done

test-unit:
	@for s in $(SERVICES); do (cd services/$$s && uv run pytest -q -m "not integration") || exit 1; done

test-integration: ## make up && make migrate kerak
	cd services/business && uv run pytest -q -m integration

test-repo:     ## Servislararo chegaralar va kontrakt schema’lari
	uv run --no-project --with pytest --with jsonschema pytest -q tests/architecture tests/contracts

test: test-unit test-repo test-integration

check: lint test
