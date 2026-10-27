# Make and the Makefiles

## What it is

A **terminal** is a window where you type commands. A **command** is the name of a program followed by some words (its **arguments**). A **shell** is the program that reads what you type and starts the program you named. Typing `ls` in a shell starts a small program that lists the files in the current folder.

`make` is one such program. It is a tool for **running recipes in the right order**. You describe your recipes in a text file named `Makefile`. When you type `make lint`, `make` reads the file, finds the recipe named `lint`, and runs the commands written under it.

A Makefile is a list of **rules**. Each rule has three parts:

```make
target: prerequisite another-prerequisite
	command that makes the target
```

- The **target** is the name of the thing the rule makes. It can be a file (such as `.venv/.installed`) or just a name for an action (such as `lint`).
- The **prerequisites** are other targets that must be ready first. `make` builds them before it runs this rule's commands.
- The **recipe** is the indented lines. Each line is a shell command. The indent **must be a tab character**, not spaces. (If you use spaces, `make` stops with `*** missing separator`.)

One more idea: `make` compares file **modification times**. If the target is a file and it is newer than all its prerequisites, there is nothing to do and the rule is skipped. This makes `make` good at "do the slow step only when its inputs changed".

macOS ships GNU Make **3.81**, which is very old; Linux machines and GitHub's runners have 4.x. The Makefiles here use only features that both versions have.

## Why this repository uses it

There are **two** Makefiles, and both follow one rule: *every job of a workflow is one `make` target, so a laptop runs the same steps as CI.*

- The root `Makefile` belongs to the **platform**: `make up`, `make run`, `make test`, `make lint`, `make down`.
- `template/Makefile` is **copied into every generated service**. It has the steps of the golden-path pipeline: `ci` (lint and test) and `release` (image, sign, attest, verify, deploy). The service's workflow calls these targets, and the platform runs the same ones locally when it generates a service.

## Where it appears

| Path | Role |
|---|---|
| `Makefile` | The platform's targets; `make help` lists them. |
| `template/Makefile` | The generated service's pipeline steps. |
| `.github/workflows/ci.yml` | Calls `make check`, `make install`, `make db`, `make test-integration`, `make audit-deps`. |
| `template/.github/workflows/ci.yml` | Calls `make lint`, `make test`, `make image`, `make sign`, `make attest`, `make verify`, `make deploy`. |
| `src/goldenpath/infrastructure/local_pipeline.py` | Starts `make --no-print-directory STEP` for each step of a generated service. |

## How it works underneath

- `make test` finds the rule whose target is `test`, makes each prerequisite first (following their own prerequisites, recursively), and then runs the recipe.
- Each recipe line is run by **its own new shell**. So a `cd` on one line does not carry over to the next line. To make several commands share a shell, the line is continued with a backslash `\` at the end.
- A line starting with `@` is run but not printed first. A line starting with `-` is run and its failure is ignored.
- A **variable** is a named piece of text. `NAME := value` sets it. `$(NAME)` uses it. `$$` is how you write a single dollar sign that the shell (not `make`) should see, so `$$script` is the shell variable `script`.
- `NAME ?= value` sets the variable only if nobody has set it already. That lets a caller override it: `make test PYTHON=python3.12`.
- A **phony** target is a name for an action, not a file. It is listed after `.PHONY:` so that `make` does not get confused when a file with the same name exists.
- `make` passes its variables to commands it starts only if they are **exported**.

## Walkthrough of this repository's use

### The platform `Makefile`, top to bottom

```make
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

.PHONY: help install up db down run evidence demo-services demo-unsigned simulate dora dora-sample trace deployments catalog audit \
        lint format test test-integration test-e2e check audit-deps workflows collector stop-collector clean
