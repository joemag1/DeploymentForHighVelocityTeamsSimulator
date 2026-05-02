# Deployment congestion collapse simulation

This workspace contains a Monte Carlo simulation for the hypothesis that slower build-and-test cycles make successful deployments less likely when engineers are committing quickly.

## What it models

- Engineers produce commits as a **time-varying Poisson process** with an average of **100 commits per day**.
- Most commits are clustered into a realistic **10-hour working window** with a morning ramp, lunch dip, and afternoon peak.
- Each commit has an independent bug probability `p`.
- A deployment attempt takes `delay_hours` before the batch is fully validated in the beta/test environment.
- If a deployment fails, one bad commit is reverted but the rest of the unresolved batch rolls forward into the next attempt together with any new commits that arrive meanwhile.

## Outputs

- `output/deployment_success_heatmap.svg` — heatmap visualization using the retry-backlog congestion model.
- `output/deployment_success_data.csv` — simulated deployment outcomes for every heatmap cell.
- `output/working_day_commit_density.csv` — the commit-density curve used for the workday timeline.
- `output/simulation_summary.md` — model assumptions and the retry/backlog interpretation.

## Run it

```bash
python3 simulate_deployment_congestion.py
```

The script uses only the Python standard library, so it should run on a stock macOS or Linux machine without extra packages.
