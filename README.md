# Deployment congestion collapse simulation

This repo contains a Monte Carlo simulator for the idea that high commit velocity plus slow build/deploy cycles can create a form of deployment congestion collapse.

Once a bad batch enters the pipeline, the next deployment attempt is not “clean” again — it inherits the unresolved backlog plus all newly landed commits. That feedback loop is the core behavior this model is trying to visualize.

## Summary

- Built a retry-aware deployment simulator in `simulate_deployment_congestion.py`.
- Modeled engineers committing at an average rate of **100 commits/day**.
- Concentrated most commits into a realistic **10-hour workday** instead of spreading them uniformly across 24 hours.
- Generated a heatmap showing how deployment success degrades as the build+deploy cycle length grows and the bug rate rises.

## Current assumptions

- **Commit arrivals:** non-homogeneous Poisson process.
- **Workday shape:** morning ramp, lunch dip, afternoon peak.
- **Bug rate axis:** `1 in 400` through `1 in 40` on a log scale.
- **X axis:** duration of the build + deploy cycle, from `1` to `12` hours.
- **Failure handling:** when a deployment fails, one bad commit is reverted, but the unresolved batch remains queued and the next deployment also carries newly landed commits.
- **Outcome metric:** success probability per deployment attempt.

## Results snapshot

- At **1 in 400**, success is about **97.6%** at `1h`, **88.5%** at `6h`, and **78.1%** at `12h`.
- At **1 in 100**, success is about **89.1%** at `1h`, **60.8%** at `6h`, and **42.0%** at `12h`.
- At **1 in 40**, success is about **71.5%** at `1h`, **25.7%** at `6h`, and **0.7%** at `12h`.

Those last numbers are the key qualitative result: once bug rates are only moderately elevated and the cycle time gets long enough, the retry backlog drives the system into a “Plateau of Misery” where successful deployments become rare.

## Visualization

![Deployment success heatmap](output/deployment_success_heatmap.png)

## Generated artifacts

- `output/deployment_success_heatmap.png` — presentation-friendly preview image.
- `output/deployment_success_heatmap.svg` — vector version of the same heatmap.
- `output/deployment_success_data.csv` — raw simulated results for every heatmap cell.
- `output/working_day_commit_density.csv` — the workday traffic profile used by the simulator.
- `output/simulation_summary.md` — short model summary.

## Run it

```bash
python3 simulate_deployment_congestion.py
```

The core simulator uses only the Python standard library. The committed PNG preview is a generated artifact included for convenience in the README.