```

- **Line 1** is a comment listing the commands a newcomer uses. **Line 2**: `PYTHON ?= $(shell command -v python3.13 || command -v python3.12 || command -v python3)`: `$(shell ...)` runs a command and uses its output; `command -v NAME` prints a program's path if it exists; `||` means "if the left side failed, try the right"; `?=` sets the variable only if nobody has. So `PYTHON` is the first of Python 3.13, 3.12 or plain `python3` that exists.
- **Lines 3 to 5**: `VENV := .venv` (the virtual environment folder, [pip-and-hash-locking.md](pip-and-hash-locking.md)); `PY := $(VENV)/bin/python` (the Python inside it); `STAMP := $(VENV)/.installed` (a stamp file, explained below). **Line 6**: `COMPOSE := docker compose`. **Line 7**: `KEYS := .local/keys`, where the demo signing key pair is kept.
- **Line 9**: `-include .env` reads `.env` as `make` assignments (the `-` means "no error if missing"). **Lines 10 and 11**: `export POSTGRES_HOST ... COSIGN_PASSWORD` marks eleven variables for passing to every command `make` starts ([dotenv.md](dotenv.md)); the trailing backslash continues the line.
- **Lines 13 and 14**: `.PHONY:` lists the targets that are actions, not files.

```make
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
```

- **Lines 16 and 17**, `help`: `grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | sort`. `$(MAKEFILE_LIST)` is the list of files `make` read; `grep` finds target lines that have a `## description`; `sed` replaces the part between the colon and `##` with a tab; `sort` orders them; the leading `@` hides the command itself.
- **Lines 19 to 23**, the **stamp file**: the target is the file `.venv/.installed` with prerequisites `requirements-dev.lock` and `pyproject.toml`. If either is newer than the stamp, the recipe runs: create the environment (`$(PYTHON) -m venv $(VENV)`), `pip install -q --require-hashes -r requirements-dev.lock` (install the exact locked tools; `-q` is quiet; `--require-hashes` refuses any file whose fingerprint is not in the lock), `pip install -q --no-deps -e .` (install this project in editable form, without touching the locked packages), then `touch $@` (`$@` is "this rule's target"; `touch` creates the file or updates its time). Nearly every target lists `$(STAMP)`, so whatever you run first creates the environment.
- **Line 25**: `install: $(STAMP)`. **Lines 27 and 28**: `.env:` is a file target: if `.env` does not exist, `cp .env.example .env`.

```make
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
```

