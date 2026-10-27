# GitHub Actions

## What it is

**GitHub** is a website that stores Git repositories and lets people work on them together. **GitHub Actions** is the part of GitHub that runs programs for you when something happens in a repository. The thing you write to describe what to run is a **workflow**: a text file in the **YAML** format ([yaml.md](yaml.md)) stored in the folder `.github/workflows/` of the repository.

The words you need:

- An **event** is something that happens: a person pushes commits, someone opens a pull request, a timer fires. A workflow says which events start it (`on:`).
- A **pull request** is a request to merge one branch of commits into another, with a place to discuss and check it first.
- A **job** is a group of steps that runs on one machine. Jobs normally run at the same time, unless one says it needs another.
- A **runner** is the machine a job runs on. GitHub provides fresh virtual machines; `ubuntu-latest` means a current Ubuntu Linux one. Every job gets a clean runner, so nothing is left over from earlier jobs.
- A **step** is one thing a job does. Either a shell command (`run:`) or a ready-made **action** (`uses:`), which is a reusable piece of automation published in another repository, such as "check out the code" or "install Python".
- An **artifact** is a file or folder a job uploads so that later jobs (or you) can download it.
- An **output** is a small piece of text a job publishes for jobs that depend on it.
- A **required check** is a job name that the repository's *branch protection* waits for before it lets a pull request merge.

## Why this repository uses it

Two different workflows live here, and the difference is the lesson.

1. `.github/workflows/ci.yml` is the **platform's own** check: format, lint, types, import rules, workflow audit, unit tests with coverage, the PostgreSQL integration tests, and a dependency audit.
2. `template/.github/workflows/ci.yml` is the **golden path**: the pipeline every generated service receives. It lints and tests, and on `main` it builds an image, **signs** it, attaches a provenance statement, **verifies** both and deploys the digest, with no stored secrets.

The platform audits the second file in every generated repository, so a team cannot quietly remove the signing or the verification ([the contract](../docs/golden-path-contract.md)).

## Where it appears

| File | Role |
|---|---|
| `.github/workflows/ci.yml` | Platform checks: jobs `check`, `integration`, `audit`. |
| `template/.github/workflows/ci.yml` | The service pipeline: jobs `lint`, `test`, `release`. |
| `template/protection.json` | Branch protection that makes `lint`, `test` and `release` required ([json.md](json.md)). |
| `src/goldenpath/domain/rules.py` | `check_workflow`: the rules the audit applies. |
| `scripts/lint_workflows.py` | Applies those rules to both workflow files in `make lint`. |

## How it works underneath

- GitHub reads the workflow file from the **commit being tested**. Changing the pipeline is therefore an ordinary change that is reviewed like any other.
- Jobs run in parallel unless a job lists another in `needs:`. Data moves between jobs only as artifacts and outputs, because each job has its own clean machine.
- A job that is **skipped** by an `if:` condition is reported as *passed* (skipped) to branch protection. A workflow that never **starts** (because of a `paths:` filter, for example) reports *nothing*, and a required check that never reports leaves the pull request waiting for ever. This difference drives a design choice below.
- `${{ ... }}` marks an **expression**: GitHub evaluates it before the step runs. `github.sha` is the commit being built, `github.ref` the branch name, `github.event.pull_request.base.sha` the commit a pull request is based on, `needs.JOB.outputs.NAME` an output of another job, `secrets.NAME` a secret the repository owner stored.
- `GITHUB_OUTPUT` is the name of a file. A step appends `name=value` lines to it, and GitHub turns them into step outputs.
- `permissions:` limits what the automatic **token** (`GITHUB_TOKEN`, a password GitHub hands each run) is allowed to do.
- `concurrency:` makes runs of the same group take turns or cancel each other.

## Walkthrough of this repository's use

### The golden-path workflow, `template/.github/workflows/ci.yml`

```yaml
# The golden path's pipeline. Do not remove the sign, attest, verify or deploy steps, the identity-token permission
# of the release job, or the pinning of actions: `goldenpath audit` fails the platform's own check when they are gone.
name: ci

on:
  push:
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}
```

- **Lines 1 and 2** are comments: do not remove the sign, attest, verify or deploy steps, the identity-token permission of the release job, or the pinning of actions: `goldenpath audit` fails the platform's own check when they are gone. **Line 3**: `name: ci`.
- **Lines 5 to 7**: `on:` lists the events that start the workflow: `push` (any branch receives commits) and `pull_request`. Empty values mean "all of these, with no filters".
- **Lines 9 and 10**: `permissions: contents: read` gives the run's automatic token (a password GitHub creates for the run) permission to read the repository and nothing else. This is **least privilege**: a step that is tricked into something nasty cannot push code or change settings.
- **Lines 12 to 14**: `concurrency:` with `group: ci-${{ github.ref }}` allows one run per branch at a time. `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}` is an *expression*: on every branch **except `main`** an older run is cancelled when a newer commit arrives; on `main` every run is allowed to finish, because every merge must be fully processed.

