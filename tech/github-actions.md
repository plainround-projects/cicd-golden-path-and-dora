# GitHub Actions

## What it is

GitHub Actions is GitHub's built-in automation. **Workflows** are YAML files under `.github/workflows/`. GitHub starts one when an **event** happens (a push, a pull request). A workflow is a set of **jobs**; each job runs on a fresh **runner** (a virtual machine) as a list of **steps**. A step is a shell command (`run:`) or a ready-made **action** (`uses:`).

## Why this repository uses it

Two different workflows live here, and the difference is the lesson.

1. `.github/workflows/ci.yml` is the **platform's own** check: format, lint, types, import rules, workflow audit, unit tests with coverage, the PostgreSQL integration tests, and a dependency audit.
2. `template/.github/workflows/ci.yml` is the **golden path**: the pipeline every generated service gets. It lints, tests, and on `main` builds an image, **signs** it, attaches provenance, **verifies** both and deploys the digest, with no stored secrets.

The platform audits the second file in every generated repository so a team cannot quietly remove the signing or the verification ([the contract](../docs/golden-path-contract.md)).

## Where it appears

| File | Role |
|---|---|
| `.github/workflows/ci.yml` | Platform checks: jobs `check`, `integration`, `audit`. |
| `template/.github/workflows/ci.yml` | Service pipeline: jobs `lint`, `test`, `release`. |
| `src/goldenpath/domain/rules.py` | `check_workflow`: the rules the audit applies to a workflow. |
| `scripts/lint_workflows.py` | Applies those rules to both workflow files in `make lint`. |
| `template/protection.json` | Branch protection that makes `lint`, `test` and `release` required. |

## How it works underneath

- GitHub reads the workflow from the commit being tested.
- Jobs run in parallel unless one lists another in `needs:`. Each job has a clean machine; data moves between jobs as artifacts or small **outputs**.
- A **required check** is a job name that branch protection waits for. A job skipped by `if:` reports as passed.
- The automatic `GITHUB_TOKEN` is limited by `permissions:`. A job may also ask for an **OpenID Connect** identity token with `id-token: write` ([oidc-identity-tokens.md](oidc-identity-tokens.md)).
- `${{ ... }}` is an expression GitHub evaluates before the step runs. `vars.NAME` reads a repository variable, `secrets.NAME` a secret.
- An **environment** (`environment: production`) is a named deployment target that can carry its own rules and approvals.

## Walkthrough of this repository's use

### The golden path workflow

```yaml
on:
  push:
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}
```
Runs on pushes and pull requests. The default token may only read the repository. `concurrency` allows one run per branch and cancels the older one, **except on `main`**, where every merge must finish (an expression decides: `cancel-in-progress` is true on every ref except `main`).

```yaml
  lint:
    name: lint
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
        with:
          python-version: "3.12"
      - run: make lint
```
Every action is pinned to a full 40-character commit SHA, with the version in a comment. A tag can be moved to different code; a SHA cannot. `make lint` runs the same command as a laptop ([make.md](make.md)).

```yaml
  release:
    name: release
    needs: [lint, test]
    if: github.ref == 'refs/heads/main'
    environment: production
    permissions:
      contents: read
      packages: write
      id-token: write # a short-lived identity token for keyless signing and for the event collector; no stored key
```
`release` waits for `lint` and `test`, runs **only on `main`** (on a pull request it is skipped, which counts as passing), and is the only job allowed to ask for an identity token. `packages: write` lets it push the image to GitHub's container registry.

```yaml
    env:
      REGISTRY: ghcr.io/${{ github.repository_owner }}
      EVENTS_URL: ${{ vars.PLATFORM_EVENTS_URL }}
    steps:
      - uses: actions/checkout@11bd7190... # v4.2.2
        with:
          fetch-depth: 0
      - uses: sigstore/cosign-installer@d58896d6... # v3.9.2
      - uses: docker/login-action@74a5d142... # v3.4.0
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
```
`REGISTRY` points at `ghcr.io/<owner>`. The collector's address comes from a repository variable the platform sets. `cosign-installer` puts the `cosign` program on the runner ([cosign.md](cosign.md)). `docker/login-action` signs in to the registry with the automatic `GITHUB_TOKEN`: no stored password.

```yaml
      - run: scripts/emit-event.sh commit "$(git rev-parse --short HEAD)"
      - run: make image
      - run: make sign
      - run: make attest
      - run: make verify
      - run: make deploy COMMITS="$(git rev-parse --short HEAD)" DEPLOYMENT="${{ github.run_id }}"
```
Record the `commit` event, then build, sign, attest, verify, deploy. The deployment id is GitHub's unique run id. `make deploy` calls `deploy.sh`, which verifies again ([bash-and-sh.md](bash-and-sh.md)): the signature is checked twice.

### The platform's own workflow

```yaml
  integration:
    services:
      postgres:
        image: postgres:16.4-alpine
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -h 127.0.0.1 -U platform -d events"
```
A PostgreSQL container next to the job ([postgresql.md](postgresql.md)). The steps are `make install`, `make db PSQL="psql ... -h localhost ..."`, `make test-integration`. The password in `env:` is a throwaway for a container that lives only for the run. `setup-python` with `cache: pip` and `cache-dependency-path: requirements-dev.lock` caches downloads keyed by the lock file's hash.

### The rules the platform enforces on a workflow

| Code | Rule |
|---|---|
| `GP-PIN` | Every `uses:` is pinned to a full commit SHA. |
| `GP-MOVING` | No `:latest`, `@main`, `@master`. |
| `GP-SIGN`, `GP-VERIFY` | A step signs the artifact; a step verifies it before deploy. |
| `GP-OIDC` | The release job has `id-token: write`. |
| `GP-PERMS` | Top-level permissions are `contents: read` only; `id-token` is granted per job. |

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
