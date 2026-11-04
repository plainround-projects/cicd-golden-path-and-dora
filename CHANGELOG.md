# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Drawn architecture and flow figures in `docs/diagrams/`, light and dark, shown in the README.

### Fixed

- ARCHITECTURE.md and README now match the code where they disagreed (see the drawn figures).

## [0.1.0] - 2026-10-27

### Added

- The golden-path template: a small service, a Dockerfile, a Makefile with one target per pipeline step, a workflow with pinned actions, read-only permissions and an identity token only in the release job, signing, attestation and verification, deploy and event scripts, `protection.json` and a catalog entry.
- A generator (`goldenpath new-service`) that validates the owner is a team, renders the template, audits the result against the contract before publishing, registers the catalog entry and takes the service to its first production deployment, with a stopwatch.
- The conformance audit (`goldenpath audit`): required checks, signing, short-lived credentials, pinned actions, no stored credential in any file, a valid catalog entry.
- An event collector and a PostgreSQL event store with the schema, the lesson's sample and the metric queries in SQL.
- The four DORA metrics per service and per week from events only, a trace from a lead time to its two events, and a deterministic simulation of a month for three teams.
- Layered code with import-linter rules, unit, template, integration and end-to-end tests, and the platform's own CI workflow.
