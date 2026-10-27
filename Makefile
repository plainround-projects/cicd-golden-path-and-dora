# make up | run | test | lint | down      (make help lists everything)
PYTHON ?= $(shell command -v python3.13 || command -v python3.12 || command -v python3)
VENV := .venv
PY := $(VENV)/bin/python
STAMP := $(VENV)/.installed
COMPOSE := docker compose
KEYS := .local/keys

-include .env
export POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD LOG_LEVEL COLLECTOR_PORT COLLECTOR_URL COLLECTOR_TOKEN \
       REGISTRY RUNBOOK_BASE COSIGN_PASSWORD

.PHONY: help install up db down run demo-services demo-unsigned simulate dora dora-sample trace deployments catalog audit \
        lint format test test-integration test-e2e check audit-deps workflows collector stop-collector clean

help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | sort

$(STAMP): requirements-dev.lock pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --require-hashes -r requirements-dev.lock
	$(VENV)/bin/pip install -q --no-deps -e .
	touch $@

install: $(STAMP) ## create .venv from the lock file

.env:
	cp .env.example .env

# The platform's local infrastructure: PostgreSQL (the event store), a registry for images, a signing key pair,
# and the collector (a background process, stopped by `make down`).
up: $(STAMP) .env ## start PostgreSQL and the registry, create a signing key, apply sql/, start the collector
	$(COMPOSE) up -d --wait
	$(MAKE) --no-print-directory db
	@mkdir -p $(KEYS) .local/logs
	@test -f $(KEYS)/cosign.key || (cd $(KEYS) && COSIGN_PASSWORD="$(COSIGN_PASSWORD)" cosign generate-key-pair >/dev/null && echo "created a local signing key pair in $(KEYS)")
	@$(MAKE) --no-print-directory collector

PSQL ?= $(COMPOSE) exec -T -e PGOPTIONS=--client-min-messages=warning db psql -v ON_ERROR_STOP=1 -q -U $(POSTGRES_USER) -d $(POSTGRES_DB)

db: ## apply sql/001_schema.sql and 002_seed.sql (safe to repeat)
	@for script in sql/00[12]_*.sql; do echo "applying $$script"; $(PSQL) < $$script || exit 1; done

collector: ## start the event collector in the background (logs in .local/logs)
	@if [ -f .local/collector.pid ] && kill -0 $$(cat .local/collector.pid) 2>/dev/null; then echo "collector already running"; else \
	  nohup $(VENV)/bin/goldenpath collector > .local/logs/collector.log 2>&1 & echo $$! > .local/collector.pid; \
	  for i in $$(seq 1 40); do curl -fsS http://127.0.0.1:$(COLLECTOR_PORT)/healthz >/dev/null 2>&1 && break; sleep 0.5; done; \
	  curl -fsS http://127.0.0.1:$(COLLECTOR_PORT)/healthz && echo " collector up on port $(COLLECTOR_PORT)"; fi

stop-collector:
	@if [ -f .local/collector.pid ]; then kill $$(cat .local/collector.pid) 2>/dev/null || true; rm -f .local/collector.pid; fi

# The whole lesson: three services for three teams, each to production through its own pipeline (signed, verified);
# an unsigned image refused; a simulated month; the four metrics per service and per week; one lead time traced.
run: up demo-services demo-unsigned simulate dora ## the whole golden path, then a simulated month and the DORA tables
	$(VENV)/bin/goldenpath trace orders orders-c1

demo-services: $(STAMP) ## generate orders, billing and search and take each to production (about 3 minutes each)
	@for pair in orders:team-orders billing:team-billing search:team-search; do \
	  rm -rf .local/services/$${pair%%:*} .local/remotes/$${pair%%:*}.git; \
	  $(VENV)/bin/goldenpath new-service $${pair%%:*} $${pair##*:} --release || exit 1; \
	done
	$(VENV)/bin/goldenpath catalog

demo-unsigned: $(STAMP) ## push an image nobody signed and try to deploy it: refused, and a failed event recorded
	$(VENV)/bin/goldenpath demo-unsigned orders

simulate: $(STAMP) ## replace the stored events with a simulated month for three teams
	$(VENV)/bin/goldenpath simulate

dora: $(STAMP) ## the four metrics per service, per week and overall, from the stored events
	$(VENV)/bin/goldenpath metrics
	$(VENV)/bin/goldenpath metrics --weekly

dora-sample: $(STAMP) ## the lesson's sample events.csv: the numbers the lesson expects
	$(VENV)/bin/goldenpath metrics --csv data/events-sample.csv

trace: $(STAMP) ## trace one lead time to its two events (make trace SERVICE=orders COMMIT=orders-c1)
	$(VENV)/bin/goldenpath trace $(or $(SERVICE),orders) $(or $(COMMIT),orders-c1)

deployments: $(STAMP) ## every production deployment of a service with its commits (SERVICE=orders)
	$(VENV)/bin/goldenpath deployments $(or $(SERVICE),orders)

catalog: $(STAMP) ## list the registered services
	$(VENV)/bin/goldenpath catalog

audit: $(STAMP) ## audit every generated repository against the contract (make audit PATH_TO=.local/services/orders for one)
	@for dir in $(or $(PATH_TO),$$(ls -d .local/services/* 2>/dev/null)); do echo "$$dir"; $(VENV)/bin/goldenpath audit $$dir || exit 1; done

lint: $(STAMP) ## ruff check, ruff format check, mypy, import-linter, workflow lint, template audit
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .
	$(VENV)/bin/mypy
	$(VENV)/bin/lint-imports
	$(PY) scripts/lint_workflows.py

format: $(STAMP) ## apply ruff's formatting and safe fixes
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/ruff format .

test: $(STAMP) ## unit tests with coverage (no database needed)
	@mkdir -p reports
	$(PY) -m pytest tests/unit tests/template -p no:cacheprovider --junitxml=reports/unit.xml --cov --cov-report=term
	$(PY) -m coverage report --include='src/goldenpath/domain/*,src/goldenpath/application/*' --fail-under=95

test-integration: $(STAMP) ## the store, the collector and the SQL against PostgreSQL (make up first)
	$(PY) -m pytest tests/integration -m integration -p no:cacheprovider

test-e2e: $(STAMP) ## generate a service and take it to production with a real registry, key and compose (make up first)
	$(PY) -m pytest tests/e2e -m e2e -p no:cacheprovider

check: lint test ## everything that needs no database or Docker

audit-deps: $(STAMP) ## check the locked dependencies for known vulnerabilities
	$(VENV)/bin/pip-audit --no-deps --disable-pip -r requirements-dev.lock

workflows: $(STAMP) ## lint the platform's own workflow and the template's
	$(PY) scripts/lint_workflows.py

down: stop-collector ## stop PostgreSQL and the registry, remove the generated services' containers and delete local state
	-@for dir in .local/services/*; do [ -d "$$dir" ] && IMAGE_REF=unused $(COMPOSE) -p $$(basename $$dir)-production -f $$dir/deploy/compose.yaml down -v 2>/dev/null; done; true
	$(COMPOSE) down -v
	rm -rf .local

clean: down
	rm -rf $(VENV) dist build reports logs .pytest_cache .mypy_cache .ruff_cache .import_linter_cache .coverage coverage.xml