- **Lines 30 and 31** (comments): the platform's local infrastructure is PostgreSQL (the event store), a registry for images, a signing key pair, and the collector (a background process stopped by `make down`).
- **Lines 32 to 37**, `up`: `$(COMPOSE) up -d --wait` starts the two services and waits for their health checks ([docker-compose.md](docker-compose.md)); `$(MAKE) --no-print-directory db` calls `make` again for the `db` target; `@mkdir -p $(KEYS) .local/logs` creates folders; `@test -f $(KEYS)/cosign.key || (cd $(KEYS) && COSIGN_PASSWORD="$(COSIGN_PASSWORD)" cosign generate-key-pair >/dev/null && echo "created ...")` means "if the key file is missing, then (in a sub-shell, so the `cd` does not leak) generate the key pair with the password from `.env`"; `@$(MAKE) --no-print-directory collector` starts the collector.
- **Line 39**: `PSQL ?= $(COMPOSE) exec -T -e PGOPTIONS=--client-min-messages=warning db psql -v ON_ERROR_STOP=1 -q -U $(POSTGRES_USER) -d $(POSTGRES_DB)`: run `psql` (PostgreSQL's command-line client) inside the running `db` container; `-T` no terminal (so input can be piped), `-v ON_ERROR_STOP=1` stop at the first error, `-q` quiet, `-U`/`-d` the user and database. CI overrides `PSQL` to talk to its service container.
- **Lines 41 to 42**, `db`: `for script in sql/00[12]_*.sql; do echo "applying $$script"; $(PSQL) < $$script || exit 1; done` applies the schema and the seed ([sql.md](sql.md)). `00[12]` matches `001` or `002`, so `003_queries.sql` is not applied; `$$script` is a shell variable (`$$` makes `make` pass one `$` through); `< file` feeds the file to psql.
- **Lines 44 to 48**, `collector`: if `.local/collector.pid` exists **and** `kill -0 $$(cat .local/collector.pid)` succeeds (signal 0 sends nothing; it only tests that the process exists), print "collector already running". Otherwise `nohup $(VENV)/bin/goldenpath collector > .local/logs/collector.log 2>&1 &` starts it in the background (`nohup` keeps it alive when the terminal closes; `> file 2>&1` sends its output and errors to a log file; `&` returns at once), and `echo $$! > .local/collector.pid` saves the new process's id (`$!` is the id of the last background process). Then `for i in $$(seq 1 40); do curl -fsS http://127.0.0.1:$(COLLECTOR_PORT)/healthz >/dev/null 2>&1 && break; sleep 0.5; done` asks the health address up to 40 times, half a second apart, and stops on the first success ([curl.md](curl.md)); a final `curl` prints the answer.
- **Lines 50 and 51**, `stop-collector`: if the pid file exists, `kill` that process (`2>/dev/null || true` hides a failure) and delete the file.

```make
# The whole lesson: three services for three teams, each to production through its own pipeline (signed, verified);
# an unsigned image refused; a simulated month; the four metrics per service and per week; one lead time traced.
run: up demo-services demo-unsigned evidence simulate dora ## the whole golden path, then a simulated month and the DORA tables
	$(VENV)/bin/goldenpath trace orders orders-c1

# What the pipelines recorded for the three real services, before the simulation replaces the store (step 4 and 5).
evidence: $(STAMP) ## every production deployment of each demo service with its commits, and one lead time traced
	@for service in orders billing search; do echo "$$service:"; $(VENV)/bin/goldenpath deployments $$service; done
	@first=$$(git -C .local/services/orders rev-list --max-parents=0 --abbrev-commit HEAD); \
	  $(VENV)/bin/goldenpath trace orders $$first
	$(VENV)/bin/goldenpath metrics

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
```

- **Lines 53 to 56**, `run`: prerequisites `up demo-services demo-unsigned evidence simulate dora`, run **in that order**, then `goldenpath trace orders orders-c1` prints one lead time traced to its two events. In words: infrastructure; three real services to production; an unsigned image refused; what the real pipelines recorded; a simulated month; the metrics tables; one traced value.
- **Lines 58 to 63**, `evidence`: for each service prints its deployments; `first=$$(git -C .local/services/orders rev-list --max-parents=0 --abbrev-commit HEAD)` finds the service's first commit (`-C DIR` runs Git as if in that folder; `--max-parents=0` selects commits with no parent; `--abbrev-commit` shortens the id), then traces it; then prints the metrics.
- **Lines 65 to 70**, `demo-services`: `for pair in orders:team-orders billing:team-billing search:team-search; do ...; done`. Inside, `${pair%%:*}` is `pair` with everything from the first `:` removed (the service) and `${pair##*:}` is `pair` with everything up to the last `:` removed (the team); `rm -rf` clears any earlier copy; `goldenpath new-service NAME TEAM --release || exit 1` creates the service and takes it to production, stopping on a failure. Then `goldenpath catalog` lists them.
- **Lines 72 to 73**, `demo-unsigned`: pushes an image nobody signed and tries to deploy it. **Lines 75 to 76**, `simulate`. **Lines 78 to 80**, `dora`: the metrics, overall and weekly. **Lines 82 to 83**, `dora-sample`: the same from the lesson's sample CSV. **Lines 85 to 86**, `trace`: `$(or $(SERVICE),orders)` is `SERVICE` if given, else `orders`. **Lines 88 to 89**, `deployments`. **Lines 91 to 92**, `catalog`.

```make
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
```

- **Lines 94 to 95**, `audit`: for each generated folder (`$(or $(PATH_TO),$$(ls -d .local/services/* 2>/dev/null))`: the folder you name, or all of them) run `goldenpath audit DIR`; `|| exit 1` stops on a failure. (This audits generated *repositories*; the dependency audit is `audit-deps`.)
- **Lines 97 to 102**, `lint`: `ruff check .`, `ruff format --check .`, `mypy`, `lint-imports` and `scripts/lint_workflows.py` ([ruff.md](ruff.md), [mypy.md](mypy.md), [import-linter.md](import-linter.md)). **Lines 104 to 106**, `format`: the fixing counterpart.
- **Lines 108 to 111**, `test`: `pytest tests/unit tests/template -p no:cacheprovider --junitxml=reports/unit.xml --cov --cov-report=term`, then `coverage report --include='src/goldenpath/domain/*,src/goldenpath/application/*' --fail-under=95`: the domain and application layers must be at least 95 percent covered ([pytest.md](pytest.md)).
- **Lines 113 to 117**: `test-integration` (needs the database) and `test-e2e` (needs Docker, cosign and the registry). **Line 119**: `check: lint test` runs both.
- **Lines 121 to 122**, `audit-deps`: `pip-audit --no-deps --disable-pip -r requirements-dev.lock` ([pip-audit.md](pip-audit.md)). **Lines 124 to 125**, `workflows`.
- **Lines 127 to 130**, `down`: it first stops the collector (a prerequisite), then `-@for dir in .local/services/*; do [ -d "$$dir" ] && IMAGE_REF=unused $(COMPOSE) -p $$(basename $$dir)-production -f $$dir/deploy/compose.yaml down -v 2>/dev/null; done; true` removes each generated service's "production" containers (`basename` keeps only the last part of a path; `IMAGE_REF=unused` satisfies a required variable; the leading `-` ignores errors; the trailing `true` makes the line succeed), then `$(COMPOSE) down -v` stops the platform's containers, and `rm -rf .local` deletes all local state.
- **Lines 132 to 133**, `clean`: `down`, then deletes the environment and build output.

### `template/Makefile`: the pipeline every service gets

```make
# make ci | release      Every job of .github/workflows/ci.yml is one of these targets, so a laptop runs the same steps.
NAME := __NAME__
REGISTRY ?= localhost:55061
VERSION ?= $(shell git rev-parse --short HEAD)
IMAGE := $(REGISTRY)/$(NAME)
DIGEST_FILE := .build/digest
# Signing: with COSIGN_KEY (a local key file) the key is used; with none, CI's keyless identity is.
# (cosign 3 needs --use-signing-config=false to sign with a key and without the public transparency log.)
COSIGN_KEY ?=
COSIGN_PUBLIC_KEY ?=
# cosign gives up after three minutes by default; a busy machine or a slow network can need longer.
KEY_FLAGS = --timeout=15m $(if $(COSIGN_KEY),--key $(COSIGN_KEY) --use-signing-config=false --tlog-upload=false,)
DEPLOYMENT ?= $(NAME)-d$(shell date +%s)
export EVENTS_URL SERVICE_NAME := $(NAME)
export COSIGN_PUBLIC_KEY
```

- **Line 1**: the comment says every job of the workflow is one of these targets. **Line 2**: `NAME := __NAME__` is a placeholder the platform replaces with the service's name when it generates the repository. **Line 3**: `REGISTRY ?= localhost:55061` (CI sets it to GitHub's registry). **Line 4**: `VERSION ?= $(shell git rev-parse --short HEAD)`: the short commit id names the image tag. **Lines 5 and 6**: `IMAGE := $(REGISTRY)/$(NAME)` and `DIGEST_FILE := .build/digest`.
- **Lines 7 to 12**: signing options. With `COSIGN_KEY` (a local key file) the key is used; with none, CI's keyless identity is. `KEY_FLAGS = --timeout=15m $(if $(COSIGN_KEY),--key $(COSIGN_KEY) --use-signing-config=false --tlog-upload=false,)`: `=` (not `:=`) because it must be worked out when used. `$(if CONDITION,THEN,ELSE)`: if a key is given add `--key FILE --use-signing-config=false --tlog-upload=false`; otherwise add nothing. cosign 3 needs `--use-signing-config=false` to sign with a key without public services, and `--tlog-upload=false` skips the public transparency log ([cosign.md](cosign.md)).
- **Line 13**: `DEPLOYMENT ?= $(NAME)-d$(shell date +%s)`: a deployment id from the Unix time. **Lines 14 and 15**: `export EVENTS_URL SERVICE_NAME := $(NAME)` and `export COSIGN_PUBLIC_KEY` pass values to the scripts.

