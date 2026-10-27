# cicd-golden-path-and-dora

A small internal platform for a pretend organization of three teams: one command turns a template into a repository with a working, signed pipeline and a catalog entry, every deployment and failure becomes an event, and the four DORA metrics are computed from those events per service and per week.

| | |
| --- | --- |
| **Lesson** | `/prep/cicd/project-golden-path-and-dora`, "A golden-path template and DORA metrics from your own events" (`data-structure-explainer/src/content/tracks/cicd/14-project-golden-path-and-dora.md` in the Plainround app) |
| **Planned hours** | 14 |
| **Level** | Advanced |
| **Architecture** | [ARCHITECTURE.md](ARCHITECTURE.md), the contract in [docs/golden-path-contract.md](docs/golden-path-contract.md), decisions in [docs/adr](docs/adr) |
| **Technology notes** | [tech/](tech/README.md): one beginner file per technology used here (31 files) |

## Prerequisites

| Tool | Version | Used for |
| --- | --- | --- |
| Docker with Compose v2 | 24 or newer (tested with 24.0.6 and Compose v2.23) | PostgreSQL (the event store), a local image registry, and the deployed services |
| Python | 3.12 or 3.13 (tested with 3.13; the workflows use 3.12) | the platform, the collector and the tests |
| cosign | 3.x (tested with 3.1.4; `brew install cosign`) | signing, attestation and verification |
| GNU Make, git, curl | the ones on macOS work | every command below, the generated repositories, the event scripts |
| Python packages | psycopg 3 and PyYAML at run time; pytest, pytest-cov, ruff, mypy, import-linter, pip-audit for development. Pinned with hashes in `requirements.lock` and `requirements-dev.lock`; `make` installs them into `.venv/` | everything |

No cloud account and no real secret. Ports used on `127.0.0.1`: 55441 (PostgreSQL), 55061 (registry), 55442 (collector); change them in `.env`.

## Setup, run, test, stop

```bash
make up              # PostgreSQL, a registry, a local signing key pair, sql/ applied, the collector started
make run             # the whole lesson: three services to production, an unsigned image refused, a simulated month, the DORA tables
make test            # unit and template tests with coverage (no database or Docker needed)
make lint            # ruff, ruff format check, mypy (strict), import-linter, the workflow and template audit
make down            # stops everything and deletes the generated services and local state
```

More targets (`make help` lists them all):

```bash
make demo-services   # generate orders, billing and search and take each to production through its own pipeline
make demo-unsigned   # push an image nobody signed and try to deploy it: refused, and a failed event recorded
make evidence        # every production deployment of each demo service with its commits, and one lead time traced
make simulate        # replace the stored events with a simulated month for three teams (seed 7)
make dora            # the four metrics per service, overall and per week, from the stored events
make dora-sample     # the lesson's sample events.csv: the numbers the lesson expects
make trace SERVICE=orders COMMIT=orders-c1   # one lead time traced to its commit event and its deploy event
make audit           # audit every generated repository against the contract
make test-integration   # the store, the SQL and the collector against PostgreSQL (make up first)
make test-e2e        # one service from the command to production with a real registry, key and compose (make up first)
make audit-deps      # known-vulnerability check of the locked dependencies
```

## Done when: the lesson's checklist and the proof for each line

