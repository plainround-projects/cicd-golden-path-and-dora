# Make and the Makefiles

## What it is

`make` runs recipes written in a file called `Makefile`. A Makefile is a list of **targets**. Each target has **prerequisites** (things that must be ready first) and a **recipe** (shell commands). Make compares file times: if a target file is newer than all its prerequisites it skips the recipe. macOS ships GNU Make 3.81; Linux CI has 4.x. These files use only features common to both.

## Why this repository uses it

There are **two** Makefiles, and both follow one rule: *a workflow job is one `make` target, so a laptop runs the same steps as CI.*

- The root `Makefile` is the **platform's**: `make up`, `make run`, `make test`, `make lint`, `make down`.
- `template/Makefile` is **copied into every generated service**: `make ci` and `make release` (image, sign, attest, verify, deploy).

## Where it appears

| Path | Role |
|---|---|
| `Makefile` | Platform targets (about 30 documented ones; `make help` lists them). |
| `template/Makefile` | The service's pipeline steps: `lint`, `test`, `ci`, `image`, `sign`, `attest`, `verify`, `deploy`, `release`. |
| `.github/workflows/ci.yml` and `template/.github/workflows/ci.yml` | Call `make check`, `make audit-deps`, `make lint`, `make test`, `make image`, `make sign`, ... |
| `src/goldenpath/infrastructure/local_pipeline.py` | Runs `make --no-print-directory <step>` for each step, timed. |

## How it works underneath

- `make test` builds prerequisites first, then runs the recipe. Each recipe line runs in its **own** shell; a trailing `\` joins lines.
- `@` hides the command line; `-` ignores its errors. `$(X)` is a Make variable, `$$X` a shell variable.
- `?=` sets a variable only if the caller did not; `:=` expands once; `=` expands each time it is used (needed for `KEY_FLAGS` below).
- `.PHONY` names targets that are actions, not files.
- A **stamp file** such as `.venv/.installed` records that a long step is done.
- `export VAR` passes a variable to every command Make starts.

## Walkthrough of this repository's use

### The platform `Makefile`: environment and `.env`

```make
STAMP := $(VENV)/.installed
-include .env
export POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD LOG_LEVEL COLLECTOR_PORT COLLECTOR_URL COLLECTOR_TOKEN \
       REGISTRY RUNBOOK_BASE COSIGN_PASSWORD
```
`.env` is read as Make assignments; `export` hands eleven settings to the Python programs and to `cosign` ([dotenv.md](dotenv.md)).

```make
$(STAMP): requirements-dev.lock pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --require-hashes -r requirements-dev.lock
	$(VENV)/bin/pip install -q --no-deps -e .
	touch $@
```
The stamp pattern: rebuild the environment only when the lock or `pyproject.toml` changes ([pip-and-hash-locking.md](pip-and-hash-locking.md)).

### `up`: the platform's local infrastructure

```make
up: $(STAMP) .env
	$(COMPOSE) up -d --wait
	$(MAKE) --no-print-directory db
	@mkdir -p $(KEYS) .local/logs
	@test -f $(KEYS)/cosign.key || (cd $(KEYS) && COSIGN_PASSWORD="$(COSIGN_PASSWORD)" cosign generate-key-pair >/dev/null && echo "created a local signing key pair in $(KEYS)")
	@$(MAKE) --no-print-directory collector
```
Start PostgreSQL and the registry and wait for health ([docker-compose.md](docker-compose.md)); apply the SQL; make a local signing key pair **once** (`test -f ... || (...)` means "if the key file is missing, create it"); start the collector. A subshell `( ... )` lets `cd` apply to the commands inside only.

### `collector`: a background process

```make
collector:
	@if [ -f .local/collector.pid ] && kill -0 $$(cat .local/collector.pid) 2>/dev/null; then echo "collector already running"; else \
	  nohup $(VENV)/bin/goldenpath collector > .local/logs/collector.log 2>&1 & echo $$! > .local/collector.pid; \
	  for i in $$(seq 1 40); do curl -fsS http://127.0.0.1:$(COLLECTOR_PORT)/healthz >/dev/null 2>&1 && break; sleep 0.5; done; \
	  curl -fsS http://127.0.0.1:$(COLLECTOR_PORT)/healthz && echo " collector up on port $(COLLECTOR_PORT)"; fi