```yaml
jobs:
  lint:
    name: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
        with:
          python-version: "3.12"
      - run: make lint

  test:
    name: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
        with:
          python-version: "3.12"
      - run: make test
```

- **Line 16**: `jobs:`. **Lines 17 to 25**, job `lint`: `name: lint` is the name branch protection checks; `runs-on: ubuntu-latest` picks a fresh Linux machine. Step 1: `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2` downloads the repository; the long hexadecimal text is a full **commit id**, which pins the action to exactly one version of its code (a tag like `v4` could be moved to different code later, a commit id cannot); the comment records the human version. Step 2: `actions/setup-python@a26af69b...` (v5.6.0) with `python-version: "3.12"` (quoted so YAML keeps it as text) installs Python. Step 3: `run: make lint` ([make.md](make.md)).
- **Lines 27 to 35**, job `test`: the same three steps with `make test`.

```yaml
  # Runs on main only (a skipped job counts as passing for the required check on a pull request).
  release:
    name: release
    needs: [lint, test]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      packages: write
      id-token: write # a short-lived identity token for keyless signing and for the event collector; no stored key
    env:
      REGISTRY: ghcr.io/${{ github.repository_owner }}
      EVENTS_URL: ${{ vars.PLATFORM_EVENTS_URL }}
```

