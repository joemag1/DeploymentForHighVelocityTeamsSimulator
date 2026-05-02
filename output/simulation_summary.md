# Simulation summary

## Model

- Commit arrivals follow a non-homogeneous Poisson process over a 24-hour day, with most commits clustered into a realistic 10-hour working window.
- A deployment attempt takes `delay_hours` from commit until end-to-end test completion.
- When a deployment fails, the bug is reverted, but the remaining unresolved batch does **not** reset; it rolls forward into the next attempt together with any new commits that arrived during the wait.
- That means a single early bad commit can drag a growing backlog across multiple retries, which directly models congestion collapse.

## What changed

- The heatmap uses a log-scaled bug axis from `1 in 40` down to `1 in 400`.
- Success probability now comes from a retrying deployment queue simulation rather than a one-shot batch approximation.