```
`kill -0 PID` sends no signal; it only tests that the process exists. `nohup ... &` starts the collector in the background and keeps it alive when the terminal closes; `$$!` is its process id (`$!` for the shell), saved in `.local/collector.pid`. The loop asks `/healthz` up to 40 times, half a second apart, and stops (`break`) on the first success ([curl.md](curl.md)). `stop-collector` kills the process using the saved id.

### `run`: the whole lesson

```make
run: up demo-services demo-unsigned evidence simulate dora
	$(VENV)/bin/goldenpath trace orders orders-c1
```
Prerequisites run left to right: infrastructure, three services to production, an unsigned image refused, the evidence the pipelines recorded, a simulated month, the DORA tables, then one traced lead time.

```make
demo-services:
	@for pair in orders:team-orders billing:team-billing search:team-search; do \
	  rm -rf .local/services/$${pair%%:*} .local/remotes/$${pair%%:*}.git; \
	  $(VENV)/bin/goldenpath new-service $${pair%%:*} $${pair##*:} --release || exit 1; \
	done
```
`${pair%%:*}` is "`pair` with everything from the first `:` removed" (the service name); `${pair##*:}` is "everything up to the last `:` removed" (the team).

### `test`, `lint`, `check`

`test` runs `tests/unit` and `tests/template` with coverage, then `coverage report ... --fail-under=95` on the domain and application packages only. `lint` runs ruff, mypy, import-linter and `scripts/lint_workflows.py`. `check: lint test` needs no database or Docker.

### `down`

```make
down: stop-collector
	-@for dir in .local/services/*; do [ -d "$$dir" ] && IMAGE_REF=unused $(COMPOSE) -p $$(basename $$dir)-production -f $$dir/deploy/compose.yaml down -v 2>/dev/null; done; true
	$(COMPOSE) down -v
	rm -rf .local
```
Remove each generated service's production containers, then the platform's, then all local state.

### `template/Makefile`

```make
REGISTRY ?= localhost:55061
VERSION ?= $(shell git rev-parse --short HEAD)
IMAGE := $(REGISTRY)/$(NAME)
DIGEST_FILE := .build/digest
```
`NAME := __NAME__` is replaced when the service is generated.

```make
KEY_FLAGS = --timeout=15m $(if $(COSIGN_KEY),--key $(COSIGN_KEY) --use-signing-config=false --tlog-upload=false,)
```
`=` (not `:=`) because it is expanded each time it is used. `$(if COND,then,else)`: with a local key file, sign with it and do not use the public log; with none, add nothing and cosign signs keyless as the CI identity ([cosign.md](cosign.md)).

```make
image:
	@mkdir -p .build
	docker build -q --build-arg APP_VERSION=$(VERSION) -t $(IMAGE):$(VERSION) .
	docker push $(IMAGE):$(VERSION) | sed -n 's/.*digest: \(sha256:[0-9a-f]*\).*/\1/p' | tail -1 > $(DIGEST_FILE)
	@test -s $(DIGEST_FILE) || { echo "no digest in the push output"; exit 1; }
```
Build once, push, and cut the **digest** out of push's output with `sed -n 's/.../.../p'` (print only lines where the substitution happened). The digest, not a tag, is what is signed, verified and deployed. `test -s` fails if the file is empty.

```make
attest:
	@printf '{"builder": "%s", "repository": "%s", "commit": "%s", "built_at": "%s"}\n' \
	  "$${GITHUB_WORKFLOW:-local}" "$(NAME)" "$$(git rev-parse HEAD)" "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .build/provenance.json
	cosign attest --yes --type custom --predicate .build/provenance.json $(KEY_FLAGS) $(IMAGE)@$$(cat $(DIGEST_FILE))
release: image sign attest verify deploy
```
Write a small provenance statement and attach it to the image digest. `release` chains the five steps in order.

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
