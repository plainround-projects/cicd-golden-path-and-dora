# Golden path contract (v1)

Every new service gets a repository with a pipeline, a deploy path, a catalog entry and an owner. One command creates it
(`goldenpath new-service NAME TEAM`); the platform checks the result against this contract before anything is published,
and `goldenpath audit` checks any repository again at any time.

## Cannot be turned off

1. **Required checks on `main`** (`lint`, `test`, `release`; the branch up to date; a pull request; administrators included).
   Why: a red `main` stops everyone, so it is a shared problem. Enforced by: `protection.json` in the repository, rules `GP-CHECKS`, `GP-STRICT`, `GP-ADMINS`, `GP-PR`.
2. **Signed artifacts, verified before deploy**, with a provenance statement attached to the signed digest.
   Why: we must know that what runs is what CI built. Enforced by: the workflow must sign and verify (`GP-SIGN`, `GP-VERIFY`) and the deploy script verifies again, so the deploy path cannot be reached with an unsigned image.
3. **Short-lived deploy credentials from the CI identity** (OIDC). Actions are pinned to full commit SHAs, workflow permissions are read-only by default, and only the release job may ask for an identity token.
   Why: a stored key leaks, and a leaked key lasts. Enforced by: `GP-OIDC`, `GP-PERMS`, `GP-PIN`, `GP-MOVING`, and `GP-SECRET`, which searches every file for what a long-lived credential looks like.

## Teams may choose

Language and framework, test tools, how many environments, their own alerts.

## Owners

The owner in `catalog-info.yaml` is a registered team (`team-<name>` in `catalog/teams.yaml`), never a person. A person leaves, a team stays on call.

## Exceptions

Ask in the platform channel. Each exception has an owner and an expiry date (default 30 days) and is recorded in the repository's `.golden-path.yaml` (`exceptions:`), where the platform can list and expire them. An exception never covers the three controls above for a service that deploys to production.

## What a failed deployment is

A `failed` event is written by the thing that decides a deployment failed, and says which: `rollback` (the platform or a person rolled it back), `incident` (an incident was declared against it), `health-check` (the deploy's own health check failed) or `signature` (the artifact did not verify, so nothing was deployed). A rolled-back deployment is a failed deployment even though the rollback worked.