```make
.PHONY: lint test ci image sign attest verify deploy release

lint:
	python3 -m compileall -q app tests

test:
	python3 -m unittest discover -s tests

ci: lint test

# Build once, push, and keep the digest: the digest, not a tag, is what is signed, verified and deployed.
image:
	@mkdir -p .build
	docker build -q --build-arg APP_VERSION=$(VERSION) -t $(IMAGE):$(VERSION) .
	docker push $(IMAGE):$(VERSION) | sed -n 's/.*digest: \(sha256:[0-9a-f]*\).*/\1/p' | tail -1 > $(DIGEST_FILE)
	@test -s $(DIGEST_FILE) || { echo "no digest in the push output"; exit 1; }
	@echo "image: $(IMAGE)@$$(cat $(DIGEST_FILE))"

sign:
	cosign sign --yes $(KEY_FLAGS) $(IMAGE)@$$(cat $(DIGEST_FILE))

# A provenance statement: which commit and which build produced the digest.
attest:
	@printf '{"builder": "%s", "repository": "%s", "commit": "%s", "built_at": "%s"}\n' \
	  "$${GITHUB_WORKFLOW:-local}" "$(NAME)" "$$(git rev-parse HEAD)" "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .build/provenance.json
	cosign attest --yes --type custom --predicate .build/provenance.json $(KEY_FLAGS) $(IMAGE)@$$(cat $(DIGEST_FILE))

verify:
	scripts/verify.sh $(IMAGE)@$$(cat $(DIGEST_FILE))

deploy:
	scripts/deploy.sh $(NAME) $(IMAGE)@$$(cat $(DIGEST_FILE)) $(DEPLOYMENT) "$(COMMITS)"

release: image sign attest verify deploy
```