| # | Done when (from the lesson) | Command | What proves it |
| --- | --- | --- | --- |
| 1 | The contract names three things a team can't turn off, such as signing, required checks and least-privilege deploy credentials, and why. | Read [docs/golden-path-contract.md](docs/golden-path-contract.md); `make audit` | Three controls, each with its reason: required checks on `main`, signed artifacts verified before deploy, and short-lived deploy credentials from the CI identity. Each is a rule with a code (`GP-CHECKS`/`GP-STRICT`/`GP-ADMINS`/`GP-PR`, `GP-SIGN`/`GP-VERIFY`, `GP-OIDC`/`GP-PERMS`/`GP-PIN`/`GP-SECRET`) in [`domain/rules.py`](src/goldenpath/domain/rules.py); deleting the signing step from a generated workflow makes `goldenpath audit` print `GP-SIGN` (a test does exactly that). The exception process (an owner and an expiry, default 30 days) is in the contract. |
| 2 | A new service goes from the command to its first production deployment in under 30 minutes, with no manual step except approving the first pull request. | `make demo-services` (one `goldenpath new-service NAME TEAM --release` per team) | For three imaginary teams, from the command to a verified, healthy container (limit 1,800 s): **orders 83 s, billing 40 s, search 66 s** on a calm Mac (the fresh-clone run), and 597 s, 447 s and 199 s earlier the same night, when the machine's load average was above 100 and the Docker daemon took minutes for a build. Where the seconds went for orders on the calm run: lint 0.8, test 0.4, image 43.7 (build and push), sign 5.9, attest 5.3, verify 6.2, deploy 17.1. The one manual step, approving the first pull request, does not exist locally (there is no pull request), so the command performs it for you. A person as owner (`alice`) stops the command before anything is published. |
| 3 | An unsigned image is refused at deployment, and a search of the generated repository finds no long-lived credential. | `make demo-unsigned`; `make audit`; `goldenpath audit .local/services/orders` | `make demo-unsigned` pushes an image by hand, never signed: `Error: no signatures found`, `deploy refused: ... does not verify`, `deploy exit status: 1 (refused)`, nothing runs, and a `failed` event with detail `signature` is recorded: the `refused` column of the metrics table reads 1 for `orders` afterwards. `goldenpath audit` reports `conforms to the golden path contract` for every generated repository; `GP-SECRET` searches every file for AWS keys, private keys, GitHub tokens and `secrets.*_PASSWORD`-style references (tests plant each and see them found). The generated workflow gets a short-lived identity token instead of a stored key. |
| 4 | You can list every production deployment of a service with the commits it contained. | `make evidence` (or `make deployments SERVICE=orders`); `sql/003_queries.sql` | `orders-d1  commits: fbbd4c2`, `billing-d1  commits: 220965f`, `search-d1  commits: d9a820e` for the real services (fresh-clone run); for the sample, `goldenpath deployments billing --csv data/events-sample.csv` prints `e1  commits: b1, b2, b3, b4`, and the SQL view `deploy_commits` gives the same rows. |
| 5 | A dashboard or table shows all four per service per week, and you can trace one lead-time value back to its commit and deployment events. | `make dora`; `make trace SERVICE=orders COMMIT=orders-c1`; `make dora-sample` | `make dora` prints the overall table and one table per week of the simulated month (below). `goldenpath trace orders orders-c1` (the simulated month) prints `commit event: 2026-09-07 15:38 ... commit orders-c1`, `deploy event: 2026-09-07 18:10 ... deploy orders-d3:orders-c1` and `lead time: 2.5 h`. For the lesson's sample the numbers match its table exactly (next section). |
| 6 | The README explains the difference with the data, and lists one way each metric could be gamed and the guard you would add. | the sections "What the numbers hide" and "Gaming the metrics" below | Below, with the simulated month. |

## Tests

In the fresh-clone run: `make test` 113 passed (domain and application at 99% coverage), `make lint` clean, `make test-integration` 6 passed against PostgreSQL, `make test-e2e` 3 passed (a service from the command to production with a real registry, key and compose, and an unsigned image refused).

## Reading the sample: the lesson's table, reproduced

