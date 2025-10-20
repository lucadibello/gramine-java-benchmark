#!/usr/bin/env python3

"""
Generate professional benchmark plots from CSV data.
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


def load_data(csv_path: Path) -> pd.DataFrame:
    """Load benchmark data from CSV."""
    df = pd.read_csv(csv_path)
    return df


def plot_throughput_comparison(df: pd.DataFrame, output_dir: Path):
    """Generate throughput comparison bar chart."""
    fig, ax = plt.subplots(figsize=(10, 6))

    scenarios = df["scenario"].str.replace("_", " ").str.title()
    x = np.arange(len(scenarios))
    width = 0.35

    bars1 = ax.bar(
        x - width / 2,
        df["normal_throughput"],
        width,
        label="Normal JVM",
        color="#2E86AB",
        alpha=0.8,
    )
    bars2 = ax.bar(
        x + width / 2,
        df["sgx_throughput"],
        width,
        label="Gramine-SGX",
        color="#A23B72",
        alpha=0.8,
    )

    ax.set_xlabel("Scenario")
    ax.set_ylabel("Throughput (messages/second)")
    ax.set_title("Throughput Comparison: Normal JVM vs Gramine-SGX")
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=45, ha="right")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / "throughput_comparison.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Generated: {output_dir / 'throughput_comparison.png'}")


def plot_overhead_by_scenario(df: pd.DataFrame, output_dir: Path):
    """Generate overhead percentage bar chart."""
    fig, ax = plt.subplots(figsize=(10, 6))

    scenarios = df["scenario"].str.replace("_", " ").str.title()
    overhead = df["throughput_overhead"]

    colors = [
        "#27AE60" if x < 20 else "#F39C12" if x < 50 else "#E74C3C" for x in overhead
    ]

    bars = ax.barh(scenarios, overhead, color=colors, alpha=0.8)

    ax.set_xlabel("Throughput Overhead (%)")
    ax.set_ylabel("Scenario")
    ax.set_title("SGX Performance Overhead by Scenario")
    ax.axvline(x=20, color="green", linestyle="--", alpha=0.5, linewidth=1)
    ax.axvline(x=50, color="orange", linestyle="--", alpha=0.5, linewidth=1)
    ax.grid(True, alpha=0.3, axis="x")

    # Add value labels
    for i, (bar, val) in enumerate(zip(bars, overhead)):
        ax.text(
            val + 2,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}%",
            va="center",
            fontsize=8,
        )

    plt.tight_layout()
    plt.savefig(output_dir / "overhead_by_scenario.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Generated: {output_dir / 'overhead_by_scenario.png'}")


def plot_latency_comparison(df: pd.DataFrame, output_dir: Path):
    """Generate latency comparison chart."""
    # Filter out rows with missing latency data
    df_latency = df[df["normal_latency"].notna() & df["sgx_latency"].notna()].copy()

    if len(df_latency) == 0:
        print("Warning: No latency data available, skipping latency plot")
        return

    fig, ax = plt.subplots(figsize=(10, 6))

    scenarios = df_latency["scenario"].str.replace("_", " ").str.title()
    x = np.arange(len(scenarios))
    width = 0.35

    bars1 = ax.bar(
        x - width / 2,
        df_latency["normal_latency"],
        width,
        label="Normal JVM",
        color="#2E86AB",
        alpha=0.8,
    )
    bars2 = ax.bar(
        x + width / 2,
        df_latency["sgx_latency"],
        width,
        label="Gramine-SGX",
        color="#A23B72",
        alpha=0.8,
    )

    ax.set_xlabel("Scenario")
    ax.set_ylabel("Average Latency (ms)")
    ax.set_title("Latency Comparison: Normal JVM vs Gramine-SGX")
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=45, ha="right")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / "latency_comparison.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Generated: {output_dir / 'latency_comparison.png'}")


def plot_concurrency_scaling(df: pd.DataFrame, output_dir: Path):
    """Generate concurrency scaling analysis."""
    # Extract concurrency info from scenario names
    concurrency_data = []
    for _, row in df.iterrows():
        scenario = row["scenario"]
        if "single" in scenario:
            clients = 1
        elif "stress" in scenario:
            clients = 100
        elif "very_high" in scenario:
            clients = 50
        elif "high" in scenario:
            clients = 20
        elif "medium" in scenario:
            clients = 10
        elif "low" in scenario:
            clients = 5
        else:
            continue

        concurrency_data.append(
            {
                "clients": clients,
                "normal": row["normal_throughput"],
                "sgx": row["sgx_throughput"],
                "overhead": row["throughput_overhead"],
            }
        )

    if not concurrency_data:
        print("Warning: Could not extract concurrency data")
        return

    conc_df = pd.DataFrame(concurrency_data).sort_values("clients")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Throughput vs concurrency
    ax1.plot(
        conc_df["clients"],
        conc_df["normal"],
        "o-",
        label="Normal JVM",
        color="#2E86AB",
        linewidth=2,
        markersize=8,
    )
    ax1.plot(
        conc_df["clients"],
        conc_df["sgx"],
        "s-",
        label="Gramine-SGX",
        color="#A23B72",
        linewidth=2,
        markersize=8,
    )
    ax1.set_xlabel("Number of Concurrent Clients")
    ax1.set_ylabel("Throughput (messages/second)")
    ax1.set_title("Throughput Scaling with Concurrency")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_xscale("log")

    # Overhead vs concurrency
    ax2.plot(
        conc_df["clients"],
        conc_df["overhead"],
        "D-",
        color="#E74C3C",
        linewidth=2,
        markersize=8,
    )
    ax2.set_xlabel("Number of Concurrent Clients")
    ax2.set_ylabel("Overhead (%)")
    ax2.set_title("SGX Overhead vs Concurrency Level")
    ax2.grid(True, alpha=0.3)
    ax2.set_xscale("log")
    ax2.axhline(y=50, color="orange", linestyle="--", alpha=0.5, linewidth=1)

    plt.tight_layout()
    plt.savefig(output_dir / "concurrency_scaling.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Generated: {output_dir / 'concurrency_scaling.png'}")


def plot_performance_matrix(df: pd.DataFrame, output_dir: Path):
    """Generate performance summary heatmap."""
    fig, ax = plt.subplots(figsize=(10, 6))

    # Prepare data for heatmap
    scenarios = df["scenario"].str.replace("_", " ").str.title()
    metrics = ["Throughput\nOverhead (%)", "Latency\nOverhead (%)"]

    # Create matrix (scenarios x metrics)
    data = np.column_stack(
        [df["throughput_overhead"].fillna(0), df["latency_overhead"].fillna(0)]
    )

    im = ax.imshow(data, cmap="RdYlGn_r", aspect="auto", vmin=0, vmax=100)

    # Set ticks and labels
    ax.set_xticks(np.arange(len(metrics)))
    ax.set_yticks(np.arange(len(scenarios)))
    ax.set_xticklabels(metrics)
    ax.set_yticklabels(scenarios)

    # Add colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Overhead (%)", rotation=270, labelpad=20)

    # Add text annotations
    for i in range(len(scenarios)):
        for j in range(len(metrics)):
            value = data[i, j]
            if not np.isnan(value):
                text = ax.text(
                    j,
                    i,
                    f"{value:.1f}%",
                    ha="center",
                    va="center",
                    color="black",
                    fontsize=8,
                )

    ax.set_title("Performance Overhead Matrix")
    plt.tight_layout()
    plt.savefig(output_dir / "performance_matrix.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Generated: {output_dir / 'performance_matrix.png'}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate benchmark plots from CSV data"
    )
    parser.add_argument("csv_file", type=Path, help="Path to benchmark CSV file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for plots (default: same as CSV file)",
    )

    args = parser.parse_args()

    # Validate input
    if not args.csv_file.exists():
        print(f"Error: CSV file not found: {args.csv_file}")
        sys.exit(1)

    # Set output directory
    output_dir = args.output_dir if args.output_dir else args.csv_file.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading data from: {args.csv_file}")
    df = load_data(args.csv_file)

    print(f"Generating plots in: {output_dir}")

    # Generate all plots
    plot_throughput_comparison(df, output_dir)
    plot_overhead_by_scenario(df, output_dir)
    plot_latency_comparison(df, output_dir)
    plot_concurrency_scaling(df, output_dir)
    plot_performance_matrix(df, output_dir)

    print("\nAll plots generated successfully!")


if __name__ == "__main__":
    main()
