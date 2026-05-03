#!/usr/bin/env python3

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from pathlib import Path


OUTPUT_DIR = Path("output")
SVG_PATH = OUTPUT_DIR / "deployment_success_heatmap.svg"
CSV_PATH = OUTPUT_DIR / "deployment_success_data.csv"
DENSITY_CSV_PATH = OUTPUT_DIR / "working_day_commit_density.csv"
SUMMARY_PATH = OUTPUT_DIR / "simulation_summary.md"


@dataclass(frozen=True)
class SimulationConfig:
    commits_per_day: float = 100.0
    total_day_hours: float = 24.0
    workday_start_hour: float = 8.0
    workday_duration_hours: float = 10.0
    timeline_bins_per_hour: int = 12
    simulation_days: int = 180
    min_delay_hours: float = 1.0
    max_delay_hours: float = 12.0
    delay_steps: int = 45
    min_bug_probability: float = 1.0 / 400.0
    max_bug_probability: float = 1.0 / 40.0
    bug_probability_steps: int = 41
    random_seed: int = 7


@dataclass(frozen=True)
class TimelineProfile:
    bin_width_hours: float
    bin_starts: list[float]
    bin_centers: list[float]
    commit_rates_per_hour: list[float]
    expected_commits_per_bin: list[float]


@dataclass(frozen=True)
class CellResult:
    success_probability: float
    successful_deployments: int
    total_deployments: int


def linear_space(start: float, stop: float, steps: int) -> list[float]:
    if steps == 1:
        return [start]
    span = stop - start
    return [start + span * index / (steps - 1) for index in range(steps)]


def log_space(start: float, stop: float, steps: int) -> list[float]:
    if steps == 1:
        return [start]
    log_start = math.log10(start)
    log_stop = math.log10(stop)
    return [10 ** value for value in linear_space(log_start, log_stop, steps)]


def sample_poisson(mean: float, rng: random.Random) -> int:
    if mean <= 0:
        return 0
    threshold = math.exp(-mean)
    product = 1.0
    count = 0
    while product > threshold:
        product *= rng.random()
        count += 1
    return count - 1


def workday_shape(hour_of_day: float, config: SimulationConfig) -> float:
    work_start = config.workday_start_hour
    work_end = work_start + config.workday_duration_hours
    if hour_of_day < work_start or hour_of_day > work_end:
        return 0.0

    progress = (hour_of_day - work_start) / config.workday_duration_hours
    if progress <= 0.0 or progress >= 1.0:
        return 0.05

    morning_peak = 0.95 * math.exp(-((hour_of_day - (work_start + 2.2)) / 1.35) ** 2)
    afternoon_peak = 1.15 * math.exp(-((hour_of_day - (work_start + 6.5)) / 1.85) ** 2)
    lunch_dip = 0.20 * math.exp(-((hour_of_day - (work_start + 4.8)) / 0.65) ** 2)
    warmup_tail = 0.35 * math.sin(math.pi * progress) ** 1.35
    return max(0.0, morning_peak + afternoon_peak + warmup_tail - lunch_dip)


def build_timeline_profile(config: SimulationConfig) -> TimelineProfile:
    bin_width_hours = 1.0 / config.timeline_bins_per_hour
    total_bins = int(config.total_day_hours * config.timeline_bins_per_hour)
    bin_starts = [index * bin_width_hours for index in range(total_bins)]
    bin_centers = [value + 0.5 * bin_width_hours for value in bin_starts]
    raw_shape = [workday_shape(hour, config) for hour in bin_centers]
    raw_area = sum(raw_shape) * bin_width_hours
    scale = config.commits_per_day / raw_area
    commit_rates_per_hour = [value * scale for value in raw_shape]
    expected_commits_per_bin = [value * bin_width_hours for value in commit_rates_per_hour]
    return TimelineProfile(
        bin_width_hours=bin_width_hours,
        bin_starts=bin_starts,
        bin_centers=bin_centers,
        commit_rates_per_hour=commit_rates_per_hour,
        expected_commits_per_bin=expected_commits_per_bin,
    )


def generate_commit_times(profile: TimelineProfile, config: SimulationConfig, rng: random.Random) -> list[float]:
    commit_times: list[float] = []
    for day in range(config.simulation_days):
        day_offset = day * config.total_day_hours
        for bin_start, expected_commits in zip(profile.bin_starts, profile.expected_commits_per_bin):
            count = sample_poisson(expected_commits, rng)
            for _ in range(count):
                commit_times.append(day_offset + bin_start + rng.random() * profile.bin_width_hours)
    commit_times.sort()
    return commit_times


