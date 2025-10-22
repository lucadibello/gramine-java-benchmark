#!/usr/bin/env python3

"""
Generate professional scaling benchmark plots from CSV data.
Creates visualizations for strong/weak scaling, throughput, latency, speedup, and efficiency.
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# Set professional style
plt.style.use("seaborn-v0_8-darkgrid")
plt.rcParams["figure.dpi"] = 300
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.size"] = 10
plt.rcParams["axes.labelsize"] = 11
plt.rcParams["axes.titlesize"] = 12
plt.rcParams["xtick.labelsize"] = 9
plt.rcParams["ytick.labelsize"] = 9
plt.rcParams["legend.fontsize"] = 9

# Color scheme for variants
COLORS = {
    "jvm-local": "#2E86AB",  # Blue - baseline
    "jvm-gramine": "#A23B72",  # Purple - JVM in SGX
    "native-dynamic": "#F18F01",  # Orange - native dynamic
    "native-static": "#C73E1D",  # Red - native static
}

VARIANT_LABELS = {
    "jvm-local": "JVM Local (Baseline)",
    "jvm-gramine": "JVM in Gramine-SGX",
    "native-dynamic": "Native Dynamic (glibc)",
    "native-static": "Native Static (musl)",
}


def load_data(csv_path: Path) -> pd.DataFrame:
    """Load benchmark data from CSV."""
    df = pd.read_csv(csv_path)
    return df


def plot_strong_scaling_throughput(df: pd.DataFrame, output_dir: Path):
    """Plot strong scaling throughput."""
    fig, ax = plt.subplots(figsize=(10, 6))

    variants = df["variant"].unique()

    for variant in sorted(variants):
        variant_data = df[df["variant"] == variant].sort_values("num_clients")

        # Plot with error bars
        ax.errorbar(
            variant_data["num_clients"],
            variant_data["throughput_mean"],
            yerr=variant_data["throughput_stdev"],
            marker="o",
            label=VARIANT_LABELS.get(variant, variant),
            color=COLORS.get(variant, "#333333"),
            linewidth=2,
            markersize=8,
            capsize=5,
            capthick=2,
        )

    ax.set_xlabel("Number of Clients")
    ax.set_ylabel("Throughput (messages/second)")
    ax.set_title(
        "Strong Scaling: Throughput vs Number of Clients\n(Fixed total workload)"
    )
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xscale("log", base=2)

    # Set x-ticks to powers of 2
    ax.set_xticks([1, 2, 4, 8, 16])
    ax.set_xticklabels([1, 2, 4, 8, 16])

    plt.tight_layout()
    plt.savefig(
        output_dir / "strong_scaling_throughput.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print(f"Generated: {output_dir / 'strong_scaling_throughput.png'}")


def plot_strong_scaling_latency(df: pd.DataFrame, output_dir: Path):
    """Plot strong scaling latency."""
    # Filter out missing latency data
    df_latency = df[df["latency_mean"].notna()].copy()

    if len(df_latency) == 0:
        print("Warning: No latency data for strong scaling, skipping plot")
        return

    fig, ax = plt.subplots(figsize=(10, 6))

    variants = df_latency["variant"].unique()

    for variant in sorted(variants):
        variant_data = df_latency[df_latency["variant"] == variant].sort_values(
            "num_clients"
        )

        if len(variant_data) == 0:
            continue

        # Plot with error bars
        ax.errorbar(
            variant_data["num_clients"],
            variant_data["latency_mean"],
            yerr=variant_data["latency_stdev"],
            marker="s",
            label=VARIANT_LABELS.get(variant, variant),
            color=COLORS.get(variant, "#333333"),
            linewidth=2,
            markersize=8,
            capsize=5,
            capthick=2,
        )

    ax.set_xlabel("Number of Clients")
    ax.set_ylabel("Average Latency (ms)")
    ax.set_title("Strong Scaling: Latency vs Number of Clients\n(Fixed total workload)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xscale("log", base=2)

    # Set x-ticks to powers of 2
    ax.set_xticks([1, 2, 4, 8, 16])
    ax.set_xticklabels([1, 2, 4, 8, 16])

    plt.tight_layout()
    plt.savefig(output_dir / "strong_scaling_latency.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Generated: {output_dir / 'strong_scaling_latency.png'}")


def plot_strong_scaling_speedup(df: pd.DataFrame, output_dir: Path):
    """Plot strong scaling speedup and efficiency."""
    df_speedup = df[df["speedup_throughput"].notna()].copy()

    if len(df_speedup) == 0:
        print("Warning: No speedup data for strong scaling, skipping plot")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    variants = df_speedup["variant"].unique()

    # Speedup plot
    for variant in sorted(variants):
        if variant == "jvm-local":
            continue  # Skip baseline in speedup plot

        variant_data = df_speedup[df_speedup["variant"] == variant].sort_values(
            "num_clients"
        )

        if len(variant_data) == 0:
            continue

        ax1.plot(
            variant_data["num_clients"],
            variant_data["speedup_throughput"],
            marker="o",
            label=VARIANT_LABELS.get(variant, variant),
            color=COLORS.get(variant, "#333333"),
            linewidth=2,
            markersize=8,
        )

    # Ideal speedup line
    ax1.axhline(
        y=1.0,
        color="gray",
        linestyle="--",
        alpha=0.5,
        linewidth=2,
        label="Baseline (1.0x)",
    )

    ax1.set_xlabel("Number of Clients")
    ax1.set_ylabel("Speedup (relative to baseline)")
    ax1.set_title("Strong Scaling: Throughput Speedup")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_xscale("log", base=2)
    ax1.set_xticks([1, 2, 4, 8, 16])
    ax1.set_xticklabels([1, 2, 4, 8, 16])

    # Efficiency plot
    for variant in sorted(variants):
        if variant == "jvm-local":
            continue  # Skip baseline

        variant_data = df_speedup[df_speedup["variant"] == variant].sort_values(
            "num_clients"
        )

        if len(variant_data) == 0:
            continue

        ax2.plot(
            variant_data["num_clients"],
            variant_data["efficiency_throughput"],
            marker="s",
            label=VARIANT_LABELS.get(variant, variant),
            color=COLORS.get(variant, "#333333"),
            linewidth=2,
            markersize=8,
        )

    # Perfect efficiency line
    ax2.axhline(
        y=1.0,
        color="gray",
        linestyle="--",
        alpha=0.5,
        linewidth=2,
        label="Perfect Efficiency (1.0)",
    )

    ax2.set_xlabel("Number of Clients")
    ax2.set_ylabel("Parallel Efficiency")
    ax2.set_title("Strong Scaling: Parallel Efficiency")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.set_xscale("log", base=2)
    ax2.set_xticks([1, 2, 4, 8, 16])
    ax2.set_xticklabels([1, 2, 4, 8, 16])

    plt.tight_layout()
    plt.savefig(output_dir / "strong_scaling_speedup.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Generated: {output_dir / 'strong_scaling_speedup.png'}")


def plot_weak_scaling_throughput(df: pd.DataFrame, output_dir: Path):
    """Plot weak scaling throughput."""
    fig, ax = plt.subplots(figsize=(10, 6))

    variants = df["variant"].unique()

    for variant in sorted(variants):
        variant_data = df[df["variant"] == variant].sort_values("num_clients")

        # Plot with error bars
        ax.errorbar(
            variant_data["num_clients"],
            variant_data["throughput_mean"],
            yerr=variant_data["throughput_stdev"],
            marker="o",
            label=VARIANT_LABELS.get(variant, variant),
            color=COLORS.get(variant, "#333333"),
            linewidth=2,
            markersize=8,
            capsize=5,
            capthick=2,
        )

    ax.set_xlabel("Number of Clients")
    ax.set_ylabel("Throughput (messages/second)")
    ax.set_title(
        "Weak Scaling: Throughput vs Number of Clients\n(Fixed per-client workload)"
    )
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xscale("log", base=2)

    # Set x-ticks to powers of 2
    ax.set_xticks([1, 2, 4, 8, 16])
    ax.set_xticklabels([1, 2, 4, 8, 16])

    plt.tight_layout()
    plt.savefig(
        output_dir / "weak_scaling_throughput.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print(f"Generated: {output_dir / 'weak_scaling_throughput.png'}")


def plot_weak_scaling_latency(df: pd.DataFrame, output_dir: Path):
    """Plot weak scaling latency."""
    df_latency = df[df["latency_mean"].notna()].copy()

    if len(df_latency) == 0:
        print("Warning: No latency data for weak scaling, skipping plot")
        return

    fig, ax = plt.subplots(figsize=(10, 6))

    variants = df_latency["variant"].unique()

    for variant in sorted(variants):
        variant_data = df_latency[df_latency["variant"] == variant].sort_values(
            "num_clients"
        )

        if len(variant_data) == 0:
            continue

        # Plot with error bars
        ax.errorbar(
            variant_data["num_clients"],
            variant_data["latency_mean"],
            yerr=variant_data["latency_stdev"],
            marker="s",
            label=VARIANT_LABELS.get(variant, variant),
            color=COLORS.get(variant, "#333333"),
            linewidth=2,
            markersize=8,
            capsize=5,
            capthick=2,
        )

    ax.set_xlabel("Number of Clients")
    ax.set_ylabel("Average Latency (ms)")
    ax.set_title(
        "Weak Scaling: Latency vs Number of Clients\n(Fixed per-client workload)"
    )
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xscale("log", base=2)

    # Set x-ticks to powers of 2
    ax.set_xticks([1, 2, 4, 8, 16])
    ax.set_xticklabels([1, 2, 4, 8, 16])

    plt.tight_layout()
    plt.savefig(output_dir / "weak_scaling_latency.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Generated: {output_dir / 'weak_scaling_latency.png'}")


def plot_weak_scaling_speedup(df: pd.DataFrame, output_dir: Path):
    """Plot weak scaling speedup and efficiency."""
    df_speedup = df[df["speedup_throughput"].notna()].copy()

    if len(df_speedup) == 0:
        print("Warning: No speedup data for weak scaling, skipping plot")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    variants = df_speedup["variant"].unique()

    # Speedup plot
    for variant in sorted(variants):
        if variant == "jvm-local":
            continue  # Skip baseline

        variant_data = df_speedup[df_speedup["variant"] == variant].sort_values(
            "num_clients"
        )

        if len(variant_data) == 0:
            continue

        ax1.plot(
            variant_data["num_clients"],
            variant_data["speedup_throughput"],
            marker="o",
            label=VARIANT_LABELS.get(variant, variant),
            color=COLORS.get(variant, "#333333"),
            linewidth=2,
            markersize=8,
        )

    # Ideal speedup line
    ax1.axhline(
        y=1.0,
        color="gray",
        linestyle="--",
        alpha=0.5,
        linewidth=2,
        label="Baseline (1.0x)",
    )

    ax1.set_xlabel("Number of Clients")
    ax1.set_ylabel("Speedup (relative to baseline)")
    ax1.set_title("Weak Scaling: Throughput Speedup")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_xscale("log", base=2)
    ax1.set_xticks([1, 2, 4, 8, 16])
    ax1.set_xticklabels([1, 2, 4, 8, 16])

    # Efficiency plot
    for variant in sorted(variants):
        if variant == "jvm-local":
            continue  # Skip baseline

        variant_data = df_speedup[df_speedup["variant"] == variant].sort_values(
            "num_clients"
        )

        if len(variant_data) == 0:
            continue

        ax2.plot(
            variant_data["num_clients"],
            variant_data["efficiency_throughput"],
            marker="s",
            label=VARIANT_LABELS.get(variant, variant),
            color=COLORS.get(variant, "#333333"),
            linewidth=2,
            markersize=8,
        )

    # Perfect efficiency line
    ax2.axhline(
        y=1.0,
        color="gray",
        linestyle="--",
        alpha=0.5,
        linewidth=2,
        label="Perfect Efficiency (1.0)",
    )

    ax2.set_xlabel("Number of Clients")
    ax2.set_ylabel("Parallel Efficiency")
    ax2.set_title("Weak Scaling: Parallel Efficiency")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.set_xscale("log", base=2)
    ax2.set_xticks([1, 2, 4, 8, 16])
    ax2.set_xticklabels([1, 2, 4, 8, 16])

    plt.tight_layout()
    plt.savefig(output_dir / "weak_scaling_speedup.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Generated: {output_dir / 'weak_scaling_speedup.png'}")


def plot_startup_times(df: pd.DataFrame, output_dir: Path):
    """Plot startup time comparison."""
    fig, ax = plt.subplots(figsize=(10, 6))

    variants = df["variant"].tolist()
    times = df["startup_time_seconds"].tolist()

    # Sort by startup time
    sorted_data = sorted(zip(variants, times), key=lambda x: x[1])
    variants_sorted, times_sorted = zip(*sorted_data)

    colors = [COLORS.get(v, "#333333") for v in variants_sorted]
    labels = [VARIANT_LABELS.get(v, v) for v in variants_sorted]

    bars = ax.barh(labels, times_sorted, color=colors, alpha=0.8)

    ax.set_xlabel("Startup Time (seconds)")
    ax.set_ylabel("Server Variant")
    ax.set_title("Server Startup Time Comparison")
    ax.grid(True, alpha=0.3, axis="x")

    # Add value labels
    for bar, val in zip(bars, times_sorted):
        ax.text(
            val + max(times_sorted) * 0.02,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.2f}s",
            va="center",
            fontsize=9,
        )

    plt.tight_layout()
    plt.savefig(output_dir / "startup_times.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Generated: {output_dir / 'startup_times.png'}")


def plot_overhead_comparison(strong_df: pd.DataFrame, output_dir: Path):
    """Plot SGX overhead comparison across variants."""
    # Calculate average speedup for each variant
    variants = []
    avg_speedups = []

    for variant in strong_df["variant"].unique():
        if variant == "jvm-local":
            continue

        variant_data = strong_df[
            (strong_df["variant"] == variant)
            & (strong_df["speedup_throughput"].notna())
        ]

        if len(variant_data) > 0:
            variants.append(variant)
            avg_speedups.append(variant_data["speedup_throughput"].mean())

    if not variants:
        print("Warning: No speedup data for overhead comparison")
        return

    fig, ax = plt.subplots(figsize=(10, 6))

    # Calculate overhead percentage: (1 - speedup) * 100
    overheads = [(1 - s) * 100 for s in avg_speedups]

    colors = [COLORS.get(v, "#333333") for v in variants]
    labels = [VARIANT_LABELS.get(v, v) for v in variants]

    bars = ax.bar(labels, overheads, color=colors, alpha=0.8)

    ax.set_ylabel("Average Performance Overhead (%)")
    ax.set_title("Average SGX Performance Overhead\n(Lower is better)")
    ax.grid(True, alpha=0.3, axis="y")
    ax.axhline(y=0, color="gray", linestyle="-", linewidth=1)

    # Add value labels
    for bar, val in zip(bars, overheads):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + max(overheads) * 0.02,
            f"{val:.1f}%",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    # Rotate x labels if needed
    plt.xticks(rotation=15, ha="right")

    plt.tight_layout()
    plt.savefig(
        output_dir / "sgx_overhead_comparison.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print(f"Generated: {output_dir / 'sgx_overhead_comparison.png'}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate scaling benchmark plots from CSV data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s scaling-results/20251022_220057
  %(prog)s /path/to/results --output plots/

The script expects to find in the directory:
  - strong_scaling.csv
  - weak_scaling.csv
  - startup_times.csv
        """,
    )
    parser.add_argument(
        "results_dir", type=Path, help="Directory containing CSV result files"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for plots (default: same as results_dir)",
    )

    args = parser.parse_args()

    # Validate input directory
    if not args.results_dir.exists():
        print(f"Error: Results directory not found: {args.results_dir}")
        sys.exit(1)

    # Set output directory
    output_dir = args.output_dir if args.output_dir else args.results_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading data from: {args.results_dir}")
    print(f"Generating plots in: {output_dir}\n")

    # Load data files
    strong_csv = args.results_dir / "strong_scaling.csv"
    weak_csv = args.results_dir / "weak_scaling.csv"
    startup_csv = args.results_dir / "startup_times.csv"

    # Generate strong scaling plots
    if strong_csv.exists():
        print("Processing strong scaling data...")
        strong_df = load_data(strong_csv)
        plot_strong_scaling_throughput(strong_df, output_dir)
        plot_strong_scaling_latency(strong_df, output_dir)
        plot_strong_scaling_speedup(strong_df, output_dir)
        plot_overhead_comparison(strong_df, output_dir)
    else:
        print(f"Warning: {strong_csv} not found, skipping strong scaling plots")

    # Generate weak scaling plots
    if weak_csv.exists():
        print("\nProcessing weak scaling data...")
        weak_df = load_data(weak_csv)
        plot_weak_scaling_throughput(weak_df, output_dir)
        plot_weak_scaling_latency(weak_df, output_dir)
        plot_weak_scaling_speedup(weak_df, output_dir)
    else:
        print(f"Warning: {weak_csv} not found, skipping weak scaling plots")

    # Generate startup time plot
    if startup_csv.exists():
        print("\nProcessing startup time data...")
        startup_df = load_data(startup_csv)
        plot_startup_times(startup_df, output_dir)
    else:
        print(f"Warning: {startup_csv} not found, skipping startup time plot")

    print("\n" + "=" * 70)
    print("All plots generated successfully!")
    print(f"Output directory: {output_dir}")
    print("=" * 70)


if __name__ == "__main__":
    main()