- **Line 17**: `.PHONY: lint test ci image sign attest verify deploy release`. **Lines 19 to 25**: `lint` runs `python3 -m compileall -q app tests` (compiles every file; a syntax error fails it); `test` runs `python3 -m unittest discover -s tests`; `ci: lint test` ([unittest-and-compileall.md](unittest-and-compileall.md)).
- **Lines 27 to 33**, `image` ("build once, push, keep the digest; the digest, not a tag, is what is signed, verified and deployed"): `docker build -q --build-arg APP_VERSION=$(VERSION) -t $(IMAGE):$(VERSION) .` builds and tags; `docker push $(IMAGE):$(VERSION) | sed -n 's/.*digest: \(sha256:[0-9a-f]*\).*/\1/p' | tail -1 > $(DIGEST_FILE)` pushes and cuts the digest out of the output (`sed -n` prints only lines where the `s/.../.../p` substitution happened; `\(...\)` is a group, `\1` its content; `tail -1` keeps the last such line); `@test -s $(DIGEST_FILE) || { echo "no digest in the push output"; exit 1; }` fails if the file is empty; the last line prints `image: <image>@<digest>` ([docker.md](docker.md), [container-registry.md](container-registry.md)).
- **Lines 35 to 36**, `sign`: `cosign sign --yes $(KEY_FLAGS) $(IMAGE)@$$(cat $(DIGEST_FILE))`. `--yes` answers prompts so CI never waits; the image is named by digest.
- **Lines 38 to 42**, `attest`: `printf '{"builder": "%s", "repository": "%s", "commit": "%s", "built_at": "%s"}\n' "$${GITHUB_WORKFLOW:-local}" "$(NAME)" "$$(git rev-parse HEAD)" "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .build/provenance.json` writes a provenance statement (who built it, from which repository and commit, when, in UTC); then `cosign attest --yes --type custom --predicate .build/provenance.json $(KEY_FLAGS) IMAGE@DIGEST` signs and attaches it.
- **Lines 44 to 45**, `verify`: `scripts/verify.sh IMAGE@DIGEST`. **Lines 47 to 48**, `deploy`: `scripts/deploy.sh NAME IMAGE@DIGEST DEPLOYMENT "COMMITS"` ([bash-and-sh.md](bash-and-sh.md)). **Line 50**, `release: image sign attest verify deploy`: the five steps in order.

## Try it yourself

```bash
make help
```

```bash
make -n run | head -12
```
Prints what `run` would do, without doing it.

```bash
make check
```
Lint and unit tests, no Docker needed. Ends with a coverage table and no `FAIL Required test coverage`.

```bash
cd template && make -n release NAME=demo COSIGN_KEY=/tmp/x.key
```
Shows the five steps and that `--key /tmp/x.key --use-signing-config=false --tlog-upload=false` appears in `sign` and `attest`.

## Mistakes people make

- Spaces instead of a tab to indent a recipe: `*** missing separator`.
- Expecting `cd` to persist between lines.
- Using a tag instead of a digest to refer to the built image. Here `image` saves the digest.
- Writing `$VAR` where the shell variable needs `$$VAR`.
- Forgetting `.PHONY`.

## Check yourself

1. Why two Makefiles? *One is the platform's commands; the other is copied into every service so its CI and laptop share steps.*
2. What does `kill -0 PID` do? *Tests whether the process exists, without sending a signal.*
3. Why is `KEY_FLAGS` defined with `=`? *It is expanded each time, after `COSIGN_KEY` is known.*
4. What does `release` run, in order? *`image sign attest verify deploy`.*
5. How does `image` obtain the digest? *It extracts `sha256:...` from `docker push` output with `sed` and saves it.*

## Further reading

- GNU Make manual: https://www.gnu.org/software/make/manual/make.html
- Conditional functions (`$(if ...)`): https://www.gnu.org/software/make/manual/make.html#Conditional-Functions
