# 6. The month of simulated work is a model with stated assumptions

Status: accepted, 2026-10-27

## Context

Step 5 and 6 need a month of events that make the metrics move. Real data takes a month of real work.

## Decision

`goldenpath simulate --seed N` generates four weeks of events for three teams, deterministic for a seed, through the same `record` use case the pipeline uses. The profiles say how each team works: `orders` deploys after every merge, `billing` batches a week of commits into one Friday deployment, `search` deploys on Tuesdays and Thursdays. The model also says that a deployment fails with probability `fail_base + fail_per_commit * size` and takes `recovery_base + recovery_per_commit * size` minutes (with noise) to recover, capped at 0.9. Those numbers are the assumptions, written in `goldenpath/domain/simulation.py`.

## Alternatives considered

- **Hand-written events:** no way to see how the metrics behave on volume.
- **A model with no dependence on batch size:** the metrics would have nothing to show in step 6.

## Consequences

- What the comparison shows is what the metrics make visible when teams batch differently, given the assumption that bigger changes fail more and take longer to fix; it is not evidence that this holds for a real team, and the README says so.
- A team that deploys once a week may see no failure in a month and then has no recovery time to show: `n/a`, a small-sample effect the tables make visible.