def simulate_retrying_pipeline(
    delay_hours: float,
    bug_probability: float,
    commit_times: list[float],
    cell_seed: int,
) -> CellResult:
    rng = random.Random(cell_seed)
    total_commits = len(commit_times)
    next_commit_index = 0
    pending_commits = 0
    pending_bugs = 0
    deployment_end_time = 0.0
    successful_deployments = 0
    total_deployments = 0

    while True:
        if pending_commits == 0:
            if next_commit_index >= total_commits:
                break
            deployment_end_time = commit_times[next_commit_index] + delay_hours
        else:
            deployment_end_time += delay_hours

        while next_commit_index < total_commits and commit_times[next_commit_index] <= deployment_end_time:
            pending_commits += 1
            if rng.random() < bug_probability:
                pending_bugs += 1
            next_commit_index += 1

        if pending_commits == 0:
            continue

        total_deployments += 1
        if pending_bugs > 0:
            pending_bugs -= 1
            pending_commits -= 1
        else:
            successful_deployments += 1
            pending_commits = 0

    success_probability = successful_deployments / total_deployments if total_deployments else 0.0
    return CellResult(
        success_probability=success_probability,
        successful_deployments=successful_deployments,
        total_deployments=total_deployments,
    )


def success_color(success_probability: float) -> str:
    clamped = max(0.0, min(1.0, success_probability))
    if clamped <= 0.8:
        ratio = clamped / 0.8
        red = round(220 + (242 - 220) * ratio)
        green = round(70 + (211 - 70) * ratio)
        blue = round(70 + (94 - 70) * ratio)
    else:
        ratio = (clamped - 0.8) / 0.2
        red = round(242 + (46 - 242) * ratio)
        green = round(211 + (160 - 211) * ratio)
        blue = round(94 + (67 - 94) * ratio)
    return f"#{red:02x}{green:02x}{blue:02x}"


