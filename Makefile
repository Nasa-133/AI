COMPOSE := docker compose -f infra/compose/docker-compose.yml
SERVICES := business ai_runtime integration_runtime
PACKAGES := abo_messaging
BUSINESS_MIGRATIONS_DATABASE_URL ?= postgresql+asyncpg://business_owner:business_owner_dev@localhost:55432/business
export BUSINESS_MIGRATIONS_DATABASE_URL

.PHONY: load eval eval-openai degradation migration-check test-db up down reset sync migrate dev worker ai-worker integration-worker check e2e e2e-ui stack web-lint web-test test test-unit test-integration test-repo lint openapi synthetic

up:            ## Platformani ko‘tarish (Postgres, RabbitMQ, Redis, S3 ombori)
	$(COMPOSE) up -d --wait postgres rabbitmq redis objectstore

down:
	$(COMPOSE) down

reset:         ## Ma’lumotlar bilan birga o‘chirish
	$(COMPOSE) down -v

sync:
	@for s in $(SERVICES); do (cd services/$$s && uv sync -q) || exit 1; done
	@for p in $(PACKAGES); do (cd packages/$$p && uv sync -q) || exit 1; done

migrate:       ## Uchala runtime bazasiga migratsiya
	cd services/business && uv run alembic upgrade head
	cd services/ai_runtime && uv run alembic upgrade head
	cd services/integration_runtime && uv run alembic upgrade head

dev:           ## Business API’ni lokal ishga tushirish (.env kerak)
	cd services/business && uv run --env-file ../../.env uvicorn business.bootstrap.app:create_app --factory --reload --port 8000

worker:        ## Business worker (outbox relay, consumer’lar)
	cd services/business && uv run --env-file ../../.env python -m business.entrypoints.worker

ai-worker:     ## AI Runtime worker (RunAgent consumer, runner, relay)
	cd services/ai_runtime && uv run --env-file ../../.env python -m ai_runtime.bootstrap.worker

integration-worker: ## Integration Runtime worker (sync consumer, runner, relay)
	cd services/integration_runtime && uv run --env-file ../../.env python -m integration_runtime.bootstrap.worker

lint:          ## ruff + mypy + import-linter har servisda
	@for s in $(SERVICES); do \
		echo "== $$s"; \
		(cd services/$$s && uv run ruff check . && uv run mypy && uv run lint-imports --no-cache) || exit 1; \
	done
	@for p in $(PACKAGES); do echo "== $$p"; (cd packages/$$p && uv run ruff check . && uv run mypy) || exit 1; done

web-lint:      ## Web: eslint + TypeScript
	cd apps/web && npx eslint src e2e && npx tsc --noEmit

web-test:      ## Web: unit testlar (vitest)
	cd apps/web && npx vitest run

e2e-ui:        ## Brauzer testlari (Playwright). Oldin: make stack
	cd apps/web && npx playwright test

test-unit:
	@for s in $(SERVICES); do (cd services/$$s && uv run pytest -q -m "not integration") || exit 1; done
	@for p in $(PACKAGES); do (cd packages/$$p && uv run pytest -q -m "not integration") || exit 1; done

eval:          ## Release eval (TZ 20) fake provayder bilan; hisobot docs/reports/ (make stack to‘xtatilgan bo‘lsin)
	./scripts/eval.sh

eval-openai:   ## Real OpenAI eval (OPENAI_API_KEY, OPENAI_MODEL_MAIN, OPENAI_EMBEDDING_MODEL kerak)
	EVAL_MODE=openai ./scripts/eval.sh

load:          ## Pilot yuklama (TZ 19): 1 mln satr, 20 foydalanuvchi, 5 parallel vazifa; hisobot docs/reports/
	./scripts/load.sh

degradation:   ## I03/I05/gate 5,7: AI, Integration, broker o‘chirilgandagi xatti-harakat (make stack to‘xtatilgan bo‘lsin)
	./scripts/degradation.sh

migration-check: ## Gate 8: toza bazada upgrade → downgrade base → upgrade (uch runtime)
	./scripts/migration-check.sh

test-db:       ## Integratsiya testlari uchun alohida *_test bazalari (idempotent)
	./scripts/test-dbs.sh

test-integration: test-db ## make up kerak; stek ishlab tursa ham xavfsiz (alohida test bazalari)
	cd services/business && uv run pytest -q -m integration
	cd services/ai_runtime && uv run pytest -q -m integration
	cd services/integration_runtime && uv run pytest -q -m integration
	cd packages/abo_messaging && uv run pytest -q -m integration

test-repo:     ## Servislararo chegaralar va kontrakt schema’lari
	uv run --no-project --with pytest --with jsonschema pytest -q tests/architecture tests/contracts tools/synthetic_data/tests

openapi:       ## Review’dan keyin OpenAPI baseline’ni yangilash
	cd services/business && uv run python ../../tools/contracts/export_openapi.py business > ../../contracts/http/business.openapi.json

synthetic:     ## Demo va golden sintetik ma’lumotlarni qayta yaratish
	python3 tools/synthetic_data/generate.py --seed 42 --rows 19000 --out fixtures/synthetic/demo
	python3 tools/synthetic_data/generate.py --golden --out fixtures/synthetic/golden

test: test-unit test-repo test-integration

check: lint web-lint test web-test

stack:         ## Butun stek lokal: API + 3 worker + web (http://localhost:3010)
	./scripts/dev.sh

e2e:           ## Vertikal kesim: API + 3 worker haqiqiy jarayon sifatida (make up kerak)
	./scripts/e2e.sh
