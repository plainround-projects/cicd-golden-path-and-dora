# 4. A small collector in front of the event store

Status: accepted, 2026-10-27

## Context

Pipelines of many repositories must record events. Giving each one database credentials would be the stored secret the golden path forbids.

## Decision

An HTTP collector (`goldenpath collector`, `POST /events`, a JSON event or a list) validates every event with the domain's rules and writes it to PostgreSQL, ignoring duplicates (a retried pipeline step cannot count twice). It answers 401 without the bearer token, 400 for an invalid event, 413 for an oversized body and 503 when the store is down, so a pipeline step can retry. In CI the generated workflow authenticates with the job's identity token (audience `goldenpath-events`), fetched at run time by `scripts/emit-event.sh`; a production collector verifies that token's signature, audience and repository claim. The local collector compares a shared bearer token with `hmac.compare_digest`; that token lives in the platform's environment and never in a generated repository.

## Alternatives considered

- **A table the pipelines write to directly:** a database credential in every repository.
- **A CSV in an object bucket:** no validation, no duplicate protection, a bucket credential in every repository.

## Consequences

- The verification of GitHub's OIDC token is not built here; the README says so.
- The collector is a second process (`make up` starts it in the background and `make down` stops it).