def svg_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def smooth_svg_path(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    if len(points) == 1:
        return f"M {points[0][0]:.2f} {points[0][1]:.2f}"
    if len(points) == 2:
        return f"M {points[0][0]:.2f} {points[0][1]:.2f} L {points[1][0]:.2f} {points[1][1]:.2f}"

    commands = [f"M {points[0][0]:.2f} {points[0][1]:.2f}"]
    for index in range(1, len(points) - 1):
        control_x, control_y = points[index]
        next_x, next_y = points[index + 1]
        midpoint_x = (control_x + next_x) / 2
        midpoint_y = (control_y + next_y) / 2
        commands.append(f"Q {control_x:.2f} {control_y:.2f} {midpoint_x:.2f} {midpoint_y:.2f}")
    last_control_x, last_control_y = points[-2]
    last_x, last_y = points[-1]
    commands.append(f"Q {last_control_x:.2f} {last_control_y:.2f} {last_x:.2f} {last_y:.2f}")
    return " ".join(commands)


def render_heatmap_svg(
    delays: list[float],
    bug_probabilities: list[float],
    result_grid: list[list[CellResult]],
    config: SimulationConfig,
) -> str:
    width = 1180
    height = 820
    left = 150
    right = 190
    top = 110
    bottom = 78
    plot_width = width - left - right
    plot_height = height - top - bottom
    cell_width = plot_width / len(delays)
    cell_height = plot_height / len(bug_probabilities)
    legend_x = width - right + 55
    legend_y = top
    legend_height = plot_height
    bug_log_min = math.log10(config.min_bug_probability)
    bug_log_max = math.log10(config.max_bug_probability)

    lines: list[str] = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    lines.append('<rect width="100%" height="100%" fill="#ffffff"/>')
    lines.append('<style>')
    lines.append('text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #1f2937; }')
    lines.append('.title { font-size: 30px; font-weight: 700; }')
    lines.append('.subtitle { font-size: 15px; fill: #4b5563; }')
    lines.append('.axis { font-size: 14px; }')
    lines.append('.tick { font-size: 12px; fill: #6b7280; }')
    lines.append('.label { font-size: 13px; font-weight: 600; }')
    lines.append('.note { font-size: 12px; fill: #6b7280; }')
    lines.append('.contour { font-size: 11px; font-weight: 700; fill: #ffffff; }')
    lines.append('</style>')

    lines.append(f'<text x="{left}" y="48" class="title">Deployment success under retry backlog congestion</text>')
    lines.append(
        f'<text x="{left}" y="76" class="subtitle">'
        f'After each failed deployment, the next attempt inherits the unresolved batch plus all newly landed commits, so failures compound instead of resetting the queue.'
        f'</text>'
    )
    lines.append(f'<text x="{left}" y="{top - 18:.2f}" class="label">Success probability per deployment attempt</text>')

    for row_index, _bug_probability in enumerate(reversed(bug_probabilities)):
        data_index = len(bug_probabilities) - 1 - row_index
        y = top + row_index * cell_height
        for column_index, _delay_hours in enumerate(delays):
            x = left + column_index * cell_width
            success_probability = result_grid[data_index][column_index].success_probability
            lines.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{cell_width + 0.35:.2f}" height="{cell_height + 0.35:.2f}" fill="{success_color(success_probability)}"/>'
            )

    lines.append(f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="none" stroke="#111827" stroke-width="1.25"/>')

    for hour in range(math.ceil(config.min_delay_hours), math.floor(config.max_delay_hours) + 1):
        x = left + (hour - config.min_delay_hours) / (config.max_delay_hours - config.min_delay_hours) * plot_width
        lines.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_height}" stroke="#e5e7eb" stroke-width="1"/>')
        lines.append(f'<line x1="{x:.2f}" y1="{top + plot_height}" x2="{x:.2f}" y2="{top + plot_height + 7}" stroke="#111827" stroke-width="1"/>')
        lines.append(f'<text x="{x:.2f}" y="{top + plot_height + 26}" text-anchor="middle" class="tick">{hour}</text>')

    for bug_probability in [0.025, 0.01, 0.005, 0.0025]:
        ratio = (math.log10(bug_probability) - bug_log_min) / (bug_log_max - bug_log_min)
        y = top + plot_height - ratio * plot_height
        lines.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}" stroke="#e5e7eb" stroke-width="1"/>')
        lines.append(f'<line x1="{left - 7}" y1="{y:.2f}" x2="{left}" y2="{y:.2f}" stroke="#111827" stroke-width="1"/>')
        lines.append(f'<text x="{left - 14}" y="{y + 4:.2f}" text-anchor="end" class="tick">1 in {int(round(1 / bug_probability))}</text>')

    lines.append(f'<text x="{left + plot_width / 2:.2f}" y="{height - 34}" text-anchor="middle" class="axis">Duration of build + deploy cycle (hours)</text>')
    lines.append(f'<text x="32" y="{top + plot_height / 2:.2f}" transform="rotate(-90 32 {top + plot_height / 2:.2f})" text-anchor="middle" class="axis">Bug probability per commit (log scale)</text>')

    gradient_steps = 120
    for index in range(gradient_steps):
        blend = index / (gradient_steps - 1)
        y = legend_y + (1.0 - blend) * legend_height
        lines.append(f'<rect x="{legend_x}" y="{y:.2f}" width="24" height="{legend_height / gradient_steps + 0.8:.2f}" fill="{success_color(blend)}"/>')
    lines.append(f'<rect x="{legend_x}" y="{legend_y}" width="24" height="{legend_height}" fill="none" stroke="#111827" stroke-width="1"/>')
    lines.append(f'<text x="{legend_x + 12}" y="{legend_y - 16}" text-anchor="middle" class="label">Success</text>')
    for value in [1.0, 0.9, 0.5, 0.1, 0.0]:
        y = legend_y + (1.0 - value) * legend_height
        lines.append(f'<line x1="{legend_x + 24}" y1="{y:.2f}" x2="{legend_x + 30}" y2="{y:.2f}" stroke="#111827" stroke-width="1"/>')
        lines.append(f'<text x="{legend_x + 36}" y="{y + 4:.2f}" class="tick">{value:.0%}</text>')

    contour_targets = [0.9, 0.5, 0.1]
    simulated_values = [[cell.success_probability for cell in row] for row in result_grid]
    for target in contour_targets:
        points: list[tuple[float, float]] = []
        for column_index, delay_hours in enumerate(delays):
            previous_difference = None
            previous_probability = None
            match_probability = None
            for row_index, bug_probability in enumerate(bug_probabilities):
                difference = simulated_values[row_index][column_index] - target
                if difference == 0:
                    match_probability = bug_probability
                    break
                if previous_difference is not None and difference * previous_difference < 0:
                    fraction = previous_difference / (previous_difference - difference)
                    match_probability = previous_probability + fraction * (bug_probability - previous_probability)
                    break
                previous_difference = difference
                previous_probability = bug_probability

            if match_probability is None:
                continue

            x = left + (delay_hours - config.min_delay_hours) / (config.max_delay_hours - config.min_delay_hours) * plot_width
            y = top + plot_height - (math.log10(match_probability) - bug_log_min) / (bug_log_max - bug_log_min) * plot_height
            points.append((x, y))

        if len(points) < 2:
            continue

        lines.append(f'<path d="{smooth_svg_path(points)}" fill="none" stroke="#ffffff" stroke-width="2" opacity="0.95" stroke-linecap="round" stroke-linejoin="round"/>')
        label_x, label_y = points[min(len(points) - 1, max(1, len(points) // 2))]
        lines.append(f'<text x="{label_x + 8:.2f}" y="{label_y - 6:.2f}" class="contour">{int(target * 100)}%</text>')

    island_text_x = left + 28
    island_text_y = top + plot_height - 56
    lines.append(f'<text x="{island_text_x:.2f}" y="{island_text_y:.2f}" text-anchor="start" fill="#111827" font-size="15" font-weight="700">Island of Success</text>')

    plateau_text_x = left + plot_width - 330
    plateau_text_y = top + 168
    lines.append(f'<text x="{plateau_text_x:.2f}" y="{plateau_text_y:.2f}" text-anchor="start" fill="#111827" font-size="22" font-weight="800" opacity="0.92">Plateau of Misery</text>')

    lines.append('</svg>')
    return "\n".join(lines)


def write_outputs(config: SimulationConfig) -> None:
    commit_rng = random.Random(config.random_seed)
    profile = build_timeline_profile(config)
    commit_times = generate_commit_times(profile, config, commit_rng)
    delays = linear_space(config.min_delay_hours, config.max_delay_hours, config.delay_steps)
    bug_probabilities = log_space(config.min_bug_probability, config.max_bug_probability, config.bug_probability_steps)

    result_grid: list[list[CellResult]] = []
    for row_index, bug_probability in enumerate(bug_probabilities):
        result_row: list[CellResult] = []
        for column_index, delay_hours in enumerate(delays):
            cell_seed = config.random_seed * 100_000 + row_index * 1_000 + column_index
            result_row.append(
                simulate_retrying_pipeline(
                    delay_hours=delay_hours,
                    bug_probability=bug_probability,
                    commit_times=commit_times,
                    cell_seed=cell_seed,
                )
            )
        result_grid.append(result_row)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with CSV_PATH.open("w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "delay_hours",
                "bug_probability",
                "bug_rate_label",
                "success_probability",
                "successful_deployments",
                "total_deployments",
                "simulation_days",
            ]
        )
        for row_index, bug_probability in enumerate(bug_probabilities):
            for column_index, delay_hours in enumerate(delays):
                result = result_grid[row_index][column_index]
                writer.writerow(
                    [
                        f"{delay_hours:.4f}",
                        f"{bug_probability:.6f}",
                        f"1 in {int(round(1 / bug_probability))}",
                        f"{result.success_probability:.6f}",
                        result.successful_deployments,
                        result.total_deployments,
                        config.simulation_days,
                    ]
                )

    with DENSITY_CSV_PATH.open("w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["hour_of_day", "commits_per_hour"])
        for hour, commits_per_hour in zip(profile.bin_centers, profile.commit_rates_per_hour):
            writer.writerow([f"{hour:.4f}", f"{commits_per_hour:.6f}"])

    svg = render_heatmap_svg(
        delays=delays,
        bug_probabilities=bug_probabilities,
        result_grid=result_grid,
        config=config,
    )
    SVG_PATH.write_text(svg)

    summary_lines = [
        "# Simulation summary",
        "",
        "## Model",
        "",
        "- Commit arrivals follow a non-homogeneous Poisson process over a 24-hour day, with most commits clustered into a realistic 10-hour working window.",
        "- A deployment attempt takes `delay_hours` from commit until end-to-end test completion.",
        "- When a deployment fails, the bug is reverted, but the remaining unresolved batch does **not** reset; it rolls forward into the next attempt together with any new commits that arrived during the wait.",
        "- That means a single early bad commit can drag a growing backlog across multiple retries, which directly models congestion collapse.",
        "",
        "## What changed",
        "",
        "- The heatmap uses a log-scaled bug axis from `1 in 40` down to `1 in 400`.",
        "- Success probability now comes from a retrying deployment queue simulation rather than a one-shot batch approximation.",
    ]
    SUMMARY_PATH.write_text("\n".join(summary_lines) + "\n")


def main() -> None:
    config = SimulationConfig()
    write_outputs(config)
    print(f"Wrote {CSV_PATH}")
    print(f"Wrote {DENSITY_CSV_PATH}")
    print(f"Wrote {SVG_PATH}")
    print(f"Wrote {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
