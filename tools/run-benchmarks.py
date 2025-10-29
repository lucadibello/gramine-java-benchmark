#!/usr/bin/env python3

"""
Benchmark automation for the Gramine TLS aggregation tree.

The script builds and launches each server variant, runs the Java benchmark
client once per variant, captures the JSON summary printed by the client,
and writes aggregated JSON/CSV artifacts under the scaling-results/
directory.  The client output prints a banner line ("== Benchmark Summary ==")
followed by pretty-printed JSON; we skip the banner, parse the JSON payload,
and merge the four variants into a single report.

Usage examples:
  python3 tools/run-benchmarks.py --all
  python3 tools/run-benchmarks.py --variants jvm-local native-dynamic
  python3 tools/run-benchmarks.py --no-sudo

The script requires the Java sources to be compiled (it invokes `make server`
once at startup) and expects TLS certificates generated via
`tools/generate-certs.sh`.  Examine the README for a description of each
variant and additional background.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional


# --------------------------------------------------------------------------- #
# Paths & configuration helpers
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    script_dir: Path
    classes_dir: Path
    bin_dir: Path
    results_dir: Path
    keystore: Path
    truststore: Path
    env_file: Path

    @staticmethod
    def resolve() -> "ProjectPaths":
        script_dir = Path(__file__).resolve().parent
        root = script_dir.parent
        return ProjectPaths(
            root=root,
            script_dir=script_dir,
            classes_dir=root / "target" / "classes",
            bin_dir=root / "target" / "bin",
            results_dir=root / "scaling-results",
            keystore=root / "server.keystore",
            truststore=root / "client.truststore",
            env_file=root / ".env",
        )


def locate_java_binary() -> str:
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / "java"
        if candidate.exists():
            return str(candidate)
    return os.environ.get("JAVA_BIN", "java")


def load_env_file(path: Path) -> Dict[str, str]:
    """Parse a POSIX .env file (KEY=VALUE) without executing it."""
    variables: Dict[str, str] = {}
    if not path.exists():
        return variables

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        variables[key.strip()] = value.strip()
    return variables


# --------------------------------------------------------------------------- #
# Variant definitions
# --------------------------------------------------------------------------- #


@dataclass
class VariantConfig:
    name: str
    port: int
    server_cmd: List[str]
    env: Dict[str, str]
    build_steps: List[List[str]]
    startup_timeout: int = 90


def build_variant_configs(
    paths: ProjectPaths, java_bin: str, use_sudo: bool
) -> Dict[str, VariantConfig]:
    sudo_prefix: List[str] = ["sudo", "-n"] if use_sudo else []

    def with_sudo(cmd: Iterable[str]) -> List[str]:
        return sudo_prefix + list(cmd) if sudo_prefix else list(cmd)

    variants: Dict[str, VariantConfig] = {
        "jvm-local": VariantConfig(
            name="jvm-local",
            port=8443,
            server_cmd=[
                java_bin,
                "-cp",
                str(paths.classes_dir),
                "com.benchmark.gramine.enclave.BenchServer",
                "--port",
                "8443",
                "--keystore",
                str(paths.keystore),
                "--password",
                "changeit",
            ],
            env={},
            build_steps=[["make", "server"]],
            startup_timeout=45,
        ),
        "jvm-gramine": VariantConfig(
            name="jvm-gramine",
            port=8444,
            server_cmd=with_sudo(
                [
                    "gramine-sgx",
                    "bench",
                    "-cp",
                    "/app/classes",
                    "com.benchmark.gramine.enclave.BenchServer",
                    "--port",
                    "8444",
                    "--keystore",
                    "server.keystore",
                    "--password",
                    "changeit",
                ]
            ),
            env={},
            build_steps=[
                [
                    "make",
                    "APP_NAME=bench",
                    "STATIC_NATIVE=0",
                    "SGX=1",
                    "all",
                ]
            ],
            startup_timeout=180,
        ),
        "native-dynamic": VariantConfig(
            name="native-dynamic",
            port=8445,
            server_cmd=with_sudo(
                [
                    "gramine-sgx",
                    "native-bench-dynamic",
                    "--port",
                    "8445",
                    "--keystore",
                    "server.keystore",
                    "--password",
                    "changeit",
                ]
            ),
            env={"APP_BIN": "BenchServer"},
            build_steps=[
                [
                    "make",
                    "APP_NAME=native-bench-dynamic",
                    "STATIC_NATIVE=0",
                    "SGX=1",
                    "all",
                ]
            ],
            startup_timeout=180,
        ),
        "native-static": VariantConfig(
            name="native-static",
            port=8446,
            server_cmd=with_sudo(
                [
                    "gramine-sgx",
                    "native-bench-static",
                    "--port",
                    "8446",
                    "--keystore",
                    "server.keystore",
                    "--password",
                    "changeit",
                ]
            ),
            env={"APP_BIN": "BenchServer"},
            build_steps=[
                [
                    "make",
                    "APP_NAME=native-bench-static",
                    "STATIC_NATIVE=1",
                    "SGX=1",
                    "all",
                ]
            ],
            startup_timeout=180,
        ),
    }

    return variants


# --------------------------------------------------------------------------- #
# Utility helpers
# --------------------------------------------------------------------------- #


def ensure_certificates(paths: ProjectPaths) -> None:
    if paths.keystore.exists() and paths.truststore.exists():
        return
    script = paths.root / "tools" / "generate-certs.sh"
    if not script.exists():
        raise FileNotFoundError(f"Certificate generation script missing: {script}")
    subprocess.run(
        ["bash", str(script)],
        cwd=paths.root,
        check=True,
    )


def run_make_server(paths: ProjectPaths) -> None:
    subprocess.run(["make", "server"], cwd=paths.root, check=True)


def wait_for_listen(host: str, port: int, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            try:
                sock.connect((host, port))
            except OSError:
                time.sleep(1.0)
                continue
            else:
                return True
    return False


def terminate_process(proc: subprocess.Popen, timeout: float = 5.0) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def extract_json_summary(output: str) -> Dict[str, object]:
    banner = "== Benchmark Summary =="
    lines = output.splitlines()
    collecting = False
    json_lines: List[str] = []
    brace_depth = 0

    for raw_line in lines:
        line = raw_line.strip()
        if not collecting:
            if line == banner:
                collecting = True
            continue

        if not json_lines and not line:
            # Skip blank lines between banner and JSON opening brace
            continue

        json_lines.append(raw_line)
        brace_depth += raw_line.count("{") - raw_line.count("}")
        if brace_depth == 0 and json_lines:
            break

    if not json_lines:
        raise ValueError("Unable to locate benchmark summary JSON in client output.")

    payload = "\n".join(json_lines).strip()
    return json.loads(payload)


# --------------------------------------------------------------------------- #
# Benchmark coordination
# --------------------------------------------------------------------------- #


@dataclass
class VariantResult:
    name: str
    startup_time: float
    summary: Dict[str, object]
    client_stdout: str
    client_stderr: str


class BenchmarkCoordinator:
    def __init__(
        self,
        paths: ProjectPaths,
        env_overrides: Dict[str, str],
        variants: Dict[str, VariantConfig],
        java_bin: str,
    ):
        self.paths = paths
        self.env_overrides = env_overrides
        self.variants = variants
        self.java_bin = java_bin

    def run_variant(self, config: VariantConfig) -> VariantResult:
        merged_env = os.environ.copy()
        merged_env.update(config.env)

        if config.build_steps:
            print(f"[INFO] Building artifacts for variant '{config.name}'...")
            for step in config.build_steps:
                subprocess.run(step, cwd=self.paths.root, check=True)

        print(f"[INFO] Starting server for variant '{config.name}'...")

        server_proc = subprocess.Popen(
            config.server_cmd,
            cwd=self.paths.root,
            env=merged_env,
            text=True,
        )
        # stdout=subprocess.DEVNULL,
        # stderr=subprocess.DEVNULL,

        try:
            start_time = time.time()
            if not wait_for_listen("127.0.0.1", config.port, config.startup_timeout):
                raise RuntimeError(
                    f"Server for variant '{config.name}' did not start within "
                    f"{config.startup_timeout} seconds."
                )
            startup_time = time.time() - start_time
            print(
                f"[INFO] Variant '{config.name}' ready "
                f"(startup time: {startup_time:.2f}s)"
            )

            client_env = os.environ.copy()
            client_env.update(self.env_overrides)

            client_cmd = [
                self.java_bin,
                "-cp",
                str(self.paths.classes_dir),
                "com.benchmark.gramine.host.BenchClient",
                "--host",
                "127.0.0.1",
                "--port",
                str(config.port),
                "--truststore",
                str(self.paths.truststore),
                "--password",
                "changeit",
            ]

            print(f"[INFO] Running client for variant '{config.name}'...")
            completed = subprocess.run(
                client_cmd,
                cwd=self.paths.root,
                env=client_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

            summary = extract_json_summary(completed.stdout)

            return VariantResult(
                name=config.name,
                startup_time=startup_time,
                summary=summary,
                client_stdout=completed.stdout,
                client_stderr=completed.stderr,
            )
        except Exception:
            if server_proc.poll() is None:
                server_proc.send_signal(signal.SIGTERM)
            raise
        finally:
            terminate_process(server_proc)
            print(f"[INFO] Server for variant '{config.name}' stopped.")


# --------------------------------------------------------------------------- #
# Result persistence
# --------------------------------------------------------------------------- #


class ResultWriter:
    def __init__(self, base_dir: Path, timestamp: datetime):
        self.output_dir = base_dir / timestamp.strftime("%Y%m%d_%H%M%S")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "logs").mkdir(exist_ok=True)
        self.timestamp = timestamp

    def write_artifacts(self, results: List[VariantResult]) -> None:
        self._write_logs(results)
        self._write_json(results)
        self._write_csv(results)

    def _write_logs(self, results: List[VariantResult]) -> None:
        for result in results:
            log_path = self.output_dir / "logs" / f"{result.name}.out"
            log_path.write_text(result.client_stdout)
            if result.client_stderr:
                err_path = self.output_dir / "logs" / f"{result.name}.err"
                err_path.write_text(result.client_stderr)

    def _write_json(self, results: List[VariantResult]) -> None:
        payload = {
            "generatedAt": self.timestamp.isoformat(),
            "variants": [
                {
                    "name": result.name,
                    "startupTimeSeconds": round(result.startup_time, 3),
                    "summary": result.summary,
                }
                for result in results
            ],
        }
        target = self.output_dir / "benchmark_results.json"
        target.write_text(json.dumps(payload, indent=2))
        print(f"[INFO] Wrote JSON summary to {target}")

    def _write_csv(self, results: List[VariantResult]) -> None:
        csv_path = self.output_dir / "scaling_results.csv"
        headers = [
            "variant",
            "scaling_type",
            "threads",
            "executed_threads",
            "data_size",
            "total_size",
            "iterations",
            "avg_time_millis",
        ]
        with csv_path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            for result in results:
                summary = result.summary
                for entry in summary.get("weakScaling", []):
                    writer.writerow(
                        [
                            result.name,
                            "weak",
                            entry.get("threads"),
                            entry.get("executedThreads"),
                            entry.get("dataSize"),
                            "",
                            entry.get("iterations"),
                            entry.get("avgTimeMillis"),
                        ]
                    )
                for entry in summary.get("strongScaling", []):
                    writer.writerow(
                        [
                            result.name,
                            "strong",
                            entry.get("threads"),
                            entry.get("executedThreads"),
                            "",
                            entry.get("totalSize"),
                            entry.get("iterations"),
                            entry.get("avgTimeMillis"),
                        ]
                    )
        print(f"[INFO] Wrote CSV summary to {csv_path}")


# --------------------------------------------------------------------------- #
# Command-line interface
# --------------------------------------------------------------------------- #


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automate Gramine TLS aggregation benchmarks."
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        help="Subset of variants to run (default: all four).",
        choices=["jvm-local", "jvm-gramine", "native-dynamic", "native-static"],
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all variants (default if --variants not provided).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = ProjectPaths.resolve()
    java_bin = locate_java_binary()
    env_overrides = load_env_file(paths.env_file)

    try:
        ensure_certificates(paths)
        run_make_server(paths)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Build prerequisite failed: {exc}") from exc

    variants = build_variant_configs(
        paths=paths, java_bin=java_bin, use_sudo=True
    )

    selected_names = (
        list(variants.keys()) if args.all or not args.variants else args.variants
    )

    coordinator = BenchmarkCoordinator(
        paths=paths,
        env_overrides=env_overrides,
        variants=variants,
        java_bin=java_bin,
    )

    results: List[VariantResult] = []
    for name in selected_names:
        config = variants[name]
        try:
            results.append(coordinator.run_variant(config))
        except subprocess.CalledProcessError as exc:
            print(
                f"[ERROR] Client for variant '{name}' exited with status "
                f"{exc.returncode}",
                file=sys.stderr,
            )
            print(exc.stdout, file=sys.stderr)
            print(exc.stderr, file=sys.stderr)
            raise SystemExit(1) from exc
        except Exception as exc:
            print(f"[ERROR] Failed to benchmark variant '{name}': {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

    timestamp = datetime.now()
    writer = ResultWriter(paths.results_dir, timestamp)
    writer.write_artifacts(results)


if __name__ == "__main__":
    main()
