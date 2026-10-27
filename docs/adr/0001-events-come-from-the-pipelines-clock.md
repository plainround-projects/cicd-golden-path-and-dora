# 1. Every event comes from the pipeline and carries the pipeline's clock

Status: accepted, 2026-10-27

## Context

The lesson's common mistakes include taking the commit time from Git history and the deploy time from the pipeline: two clocks, two definitions, and a lead time that cannot be traced back to events.

## Decision

Commits, deployments, failures and recoveries are all events posted by the pipeline (or by whatever decides a deployment failed) to one collector, with a UTC timestamp from the sender's clock at the moment it happens. A `commit` event is posted when the commit enters the pipeline (on push); Git history is never read to compute a metric. Lead time is the difference of two events of the same store, so any value prints the two events behind it (`goldenpath trace`).

## Alternatives considered

- **Read the commit time from `git log`:** the author can set it, and it is a different clock from the deployment's.
- **Compute from the CI system's API:** ties the metrics to one vendor and to what its retention keeps.

## Consequences

- A developer cannot shorten a lead time by editing a field; the guard against "start the clock later" is that the clock starts at an event nobody sets by hand.
- A commit that was never reported as an event has no lead time (it is not guessed).