- **Line 37** (comment): runs on `main` only; a skipped job counts as passing for the required check on a pull request.
- **Lines 38 to 41**: job `release`; `needs: [lint, test]` waits for both; `if: github.ref == 'refs/heads/main'` runs the job only on `main`; `runs-on: ubuntu-latest`; `environment: production` ties the job to a named deployment target (a place where GitHub can enforce rules such as required approvers).
- **Lines 44 to 47**, the **job-level** permissions: `contents: read`, `packages: write` (push the image to GitHub's container registry) and `id-token: write` ("a short-lived identity token for keyless signing and for the event collector; no stored key", [oidc-identity-tokens.md](oidc-identity-tokens.md)). Only this job may request an identity token; the top-level permissions do not include it.
- **Lines 48 to 50**: `env:` sets `REGISTRY: ghcr.io/${{ github.repository_owner }}` (GitHub's container registry under the owner's name) and `EVENTS_URL: ${{ vars.PLATFORM_EVENTS_URL }}` (the collector's address from a repository *variable* that the platform sets).

```yaml
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with:
          fetch-depth: 0
      - uses: sigstore/cosign-installer@d58896d6a1865668819e1d91763c7751a165e159 # v3.9.2
      - uses: docker/login-action@74a5d142397b4f367a81961eba4e8cd7edddf772 # v3.4.0
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - run: scripts/emit-event.sh commit "$(git rev-parse --short HEAD)"
      - run: make image
      - run: make sign
      - run: make attest
      - run: make verify
      - run: make deploy COMMITS="$(git rev-parse --short HEAD)" DEPLOYMENT="${{ github.run_id }}"
```

- **Lines 52 to 54**: check out with `fetch-depth: 0` (the whole history). **Line 55**: `sigstore/cosign-installer@d58896d6...` (v3.9.2) puts the `cosign` program on the runner ([cosign.md](cosign.md)). **Lines 56 to 60**: `docker/login-action@74a5d142...` (v3.4.0) signs in to `ghcr.io` with `username: ${{ github.actor }}` and `password: ${{ secrets.GITHUB_TOKEN }}`, the automatic token: no stored password.
- **Lines 61 to 66**, in order: `scripts/emit-event.sh commit "$(git rev-parse --short HEAD)"` records a `commit` event ([bash-and-sh.md](bash-and-sh.md)); `make image` builds and pushes once and saves the digest; `make sign`; `make attest`; `make verify`; `make deploy COMMITS="$(git rev-parse --short HEAD)" DEPLOYMENT="${{ github.run_id }}"`. The deployment id is GitHub's unique run number. `make deploy` runs `deploy.sh`, which verifies **again**, so the signature is checked twice: once as a step, once at the door of deployment.

### The platform's own workflow, `.github/workflows/ci.yml`

```yaml
name: ci

on:
  push:
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}

jobs:
  check:
    name: Format, lint, types, import rules, workflow audit, unit tests with coverage
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: requirements-dev.lock
      - run: make check

```

- **Lines 3 to 12** are the same trigger, permissions and concurrency as above. **Lines 14 to 25**, job `check`: its `name` is a long description (GitHub shows it; a required check would use this exact text); steps: checkout, `setup-python` with `cache: pip` and `cache-dependency-path: requirements-dev.lock` (pip's downloads are cached and the lock file is the cache key: reused while unchanged, replaced when dependencies change), and `make check` (lint and unit tests, no database or Docker).

```yaml
  integration:
    name: Store, collector and SQL (PostgreSQL service container)
    runs-on: ubuntu-latest
    env:
      POSTGRES_HOST: localhost
      POSTGRES_PORT: "5432"
      POSTGRES_DB: events
      POSTGRES_USER: platform
      POSTGRES_PASSWORD: test-only-password # a throwaway for a container that lives only for this run
      PGPASSWORD: test-only-password
    services:
      postgres:
        image: postgres:16.4-alpine
        env:
          POSTGRES_DB: events
          POSTGRES_USER: platform
          POSTGRES_PASSWORD: test-only-password
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -h 127.0.0.1 -U platform -d events"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
```

- **Lines 27 to 50**, job `integration`: `env:` sets the database variables and `PGPASSWORD` (read by `psql` so it does not ask for a password); the comment says the password is a throw-away for a container that lives only for this run. `services: postgres:` starts a database container beside the job: `image: postgres:16.4-alpine`, its own `env:`, `ports: - 5432:5432`, and `options: >-` (a folded string, [yaml.md](yaml.md)) with `--health-cmd "pg_isready -h 127.0.0.1 -U platform -d events"`, `--health-interval 5s`, `--health-timeout 5s`, `--health-retries 10`: Docker flags that define the health check GitHub waits on.

```yaml
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: requirements-dev.lock
      - run: make install
      - run: make db PSQL="psql -v ON_ERROR_STOP=1 -q -h localhost -p 5432 -U platform -d events"
      - run: make test-integration

  audit:
    name: Known-vulnerability check of the locked dependencies
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
        with:
          python-version: "3.12"
      - run: make audit-deps
```

- **Lines 51 to 60**: steps checkout, setup Python, `make install`, `make db PSQL="psql -v ON_ERROR_STOP=1 -q -h localhost -p 5432 -U platform -d events"` (apply the SQL, overriding `PSQL` to talk to the service container; `-h` host, `-p` port, `-U` user, `-d` database), `make test-integration`.
- **Lines 62 to 70**, job `audit`: checkout, setup Python, `make audit-deps` ([pip-audit.md](pip-audit.md)).

### The rules the platform enforces on a workflow (`rules.check_workflow`)

| Code | Rule |
|---|---|
| `GP-PIN` | Every `uses:` is a local path or pinned to a full 40-character commit id. |
| `GP-MOVING` | No `:latest`, `@main`, `@master`, `@latest`. |
| `GP-SIGN`, `GP-VERIFY` | Some step signs the artifact and some step verifies it before deploy. |
| `GP-OIDC` | The release job has `id-token: write`. |
| `GP-PERMS` | The top-level permissions are `contents: read` only; `id-token` is granted per job. |

`scripts/lint_workflows.py` applies all of them to the template's workflow and only GP-PIN, GP-MOVING and GP-PERMS to the platform's own.

## Try it yourself

```bash
make workflows
```
Expect `workflows ok`.

```bash
.venv/bin/python -c "
import json
from goldenpath.domain import rules
from goldenpath.infrastructure.auditor import load_workflow
doc = load_workflow(open('template/.github/workflows/ci.yml').read())
print(rules.check_workflow(doc))
doc['jobs']['release']['steps'] = [s for s in doc['jobs']['release']['steps'] if s.get('run') != 'make sign']
print([f.code for f in rules.check_workflow(doc)])
"
```
Prints `[]`, then a list that contains `GP-SIGN`: removing the signing step breaks the contract.

```bash
.venv/bin/python -c "import yaml; print(list(yaml.safe_load(open('.github/workflows/ci.yml'))['jobs']))"
```
Expect `['check', 'integration', 'audit']`.

## Mistakes people make

- Granting `id-token: write` at the top of the workflow, so every job can mint tokens. Only `release` has it.
- Pinning to a tag instead of a SHA.
- Storing a cloud key as a secret. The golden path uses short-lived identity tokens.
- Cancelling the run on `main`; here it is never cancelled there.
- Deploying a tag instead of a digest.

## Check yourself

1. Why is `release` skipped on pull requests and still safe as a required check? *A skipped job reports as passed.*
2. Which job may ask for an identity token? *Only `release`.*
3. Why pin actions to a SHA? *A tag can be re-pointed; a SHA cannot.*
4. Where is the signature checked? *In `make verify` and again inside `deploy.sh`.*
5. What does `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}` do? *Cancels older runs on every ref except `main`.*

## Further reading

- Workflow syntax: https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions
- Permissions and `id-token`: https://docs.github.com/en/actions/security-guides/automatic-token-authentication
- OIDC in Actions: https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect
- Pinned here: checkout v4.2.2, setup-python v5.6.0, cosign-installer v3.9.2, docker/login-action v3.4.0
