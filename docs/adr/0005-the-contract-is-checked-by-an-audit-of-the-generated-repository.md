# 5. The contract is a template plus an audit, not a reusable workflow

Status: accepted, 2026-10-27

## Context

"Cannot be turned off" has to mean something. A reusable workflow owned by the platform makes the steps impossible to remove from a team's pipeline, but it needs a second repository and a published reference to run at all.

## Decision

The template generates a complete workflow and `scripts/`. Conformance is checked by code: `goldenpath audit` (and the generator itself, before anything is published, and `make lint` on the template) applies the rules in `goldenpath/domain/rules.py` to the workflow, `protection.json`, the catalog entry and every file's text. Removing the signing step, the identity-token permission, the pinning of an action or the required checks fails the audit with a named rule; an owner that is a person fails the catalog check.

## Alternatives considered

- **A reusable workflow in a platform repository:** stronger against removal, and the better design once there is a platform repository to publish it from. The template's steps are one `make` target each, so moving them behind `uses:` later changes the template, not the teams' code.
- **Trust and review:** the first team that finds a rule annoying removes it.

## Consequences

- The audit is a regular check the platform can run over every repository it has generated (`make audit`), not only at creation.
- A team can still edit its repository; the platform finds out at the next audit, which is the lesson's "exceptions are explicit and expire".
