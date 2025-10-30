"""
Generate throughput, speedup, and parallel-efficiency plots for each benchmark
variant using the CSV output produced by tools/run-benchmarks.py.

Usage:
  python scripts/generate_plots.py \
    --results scaling-results/20251030_004543/scaling_results.csv \
    --output plots/

The script expects a CSV with the schema documented in README.md:
  variant,scaling_type,threads,executed_threads,data_size,total_size,iterations,avg_time_millis

For each non-baseline variant it produces two PNG files per scaling mode:
  <variant>_<scaling>_throughput.png
  <variant>_<scaling>_speedup_efficiency.png
The baseline `jvm-local` variant is excluded from per-variant plots.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

import matplotlib.pyplot as plt
import numpy as np


@dataclass
class ScalingEntry:
    variant: str
    scaling_type: str
    threads: int
    executed_threads: int
    data_size: float
    total_size: float
    iterations: int
    avg_time_ms: float

    @property
    def duration_seconds(self) -> float:
        return self.avg_time_ms / 1_000.0

    @property
    def work_amount(self) -> float:
        if self.scaling_type == "strong":
            return self.total_size
        return self.data_size * self.executed_threads


def _parse_csv(path: Path) -> Dict[str, Dict[str, List[ScalingEntry]]]:
    result: Dict[str, Dict[str, List[ScalingEntry]]] = {}
    with path.open() as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            entry = ScalingEntry(
                variant=row["variant"],
                scaling_type=row["scaling_type"],
                threads=int(row["threads"]),
                executed_threads=int(row["executed_threads"]),
                data_size=float(row["data_size"]) if row["data_size"] else 0.0,
                total_size=float(row["total_size"]) if row["total_size"] else 0.0,
                iterations=int(row["iterations"]),
                avg_time_ms=float(row["avg_time_millis"]),
            )
            by_variant = result.setdefault(entry.variant, {})
            entries = by_variant.setdefault(entry.scaling_type, [])
            entries.append(entry)

    # Ensure consistent ordering by thread count
    for variant_data in result.values():
        for entries in variant_data.values():
            entries.sort(key=lambda e: e.executed_threads)
    return result


def _compute_metrics(entries: Iterable[ScalingEntry]) -> Dict[str, np.ndarray]:
    entries = list(entries)
    threads = np.array([item.executed_threads for item in entries], dtype=int)
    work = np.array([item.work_amount for item in entries], dtype=float)
    duration = np.array([item.duration_seconds for item in entries], dtype=float)

    throughput = work / duration
    baseline = throughput[threads.argmin()]
    speedup = throughput / baseline
    efficiency = speedup / threads

    return {
        "threads": threads,
        "work": work,
        "duration": duration,
        "throughput": throughput,
        "speedup": speedup,
        "efficiency": efficiency,
    }


def _plot_throughput(metrics: Dict[str, np.ndarray], title: str, outfile: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(metrics["threads"], metrics["throughput"] / 1_000.0, marker="o")
    ax.set_xlabel("Clients (threads)")
    ax.set_ylabel("Throughput [thousand ops/s]")
    ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.5)
    _set_thread_ticks(ax, metrics["threads"])
    fig.tight_layout()
    fig.savefig(outfile, dpi=200)
    plt.close(fig)


def _plot_speedup_efficiency(metrics: Dict[str, np.ndarray], title_prefix: str, outfile: Path) -> None:
    fig, axes = plt.subplots(nrows=1, ncols=2, figsize=(10, 4))

    axes[0].plot(metrics["threads"], metrics["speedup"], marker="o")
    axes[0].set_xlabel("Clients (threads)")
    axes[0].set_ylabel("Throughput speedup")
    axes[0].set_title(f"{title_prefix} Speedup")
    axes[0].grid(True, linestyle="--", alpha=0.5)
    _set_thread_ticks(axes[0], metrics["threads"])

    axes[1].plot(metrics["threads"], metrics["efficiency"], marker="o")
    axes[1].set_xlabel("Clients (threads)")
    axes[1].set_ylabel("Parallel efficiency")
    axes[1].set_title(f"{title_prefix} Efficiency")
    axes[1].grid(True, linestyle="--", alpha=0.5)
    _set_thread_ticks(axes[1], metrics["threads"])

    fig.tight_layout()
    fig.savefig(outfile, dpi=200)
    plt.close(fig)


def _set_thread_ticks(ax, threads: np.ndarray) -> None:
    desired = np.array([1, 2, 4, 8, 16, 32])
    ticks = desired[desired <= threads.max()]
    if ticks.size:
        ax.set_xticks(ticks.tolist())


def _generate_variant_plots(
    variant: str,
    scaling_type: str,
    entries: List[ScalingEntry],
    output_dir: Path,
) -> None:
    metrics = _compute_metrics(entries)

    def outfile(name: str) -> Path:
        return output_dir / f"{variant}_{scaling_type}_{name}.png"

    title_prefix = f"{variant.replace('-', ' ').title()} – {scaling_type.capitalize()} Scaling"
    _plot_throughput(metrics, f"{title_prefix} Throughput", outfile("throughput"))
    _plot_speedup_efficiency(metrics, title_prefix, outfile("speedup_efficiency"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate scaling plots per variant.")
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("scaling-results") / "latest" / "scaling_results.csv",
        help="Path to scaling_results.csv (default: scaling-results/latest/scaling_results.csv).",
    )
    parser.add_argument(
        "--startup",
        type=Path,
        default=Path("scaling-results") / "latest" / "benchmark_results.json",
        help="Path to benchmark_results.json (default: scaling-results/latest/benchmark_results.json).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("plots"),
        help="Directory where plots will be written (default: plots/).",
    )
    args = parser.parse_args()

    data = _parse_csv(args.results)
    args.output.mkdir(parents=True, exist_ok=True)

    for variant, groups in data.items():
        if variant == "jvm-local":
            continue
        for scaling_type, entries in groups.items():
            if not entries:
                continue
            _generate_variant_plots(variant, scaling_type, entries, args.output)

    if args.startup.exists():
        _plot_startup_times(args.startup, args.output / "startup_times.png")

    print(f"Wrote plots to {args.output.resolve()}")


def _plot_startup_times(json_path: Path, outfile: Path) -> None:
    with json_path.open() as handle:
        payload = json.load(handle)

    variants = payload.get("variants", [])
    names = [item.get("name", "") for item in variants]
    times = [float(item.get("startupTimeSeconds", 0.0)) for item in variants]

    order = np.argsort(times)
    ordered_names = [names[idx] for idx in order]
    ordered_times = [times[idx] for idx in order]

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(ordered_names, ordered_times, color="#4c78a8")
    ax.set_ylabel("Startup time [seconds]")
    ax.set_title("Server Startup Times")
    ax.grid(True, axis="y", linestyle="--", alpha=0.5)

    for bar, value in zip(bars, ordered_times):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.2f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    fig.tight_layout()
    fig.savefig(outfile, dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    main()
