# __NAME__

A service generated from the golden path (platform commit `__PLATFORM_REF__`). It owns nothing but its code: the pipeline,
the signing, the deploy credentials and the catalog entry come from the template and cannot be turned off.

| | |
| --- | --- |
| Owner | `__OWNER__` (a team, not a person) |
| Runbook | __RUNBOOK__ |
| SLO | availability 99.9% over 30 days |

## What you get

- `.github/workflows/ci.yml`: `lint`, `test` and `release` run on every push; `release` runs on `main` only. Every action is pinned to a full commit SHA, the workflow has read-only permissions, and only the release job may ask for an identity token.
- `release` builds one image, pushes it, **signs** it, attaches a provenance statement, **verifies** both, and only then deploys that digest. An image that does not verify is never deployed.
- No stored cloud key or deploy password: the release job gets a short-lived identity token from the CI system (OIDC).
- `protection.json`: the branch protection to apply to `main` (required checks `lint`, `test`, `release`, branch up to date, pull request required, administrators included).
- `catalog-info.yaml`: owner (a team), lifecycle, runbook and SLO.

## Run it

```bash
make ci        # lint and test
make release   # image, sign, attest, verify, deploy (see the Makefile for the variables)
```

## What you may change

The language, framework and tests (`app/`, `tests/`), the number of environments, your own alerts. Anything touching `.github/workflows/ci.yml`, `scripts/`, `protection.json` or `catalog-info.yaml` is audited by the platform (`goldenpath audit`); ask in the platform channel for an exception, and every exception expires (default 30 days).