`make dora-sample` reads [`data/events-sample.csv`](data/events-sample.csv) (the lesson's file) through the same domain code and prints:

```text
service  deploys/week  median lead time  change fail rate  recovery time  batch  empty  open  refused
billing  1             62.0 h            100%              240 min        4.0    0      0     0
orders   4             4.0 h             25%               30 min         1.0    0      0     0
```

How one value is built, from the lesson: the `orders` lead times are 0.5, 3.5, 4.0, 5.0 and 66.0 hours (commits `a4`, `a2`, `a3`, `a1`, `a5`) and the median of five values is the third, 4.0; `billing` has 26, 50, 74 and 98 hours, median 62.0. The same numbers come out of SQL (`make test-integration`, 6 tests, passed in the fresh-clone run): `sql/003_queries.sql` run on the seed (services `sample-orders` and `sample-billing`) gives the table below, and `tests/integration` asserts that SQL and Python agree on a real PostgreSQL.

## What the numbers hide

`make simulate` replaces the stored events with a simulated month (four weeks from 2026-09-07, seed 7) for the three teams: `orders` deploys after every merge, `billing` batches a week of commits into one Friday deployment, `search` deploys on Tuesdays and Thursdays. `make dora` printed, from the events only:

```text
service  deploys/week  median lead time  change fail rate  recovery time  batch  empty  open  refused
billing  1             47.2 h            25%               419 min        9.5    0      0     0
orders   15            1.8 h             5%                18 min         1.0    0      0     0
search   2             21.4 h            25%               113 min        4.5    0      0     0
```

and one table per week (for example week 3: `billing` 1 deployment, 45.5 h, 100% failed, 419 min to recover, 9 commits in it; `orders` 16 deployments, 1.8 h, 12%, 17 min). The pattern is the lesson's: the team that batches has a lead time of days (the oldest commit of a batch waits for Friday), fails more often and takes longer to recover, and the metrics only make sense read together: `billing`'s 25% over four deployments is one failure, not a trend, and in three of its four weeks it has no failure at all, so no recovery time (`n/a`, never zero). The batch size column explains the rest: a deployment of 9.5 commits is hard to understand when it fails.

**This is a model, not a measurement.** The simulation encodes that a bigger change fails more often and takes longer to recover from ([ADR 0006](docs/adr/0006-the-simulation-states-its-assumptions.md)); what the comparison shows is what the metrics reveal given that assumption. The same code with other seeds gives other numbers; a test asserts that the pattern (lower lead time, higher frequency and faster recovery for the small-change team) holds for twenty seeds.

## Gaming the metrics

Each metric can be gamed, and each has a guard, built where it is cheap:

| Metric | How it can be gamed | The guard |
| --- | --- | --- |
| Deployment frequency | Split one deployment into many empty ones. | **Built.** A deployment with no commits is counted in its own `empty` column and never in the frequency; the batch size is shown beside the four metrics. |
| Change fail rate | Define "failure" narrowly, or roll back quietly and call it a success. | **Built in part.** A `failed` event comes from the thing that decides, with a reason (`rollback`, `incident`, `health-check`, `signature`); a rolled-back deployment counts as failed, and a refused deployment is reported (`refused`). The written definition is in [the contract](docs/golden-path-contract.md). Not built: a rework rate (the stretch). |
| Lead time | Start the clock at a later event, or edit the commit time. | **Built.** Every event carries the pipeline's clock; nothing reads Git history or a developer-set field, and `goldenpath trace` prints the two events behind any value ([ADR 0001](docs/adr/0001-events-come-from-the-pipelines-clock.md)). |
| Recovery time | Mark `recovered` before service is really restored. | **Not built.** `recovered` should come from a health check that is not under the team's control; here it comes from the sender. A failure with no recovery is counted as `open`, never as a short time. |

The metrics are for learning, not for ranking teams or people; a team rewarded on one of them will move that one.

## Stretch goals

| Stretch (from the lesson) | Built? |
| --- | --- |
| Add the deployment rework rate and decide how to tell an unplanned, incident-driven deployment from a planned one. | No. The groundwork is there: a `failed` event carries a `detail` (`rollback`, `incident`, `health-check`, `signature`), which is what a rework-rate would classify on. |
| Add a scorecard that checks each catalog entry for an owner, a runbook link and an alert. | Partly. The catalog rules check the owner (a registered team), the runbook (an https link), the lifecycle and the SLO at generation and at every audit. The alert check is not built. |
| Let a team opt out of one default with an expiring exception that the platform tracks. | Partly. Every repository has `exceptions:` in `.golden-path.yaml` and [the contract](docs/golden-path-contract.md) says how they work and that they expire. The platform does not read or expire them yet. |

## What is simplified for teaching

Only what the lesson scopes out, plus where this build differs from the lesson's text:

- **Keyless signing is written, not run.** The template's workflow signs with the CI job's identity token and verifies by workflow identity and issuer. That needs GitHub's identity provider and the public Sigstore services, so the local run signs with a key pair created by `make up` (`.local/keys`, never in a generated repository) and verifies with the public key. Everything else is the same make targets.
- **The cluster admission policy of step 3 is not built.** Deployments here go to compose; the deploy script verifies the signature and the attestation before it starts a container, so an unsigned image cannot be deployed by that path. On a cluster the same rule belongs in an admission controller, so that a manual `kubectl apply` is refused too ([ADR 0003](docs/adr/0003-sign-in-ci-with-the-identity-and-verify-twice.md)).
- **No GitHub repository is created.** `gh repo create` is replaced by a local bare remote; `protection.json` (the real branch-protection payload) is generated and audited but not applied, so "approving the first pull request" is the one manual step and the command performs it for you.
- **The collector authenticates with a shared token locally** and with the CI identity token in a generated workflow; verifying GitHub's token (signature, audience, repository claim) is not built.
- **The service catalog is a folder of YAML files**, not a Backstage instance.
- **Lead time of the demo services** starts at the commit event the generator posts when it publishes the repository, so it is short by construction; the simulated month is where lead times vary.
- **The simulation is a model with stated assumptions** ([ADR 0006](docs/adr/0006-the-simulation-states-its-assumptions.md)): bigger changes fail more often and take longer to recover from. Step 6's comparison shows what the metrics reveal given that assumption; it is not evidence about real teams.
- **Dates:** the simulated month is September 2026 (it starts on 2026-09-07), a fixed window so that results are the same on every run.

## Project structure

```text
src/goldenpath/
  domain/            events, the four metrics, the catalog rules, the contract rules, the simulation.
                     Depends on nothing outside the standard library.
  application/       record events, measure, generate a service, and the ports they need.
                     Depends on domain only.
  infrastructure/    PostgreSQL and CSV stores, the template renderer, the file catalog, the repository auditor,
                     git, the collector's HTTP client, the local pipeline runner, settings, logging.
                     Depends on application and domain.
  interfaces/        the goldenpath command, the event collector (HTTP). Nothing depends on it.
template/            the golden path: the service skeleton, Dockerfile, Makefile, workflow, scripts, protection.json,
                     catalog-info.yaml. Placeholders __NAME__, __OWNER__, __RUNBOOK__, __PLATFORM_REF__.
catalog/             teams.yaml: the teams that may own a service.
sql/                 001_schema.sql (DDL), 002_seed.sql (DML: the lesson's sample), 003_queries.sql (the metrics in SQL).
data/                events-sample.csv: the lesson's sample events.
tests/
  unit/              domain, application (in-memory fakes), infrastructure adapters, the collector over real sockets, the command.
  template/          the template generated for three imaginary teams, with real git and real make.
  integration/       the store and the SQL against PostgreSQL.
  e2e/               one service to production with a real registry, key and compose.
scripts/             lint_workflows.py: audits the template and the platform's workflow (make lint runs it).
docs/                golden-path-contract.md and adr/ (six decision records).
.github/workflows/   the platform's own CI (check, integration with a PostgreSQL service container, audit).
docker-compose.yml   PostgreSQL 16 and a registry.     pyproject.toml  metadata and every tool's configuration.
requirements*.lock   hash-pinned dependencies.         Makefile        the only commands a reader needs (make help).
```

The dependency rule (domain depends on nothing; application on domain; infrastructure and interfaces on both; nothing on interfaces) is enforced by `make lint` through import-linter, which also forbids `psycopg`, `yaml`, `subprocess`, `http` and `urllib` in `domain` and `application`.

## SQL

`make up` applies `sql/001_schema.sql` (the `events` table with its checks and a unique constraint that makes a retried event harmless; the views `deploy_commits` and `lead_times`) and `sql/002_seed.sql` (the lesson's sample as services `sample-orders` and `sample-billing`). `sql/003_queries.sql` has the three queries of steps 4 and 5, each with a one-line comment: every deployment with its commits, a lead time traced to its two events, and the four metrics in SQL.

## Troubleshooting

- **A port is in use:** change `POSTGRES_PORT`, `REGISTRY_PORT` or `COLLECTOR_PORT` in `.env` and `make down && make up`.
- **A step times out on a busy machine:** the health checks and the collector client allow 20 to 30 seconds because a laptop under heavy load (the numbers below were measured at a load average above 100) is slow; give `make run` more time rather than a shorter timeout.
- **`cosign` prints deprecation warnings** about `--use-signing-config` and `--tlog-upload` when it signs with a local key; they are expected with cosign 3.
- **The collector is a background process:** `make up` starts it (log in `.local/logs/collector.log`), `make down` stops it.

## Author and license

Written by Sumit Srivastava. Released under the MIT License, see [LICENSE](LICENSE). Changes are in [CHANGELOG.md](CHANGELOG.md).
