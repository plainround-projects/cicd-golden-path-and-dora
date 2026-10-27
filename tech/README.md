# tech: the technologies in this repository, from zero

One file per technology. Each file says what the technology is, why this repository uses it, where it appears, how it works underneath, walks through this repository's own lines, gives commands to try, lists common mistakes, asks five questions and links the official documentation. Read them with the repository open next to you.

## If you have ten minutes

1. [dora-metrics.md](dora-metrics.md): the idea the whole second half of the repository computes.
2. [cosign.md](cosign.md): how an image is signed, attested and verified, and why an unsigned one is refused.
3. [github-actions.md](github-actions.md): the golden-path pipeline job by job, and the permissions that make it safe.

## Reading order

**The language and the build tools**

| File | Role |
|---|---|
| [python.md](python.md) | Python 3.12: the platform, its domain rules and the simulation. |
| [bash-and-sh.md](bash-and-sh.md) | The three scripts of the template: verify, deploy, emit an event. |
| [make.md](make.md) | The platform's `Makefile` and the template's. |
| [pip-and-hash-locking.md](pip-and-hash-locking.md) | Virtual environments, `pip`, hash-checked locks. |
| [uv.md](uv.md) | The tool that writes the lock files. |

**The golden path (what every service gets)**

| File | Role |
|---|---|
| [git.md](git.md) | Creating the repository, the bot identity, commits since the last deploy. |
| [github-actions.md](github-actions.md) | `lint`, `test`, `release`, and the platform's own workflow. |
| [docker.md](docker.md) | The template's `Dockerfile`; images, digests, health checks. |
| [docker-compose.md](docker-compose.md) | The platform's infrastructure and each service's locked-down "production". |
| [container-registry.md](container-registry.md) | Where images are pushed and how their digest is known. |
| [cosign.md](cosign.md) | Signing, attesting and verifying images. |
| [oidc-identity-tokens.md](oidc-identity-tokens.md) | Short-lived credentials in place of stored keys. |
| [unittest-and-compileall.md](unittest-and-compileall.md) | The generated service's own checks. |

**The platform and its metrics**

| File | Role |
|---|---|
| [dora-metrics.md](dora-metrics.md) | The four measures, with the lesson's sample worked through. |
| [http-server.md](http-server.md) | The event collector and the service's `/healthz`. |
| [curl.md](curl.md) | How a shell script sends an event. |
| [postgresql.md](postgresql.md) | The event store, its constraints and views. |
| [sql.md](sql.md) | The metric queries in SQL. |
| [psycopg.md](psycopg.md) | The Python driver for PostgreSQL. |
| [dotenv.md](dotenv.md) | Environment variables and `.env`. |

**The checks and the tests**

| File | Role |
|---|---|
| [pytest.md](pytest.md) | The test runner, coverage and the four kinds of test. |
| [ruff.md](ruff.md) | Lint and format. |
| [mypy.md](mypy.md) | Static types and the ports. |
| [import-linter.md](import-linter.md) | Architecture rules over imports. |
| [pip-audit.md](pip-audit.md) | Known-vulnerability check of the lock. |

**File formats**

| File | Role |
|---|---|
| [yaml.md](yaml.md) | Workflows, compose files, the catalog and the teams list. |
| [toml.md](toml.md) | `pyproject.toml`. |
| [json.md](json.md) | Events on the wire, provenance, branch protection. |
| [csv.md](csv.md) | The lesson's sample events. |
| [markdown.md](markdown.md) | The documentation and the generated README. |
| [editorconfig.md](editorconfig.md) | Shared editor settings. |

## What was not verified

The notes were written against the pinned versions in `requirements-dev.lock` and the files in this repository, and every command that needs only Python, `make`, `git` and `docker compose config` was run. Not re-run when the notes were written, because Docker and the shared machine were out of capacity: anything that starts containers (`make up`, `make run`, `make demo-services`, `make demo-unsigned`, `make test-integration`, `make test-e2e`) and anything that needs the network (`make audit-deps`). The GitHub paths (keyless signing, the identity-token request, branch protection, `ghcr.io`) are written but need a real GitHub repository, and were not run at all; the notes say so where it matters. The tag names cosign uses for signatures in the local registry depend on the cosign version (3.1.4 here).
