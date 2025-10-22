#!/usr/bin/env python3

"""
Scientific Benchmark Suite for TLS Server Performance Analysis
Performs strong and weak scaling studies across 4 server variants:
1. JVM on local machine (baseline)
2. JVM inside Gramine-SGX
3. GraalVM native (dynamic + glibc) inside Gramine-SGX
4. GraalVM native (static + musl) inside Gramine-SGX

Scaling Analysis:
- Strong scaling: Fixed total workload, varying number of clients (2^0 to 2^4)
- Weak scaling: Fixed workload per client, varying number of clients
- Speedup calculation: Baseline performance / Variant performance
"""

import argparse
import csv
import json
import re
import signal
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple


# ANSI color codes
class Colors:
    RED: str = "\033[0;31m"
    GREEN: str = "\033[0;32m"
    YELLOW: str = "\033[1;33m"
    BLUE: str = "\033[0;34m"
    CYAN: str = "\033[0;36m"
    MAGENTA: str = "\033[0;35m"
    NC: str = "\033[0m"  # No Color


# Configuration
class Config:
    def __init__(self):
        self.script_dir: Path = Path(__file__).parent.resolve()
        self.project_dir: Path = self.script_dir.parent
        self.classes_dir: Path = self.project_dir / "target" / "classes"
        self.bin_dir: Path = self.project_dir / "target" / "bin"

        # Java paths
        self.java_home: Path = Path("/usr/java/graalvm")
        self.java_bin: Path = self.java_home / "bin" / "java"

        self.server_host: str = "localhost"

        # Different ports for different server variants
        self.port_jvm_local: int = 9443
        self.port_jvm_gramine: int = 9444
        self.port_native_dynamic: int = 9445
        self.port_native_static: int = 9446

        self.results_dir: Path = self.project_dir / "scaling-results"
        self.timestamp: str = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Scaling parameters (2^0 to 2^4 = 1, 2, 4, 8, 16 clients)
        self.client_counts: List[int] = [2**i for i in range(5)]
        self.max_threads: int = 16

        # Active server processes
        self.server_process: Optional[subprocess.Popen[bytes]] = None
        self.current_variant: Optional[str] = None

        # Sudo management for SGX
        self.use_sudo: bool = True


# Logging functions
def print_info(msg: str):
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {msg}")


def print_success(msg: str):
    print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {msg}")


def print_warning(msg: str):
    print(f"{Colors.YELLOW}[WARNING]{Colors.NC} {msg}")


def print_error(msg: str):
    print(f"{Colors.RED}[ERROR]{Colors.NC} {msg}", file=sys.stderr)


def print_header(msg: str):
    print(f"\n{Colors.CYAN}{'=' * 70}{Colors.NC}")
    print(f"{Colors.CYAN}{msg:^70}{Colors.NC}")
    print(f"{Colors.CYAN}{'=' * 70}{Colors.NC}\n")


def print_subheader(msg: str):
    print(f"\n{Colors.MAGENTA}{'─' * 70}{Colors.NC}")
    print(f"{Colors.MAGENTA}{msg}{Colors.NC}")
    print(f"{Colors.MAGENTA}{'─' * 70}{Colors.NC}\n")


# Server management
class ServerManager:
    def __init__(self, config: Config):
        self.config: Config = config

    def check_server(self, port: int, timeout: int = 3) -> bool:
        """Check if server is running and accepting TLS connections"""
        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

            with socket.create_connection(
                (self.config.server_host, port), timeout=timeout
            ) as sock:
                with context.wrap_socket(sock, server_hostname=self.config.server_host):
                    return True
        except (socket.error, ssl.SSLError, ConnectionRefusedError, TimeoutError):
            return False

    def wait_for_server(self, port: int, max_attempts: int = 60) -> Tuple[bool, float]:
        """
        Wait for server to start (increased timeout for SGX)
        Returns: (success: bool, startup_time: float in seconds)
        """
        print_info(f"Waiting for server on port {port}...")
        start_time = time.time()

        for attempt in range(1, max_attempts + 1):
            if self.check_server(port):
                startup_time = time.time() - start_time
                print_success(f"Server is ready (startup time: {startup_time:.2f}s)")
                time.sleep(2)  # Stabilization time
                return True, startup_time

            if attempt % 10 == 0:
                print_info(f"Still waiting... ({attempt}/{max_attempts}s)")

            time.sleep(1)

        print_error(f"Server did not start within {max_attempts} seconds")
        return False, 0.0

    def start_jvm_local(self) -> bool:
        """Start normal JVM server (baseline)"""
        print_info("Starting JVM server (local/baseline)...")

        if self.check_server(self.config.port_jvm_local):
            print_warning(
                f"Server already running on port {self.config.port_jvm_local}"
            )
            return False

        # Check certificates
        keystore = self.config.project_dir / "server.keystore"
        if not keystore.exists():
            print_info("Generating TLS certificates...")
            subprocess.run(
                ["bash", "tools/generate-certs.sh"],
                cwd=self.config.project_dir,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # Start server
        try:
            process = subprocess.Popen(
                [
                    str(self.config.java_bin),
                    "-cp",
                    str(self.config.classes_dir),
                    "BenchServer",
                    "--port",
                    str(self.config.port_jvm_local),
                    "--keystore",
                    str(keystore),
                    "--password",
                    "changeit",
                ],
                cwd=self.config.project_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            self.config.server_process = process
            self.config.current_variant = "jvm-local"

            success, startup_time = self.wait_for_server(self.config.port_jvm_local)
            if success:
                print_success(
                    f"JVM server started (PID: {process.pid}, startup: {startup_time:.2f}s)"
                )
                return True
            else:
                self.stop_server()
                return False

        except Exception as e:
            print_error(f"Failed to start JVM server: {e}")
            return False

    def start_jvm_gramine(self) -> bool:
        """Start JVM inside Gramine-SGX"""
        print_info("Starting JVM inside Gramine-SGX...")

        if self.check_server(self.config.port_jvm_gramine):
            print_warning(
                f"Server already running on port {self.config.port_jvm_gramine}"
            )
            return False

        # Build manifest (clean first to ensure fresh build)
        print_info("Building Gramine manifest for JVM...")
        subprocess.run(
            ["make", "clean"],
            cwd=self.config.project_dir,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                "make",
                "APP_NAME=bench",
                "STATIC_NATIVE=0",
                "SGX=1",
                "all",
            ],
            cwd=self.config.project_dir,
            check=True,
        )

        # Start server
        try:
            cmd = [
                "gramine-sgx",
                "bench",
                "-cp",
                "/app/classes",
                "BenchServer",
                "--port",
                str(self.config.port_jvm_gramine),
                "--keystore",
                "server.keystore",
                "--password",
                "changeit",
            ]

            if self.config.use_sudo:
                cmd = ["sudo", "-n"] + cmd

            process = subprocess.Popen(
                cmd,
                cwd=self.config.project_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            self.config.server_process = process
            self.config.current_variant = "jvm-gramine"

            success, startup_time = self.wait_for_server(
                self.config.port_jvm_gramine, max_attempts=200
            )
            if success:
                print_success(
                    f"JVM-Gramine server started (PID: {process.pid}, startup: {startup_time:.2f}s)"
                )
                return True
            else:
                self.stop_server()
                return False

        except Exception as e:
            print_error(f"Failed to start JVM-Gramine server: {e}")
            return False

    def start_native_dynamic(self) -> bool:
        """Start GraalVM native (dynamic + glibc) inside Gramine-SGX"""
        print_info("Starting GraalVM native-dynamic inside Gramine-SGX...")

        if self.check_server(self.config.port_native_dynamic):
            print_warning(
                f"Server already running on port {self.config.port_native_dynamic}"
            )
            return False

        # Build native image and manifest if needed
        manifest = self.config.project_dir / "native-bench-dynamic.manifest.sgx"
        native_server = self.config.bin_dir / "BenchServer"

        if not manifest.exists() or not native_server.exists():
            print_info("Building native-dynamic image and manifest...")
            subprocess.run(
                ["make", "clean"],
                cwd=self.config.project_dir,
                check=True,
            )
            subprocess.run(
                [
                    "make",
                    "APP_NAME=native-bench-dynamic",
                    "STATIC_NATIVE=0",
                    "SGX=1",
                    "all",
                ],
                cwd=self.config.project_dir,
                check=True,
            )

        # Start server
        try:
            # Set environment variable for the manifest to use BenchServer
            env = {**subprocess.os.environ, "APP_BIN": "BenchServer"}

            cmd = [
                "gramine-sgx",
                "native-bench-dynamic",
                "--port",
                str(self.config.port_native_dynamic),
                "--keystore",
                "server.keystore",
                "--password",
                "changeit",
            ]

            if self.config.use_sudo:
                cmd = ["sudo", "-n", "-E"] + cmd

            process = subprocess.Popen(
                cmd,
                cwd=self.config.project_dir,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            self.config.server_process = process
            self.config.current_variant = "native-dynamic"

            success, startup_time = self.wait_for_server(
                self.config.port_native_dynamic, max_attempts=90
            )
            if success:
                print_success(
                    f"Native-dynamic server started (PID: {process.pid}, startup: {startup_time:.2f}s)"
                )
                return True
            else:
                self.stop_server()
                return False

        except Exception as e:
            print_error(f"Failed to start native-dynamic server: {e}")
            return False

    def start_native_static(self) -> bool:
        """Start GraalVM native (static + musl) inside Gramine-SGX"""
        print_info("Starting GraalVM native-static inside Gramine-SGX...")

        if self.check_server(self.config.port_native_static):
            print_warning(
                f"Server already running on port {self.config.port_native_static}"
            )
            return False

        # Build native image and manifest if needed
        manifest = self.config.project_dir / "native-bench-static.manifest.sgx"
        native_server = self.config.bin_dir / "BenchServer"

        if not manifest.exists() or not native_server.exists():
            print_info("Building native-static image and manifest...")
            subprocess.run(
                ["make", "clean"],
                cwd=self.config.project_dir,
                check=True,
            )
            subprocess.run(
                [
                    "make",
                    "APP_NAME=native-bench-static",
                    "STATIC_NATIVE=1",
                    "SGX=1",
                    "all",
                ],
                cwd=self.config.project_dir,
                check=True,
            )

        # Start server
        try:
            env = {**subprocess.os.environ, "APP_BIN": "BenchServer"}

            cmd = [
                "gramine-sgx",
                "native-bench-static",
                "--port",
                str(self.config.port_native_static),
                "--keystore",
                "server.keystore",
                "--password",
                "changeit",
            ]

            if self.config.use_sudo:
                cmd = ["sudo", "-n", "-E"] + cmd

            process = subprocess.Popen(
                cmd,
                cwd=self.config.project_dir,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            self.config.server_process = process
            self.config.current_variant = "native-static"

            success, startup_time = self.wait_for_server(
                self.config.port_native_static, max_attempts=90
            )
            if success:
                print_success(
                    f"Native-static server started (PID: {process.pid}, startup: {startup_time:.2f}s)"
                )
                return True
            else:
                self.stop_server()
                return False

        except Exception as e:
            print_error(f"Failed to start native-static server: {e}")
            return False

    def stop_server(self):
        """Stop the currently running server"""
        if self.config.server_process:
            print_info(f"Stopping {self.config.current_variant} server...")
            try:
                self.config.server_process.terminate()
                try:
                    self.config.server_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print_warning("Server didn't stop gracefully, forcing...")
                    self.config.server_process.kill()
                    self.config.server_process.wait()
                print_success("Server stopped")
            except Exception as e:
                print_error(f"Error stopping server: {e}")
            finally:
                self.config.server_process = None
                self.config.current_variant = None


# Benchmark metrics extractor
class MetricsExtractor:
    @staticmethod
    def extract_from_output(output: str) -> Dict[str, Optional[float]]:
        """Extract performance metrics from benchmark output"""
        metrics: Dict[str, Optional[float]] = {
            "throughput": None,
            "avg_latency": None,
            "min_latency": None,
            "max_latency": None,
            "p50_latency": None,
            "p95_latency": None,
            "p99_latency": None,
            "total_time": None,
            "total_messages": None,
            "success_rate": None,
        }

        try:
            # Throughput (messages/second)
            match = re.search(r"Throughput:\s+(\d+\.?\d*)", output)
            if match:
                metrics["throughput"] = float(match.group(1))
            else:
                match = re.search(
                    r"(\d+\.?\d*)\s+messages?/s(?:ec(?:ond)?)?", output, re.IGNORECASE
                )
                if match:
                    metrics["throughput"] = float(match.group(1))

            # Latencies (ms)
            match = re.search(r"Average latency:\s+(\d+\.?\d*)\s*ms", output)
            if match:
                metrics["avg_latency"] = float(match.group(1))

            match = re.search(r"Min(?:imum)? latency:\s+(\d+\.?\d*)\s*ms", output)
            if match:
                metrics["min_latency"] = float(match.group(1))

            match = re.search(r"Max(?:imum)? latency:\s+(\d+\.?\d*)\s*ms", output)
            if match:
                metrics["max_latency"] = float(match.group(1))

            match = re.search(r"P50 latency:\s+(\d+\.?\d*)\s*ms", output)
            if match:
                metrics["p50_latency"] = float(match.group(1))

            match = re.search(r"P95 latency:\s+(\d+\.?\d*)\s*ms", output)
            if match:
                metrics["p95_latency"] = float(match.group(1))

            match = re.search(r"P99 latency:\s+(\d+\.?\d*)\s*ms", output)
            if match:
                metrics["p99_latency"] = float(match.group(1))

            # Total time (ms)
            match = re.search(r"Total time:\s+(\d+\.?\d*)\s*ms", output)
            if match:
                metrics["total_time"] = float(match.group(1))

            # Total messages
            match = re.search(r"Total messages (?:sent|processed):\s+(\d+)", output)
            if match:
                metrics["total_messages"] = float(match.group(1))

            # Success rate (%)
            match = re.search(r"Success rate:\s+(\d+\.?\d*)%", output)
            if match:
                metrics["success_rate"] = float(match.group(1))

            # Calculate throughput if not found but we have time and messages
            if (
                metrics["throughput"] is None
                and metrics["total_time"]
                and metrics["total_messages"]
                and metrics["total_time"] > 0
            ):
                metrics["throughput"] = (metrics["total_messages"] * 1000.0) / metrics[
                    "total_time"
                ]

        except Exception as e:
            print_error(f"Error extracting metrics: {e}")

        return metrics


# Benchmark runner
class ScalingBenchmark:
    def __init__(self, config: Config, server_manager: ServerManager):
        self.config: Config = config
        self.server_manager: ServerManager = server_manager
        self.metrics_extractor = MetricsExtractor()

    def run_single_test(
        self,
        variant: str,
        port: int,
        num_clients: int,
        messages_per_client: int,
        run_number: int = 1,
    ) -> Dict[str, Any]:
        """Run a single benchmark test"""

        truststore = self.config.project_dir / "client.truststore"

        cmd = [
            str(self.config.java_bin),
            "-cp",
            str(self.config.classes_dir),
            "BenchClient",
            "--host",
            self.config.server_host,
            "--port",
            str(port),
            "--messages",
            str(messages_per_client),
            "--truststore",
            str(truststore),
            "--truststore-password",
            "changeit",
        ]

        if num_clients > 1:
            cmd.extend(["--load-test", "--clients", str(num_clients)])

        print_info(
            f"Run {run_number}: {num_clients} client(s) × {messages_per_client} messages = {num_clients * messages_per_client} total"
        )

        try:
            result = subprocess.run(
                cmd,
                cwd=self.config.project_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            metrics = self.metrics_extractor.extract_from_output(result.stdout)

            return {
                "variant": variant,
                "num_clients": num_clients,
                "messages_per_client": messages_per_client,
                "total_messages": num_clients * messages_per_client,
                "run_number": run_number,
                "success": result.returncode == 0,
                "output": result.stdout,
                **metrics,
            }

        except subprocess.TimeoutExpired:
            print_error("Benchmark timed out")
            return {
                "variant": variant,
                "num_clients": num_clients,
                "messages_per_client": messages_per_client,
                "total_messages": num_clients * messages_per_client,
                "run_number": run_number,
                "success": False,
                "error": "timeout",
            }
        except Exception as e:
            print_error(f"Benchmark failed: {e}")
            return {
                "variant": variant,
                "num_clients": num_clients,
                "messages_per_client": messages_per_client,
                "total_messages": num_clients * messages_per_client,
                "run_number": run_number,
                "success": False,
                "error": str(e),
            }

    def run_strong_scaling(
        self, variant: str, port: int, total_messages: int = 1000, num_runs: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Strong scaling: Fixed total workload, vary number of clients
        Total work = constant, work per client = total_work / num_clients
        """
        print_subheader(f"Strong Scaling Test: {variant}")
        print_info(f"Fixed total workload: {total_messages} messages")
        print_info(f"Number of runs per configuration: {num_runs}")

        results = []

        for num_clients in self.config.client_counts:
            messages_per_client = total_messages // num_clients

            print(f"\n{Colors.YELLOW}Testing with {num_clients} client(s):{Colors.NC}")

            for run in range(1, num_runs + 1):
                result = self.run_single_test(
                    variant, port, num_clients, messages_per_client, run
                )
                result["scaling_type"] = "strong"
                results.append(result)

                if result["success"] and result.get("throughput"):
                    print_success(
                        f"  Throughput: {result['throughput']:.2f} msg/s, "
                        f"Avg Latency: {result.get('avg_latency', 0):.2f} ms"
                    )

                time.sleep(1)  # Brief pause between runs

        return results

    def run_weak_scaling(
        self, variant: str, port: int, messages_per_client: int = 100, num_runs: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Weak scaling: Fixed workload per client, vary number of clients
        Work per client = constant, total work = work_per_client × num_clients
        """
        print_subheader(f"Weak Scaling Test: {variant}")
        print_info(f"Fixed workload per client: {messages_per_client} messages")
        print_info(f"Number of runs per configuration: {num_runs}")

        results = []

        for num_clients in self.config.client_counts:
            total_messages = num_clients * messages_per_client

            print(
                f"\n{Colors.YELLOW}Testing with {num_clients} client(s) ({total_messages} total messages):{Colors.NC}"
            )

            for run in range(1, num_runs + 1):
                result = self.run_single_test(
                    variant, port, num_clients, messages_per_client, run
                )
                result["scaling_type"] = "weak"
                results.append(result)

                if result["success"] and result.get("throughput"):
                    print_success(
                        f"  Throughput: {result['throughput']:.2f} msg/s, "
                        f"Avg Latency: {result.get('avg_latency', 0):.2f} ms"
                    )

                time.sleep(1)

        return results

    def run_variant_benchmarks(
        self,
        variant: str,
        strong_total: int = 1000,
        weak_per_client: int = 100,
        num_runs: int = 3,
    ) -> Dict[str, Any]:
        """Run both strong and weak scaling for a variant"""

        print_header(f"Benchmarking: {variant.upper()}")

        # Determine which server to start and which port to use
        server_configs = {
            "jvm-local": (
                self.server_manager.start_jvm_local,
                self.config.port_jvm_local,
            ),
            "jvm-gramine": (
                self.server_manager.start_jvm_gramine,
                self.config.port_jvm_gramine,
            ),
            "native-dynamic": (
                self.server_manager.start_native_dynamic,
                self.config.port_native_dynamic,
            ),
            "native-static": (
                self.server_manager.start_native_static,
                self.config.port_native_static,
            ),
        }

        if variant not in server_configs:
            print_error(f"Unknown variant: {variant}")
            return {"variant": variant, "error": "unknown_variant"}

        start_func, port = server_configs[variant]

        # Start server and measure startup time
        startup_start = time.time()
        if not start_func():
            print_error(f"Failed to start {variant} server")
            return {"variant": variant, "error": "server_start_failed"}
        startup_time = time.time() - startup_start

        try:
            # Warmup
            print_info("Running warmup...")
            self.run_single_test(variant, port, 1, 10, 0)
            time.sleep(2)

            # Strong scaling
            strong_results = self.run_strong_scaling(
                variant, port, strong_total, num_runs
            )
            time.sleep(3)

            # Weak scaling
            weak_results = self.run_weak_scaling(
                variant, port, weak_per_client, num_runs
            )

            return {
                "variant": variant,
                "startup_time": startup_time,
                "strong_scaling": strong_results,
                "weak_scaling": weak_results,
                "timestamp": datetime.now().isoformat(),
            }

        finally:
            # Always stop the server
            self.server_manager.stop_server()
            time.sleep(3)  # Cool-down period


# Results analyzer and reporter
class ScalingAnalyzer:
    def __init__(self, config: Config):
        self.config = config

    def calculate_speedup(
        self,
        baseline_value: Optional[float],
        variant_value: Optional[float],
        metric_type: str = "throughput",
    ) -> Optional[float]:
        """
        Calculate speedup relative to baseline
        For throughput: speedup = variant / baseline (higher is better)
        For latency: speedup = baseline / variant (lower latency = higher speedup)
        """
        if baseline_value is None or variant_value is None or variant_value == 0:
            return None

        if metric_type == "throughput":
            return variant_value / baseline_value
        else:  # latency or time
            return baseline_value / variant_value

    def calculate_efficiency(
        self, speedup: Optional[float], num_clients: int
    ) -> Optional[float]:
        """
        Parallel efficiency = speedup / num_clients
        Perfect scaling = 1.0 (100%)
        """
        if speedup is None or num_clients == 0:
            return None
        return speedup / num_clients

    def aggregate_runs(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate multiple runs into mean and std dev"""
        if not results:
            return {}

        # Group by num_clients
        by_clients: Dict[int, List[Dict[str, Any]]] = {}
        for r in results:
            nc = r.get("num_clients", 0)
            if nc not in by_clients:
                by_clients[nc] = []
            by_clients[nc].append(r)

        aggregated = []
        for num_clients in sorted(by_clients.keys()):
            runs = by_clients[num_clients]

            # Extract throughputs and latencies
            throughputs = [r["throughput"] for r in runs if r.get("throughput")]
            latencies = [r["avg_latency"] for r in runs if r.get("avg_latency")]

            agg = {
                "num_clients": num_clients,
                "num_runs": len(runs),
                "messages_per_client": runs[0].get("messages_per_client", 0),
                "total_messages": runs[0].get("total_messages", 0),
            }

            if throughputs:
                import statistics

                agg["throughput_mean"] = statistics.mean(throughputs)
                if len(throughputs) > 1:
                    agg["throughput_stdev"] = statistics.stdev(throughputs)
                else:
                    agg["throughput_stdev"] = 0.0

            if latencies:
                import statistics

                agg["latency_mean"] = statistics.mean(latencies)
                if len(latencies) > 1:
                    agg["latency_stdev"] = statistics.stdev(latencies)
                else:
                    agg["latency_stdev"] = 0.0

            aggregated.append(agg)

        return {"aggregated": aggregated, "raw": results}

    def generate_scaling_report(self, all_results: List[Dict[str, Any]]):
        """Generate comprehensive scaling analysis report"""

        print_header("GENERATING SCALING ANALYSIS REPORT")

        # Create output directory
        output_dir = self.config.results_dir / self.config.timestamp
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save raw results as JSON
        raw_file = output_dir / "raw_results.json"
        with open(raw_file, "w") as f:
            json.dump(all_results, f, indent=2)
        print_success(f"Raw results saved to: {raw_file}")

        # Process each variant
        baseline_data = None
        processed_variants = {}
        startup_times = {}

        for variant_result in all_results:
            variant = variant_result.get("variant")
            if not variant:
                continue

            strong = self.aggregate_runs(variant_result.get("strong_scaling", []))
            weak = self.aggregate_runs(variant_result.get("weak_scaling", []))
            startup_time = variant_result.get("startup_time", 0.0)

            processed_variants[variant] = {"strong": strong, "weak": weak}
            startup_times[variant] = startup_time

            # Use jvm-local as baseline
            if variant == "jvm-local":
                baseline_data = processed_variants[variant]

        # Generate startup times CSV
        self._generate_startup_times_csv(output_dir, startup_times)

        # Generate comparison CSV for strong scaling
        self._generate_strong_scaling_csv(output_dir, processed_variants, baseline_data)

        # Generate comparison CSV for weak scaling
        self._generate_weak_scaling_csv(output_dir, processed_variants, baseline_data)

        # Generate text report
        self._generate_text_report(
            output_dir, processed_variants, baseline_data, startup_times
        )

        print_success(f"\nAll reports saved to: {output_dir}")

    def _generate_strong_scaling_csv(
        self,
        output_dir: Path,
        variants: Dict[str, Any],
        baseline: Optional[Dict[str, Any]],
    ):
        """Generate CSV for strong scaling analysis"""

        csv_file = output_dir / "strong_scaling.csv"

        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)

            # Header
            header = [
                "num_clients",
                "variant",
                "throughput_mean",
                "throughput_stdev",
                "latency_mean",
                "latency_stdev",
                "speedup_throughput",
                "speedup_latency",
                "efficiency_throughput",
                "efficiency_latency",
            ]
            writer.writerow(header)

            # Get baseline throughput/latency for each client count
            baseline_lookup = {}
            if baseline:
                for agg in baseline.get("strong", {}).get("aggregated", []):
                    nc = agg["num_clients"]
                    baseline_lookup[nc] = {
                        "throughput": agg.get("throughput_mean"),
                        "latency": agg.get("latency_mean"),
                    }

            # Write data for each variant
            for variant_name in sorted(variants.keys()):
                variant_data = variants[variant_name]

                for agg in variant_data.get("strong", {}).get("aggregated", []):
                    nc = agg["num_clients"]

                    # Calculate speedups
                    speedup_tp = None
                    speedup_lat = None
                    eff_tp = None
                    eff_lat = None

                    if nc in baseline_lookup:
                        baseline_tp = baseline_lookup[nc]["throughput"]
                        baseline_lat = baseline_lookup[nc]["latency"]

                        speedup_tp = self.calculate_speedup(
                            baseline_tp, agg.get("throughput_mean"), "throughput"
                        )
                        speedup_lat = self.calculate_speedup(
                            baseline_lat, agg.get("latency_mean"), "latency"
                        )

                        if speedup_tp is not None:
                            eff_tp = self.calculate_efficiency(speedup_tp, nc)
                        if speedup_lat is not None:
                            eff_lat = self.calculate_efficiency(speedup_lat, nc)

                    # Format values, using empty string for None
                    row = [
                        nc,
                        variant_name,
                        f"{agg.get('throughput_mean'):.2f}"
                        if agg.get("throughput_mean") is not None
                        else "",
                        f"{agg.get('throughput_stdev'):.2f}"
                        if agg.get("throughput_stdev") is not None
                        else "",
                        f"{agg.get('latency_mean'):.2f}"
                        if agg.get("latency_mean") is not None
                        else "",
                        f"{agg.get('latency_stdev'):.2f}"
                        if agg.get("latency_stdev") is not None
                        else "",
                        f"{speedup_tp:.4f}" if speedup_tp is not None else "",
                        f"{speedup_lat:.4f}" if speedup_lat is not None else "",
                        f"{eff_tp:.4f}" if eff_tp is not None else "",
                        f"{eff_lat:.4f}" if eff_lat is not None else "",
                    ]
                    writer.writerow(row)

        print_success(f"Strong scaling CSV: {csv_file}")
        if not baseline:
            print_warning(
                "  Note: No baseline data found - speedup/efficiency not calculated"
            )

    def _generate_weak_scaling_csv(
        self,
        output_dir: Path,
        variants: Dict[str, Any],
        baseline: Optional[Dict[str, Any]],
    ):
        """Generate CSV for weak scaling analysis"""

        csv_file = output_dir / "weak_scaling.csv"

        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)

            # Header
            header = [
                "num_clients",
                "total_messages",
                "variant",
                "throughput_mean",
                "throughput_stdev",
                "latency_mean",
                "latency_stdev",
                "speedup_throughput",
                "speedup_latency",
                "efficiency_throughput",
                "efficiency_latency",
            ]
            writer.writerow(header)

            # Get baseline data
            baseline_lookup = {}
            if baseline:
                for agg in baseline.get("weak", {}).get("aggregated", []):
                    nc = agg["num_clients"]
                    baseline_lookup[nc] = {
                        "throughput": agg.get("throughput_mean"),
                        "latency": agg.get("latency_mean"),
                    }

            # Write data for each variant
            for variant_name in sorted(variants.keys()):
                variant_data = variants[variant_name]

                for agg in variant_data.get("weak", {}).get("aggregated", []):
                    nc = agg["num_clients"]

                    # Calculate speedups
                    speedup_tp = None
                    speedup_lat = None
                    eff_tp = None
                    eff_lat = None

                    if nc in baseline_lookup:
                        baseline_tp = baseline_lookup[nc]["throughput"]
                        baseline_lat = baseline_lookup[nc]["latency"]

                        speedup_tp = self.calculate_speedup(
                            baseline_tp, agg.get("throughput_mean"), "throughput"
                        )
                        speedup_lat = self.calculate_speedup(
                            baseline_lat, agg.get("latency_mean"), "latency"
                        )

                        if speedup_tp is not None:
                            eff_tp = self.calculate_efficiency(speedup_tp, nc)
                        if speedup_lat is not None:
                            eff_lat = self.calculate_efficiency(speedup_lat, nc)

                    # Format values, using empty string for None
                    row = [
                        nc,
                        agg.get("total_messages", ""),
                        variant_name,
                        f"{agg.get('throughput_mean'):.2f}"
                        if agg.get("throughput_mean") is not None
                        else "",
                        f"{agg.get('throughput_stdev'):.2f}"
                        if agg.get("throughput_stdev") is not None
                        else "",
                        f"{agg.get('latency_mean'):.2f}"
                        if agg.get("latency_mean") is not None
                        else "",
                        f"{agg.get('latency_stdev'):.2f}"
                        if agg.get("latency_stdev") is not None
                        else "",
                        f"{speedup_tp:.4f}" if speedup_tp is not None else "",
                        f"{speedup_lat:.4f}" if speedup_lat is not None else "",
                        f"{eff_tp:.4f}" if eff_tp is not None else "",
                        f"{eff_lat:.4f}" if eff_lat is not None else "",
                    ]
                    writer.writerow(row)

        print_success(f"Weak scaling CSV: {csv_file}")
        if not baseline:
            print_warning(
                "  Note: No baseline data found - speedup/efficiency not calculated"
            )

    def _generate_startup_times_csv(
        self, output_dir: Path, startup_times: Dict[str, float]
    ):
        """Generate CSV for startup times"""

        csv_file = output_dir / "startup_times.csv"

        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["variant", "startup_time_seconds"])

            for variant_name in sorted(startup_times.keys()):
                writer.writerow([variant_name, startup_times[variant_name]])

        print_success(f"Startup times CSV: {csv_file}")

    def _generate_text_report(
        self,
        output_dir: Path,
        variants: Dict[str, Any],
        baseline: Optional[Dict[str, Any]],
        startup_times: Dict[str, float],
    ):
        """Generate human-readable text report"""

        report_file = output_dir / "scaling_report.txt"

        with open(report_file, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("SCALING ANALYSIS REPORT\n")
            f.write("TLS Server Performance Study\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

            f.write(
                "This report analyzes strong and weak scaling across 4 server variants:\n"
            )
            f.write("1. jvm-local      - JVM on local machine (baseline)\n")
            f.write("2. jvm-gramine    - JVM inside Gramine-SGX\n")
            f.write("3. native-dynamic - GraalVM native (glibc) inside Gramine-SGX\n")
            f.write("4. native-static  - GraalVM native (musl) inside Gramine-SGX\n\n")

            f.write("SCALING DEFINITIONS:\n")
            f.write("- Strong scaling: Fixed total workload, varying client count\n")
            f.write("- Weak scaling: Fixed per-client workload, varying client count\n")
            f.write("- Speedup: Relative performance vs baseline (>1.0 is better)\n")
            f.write("- Efficiency: Speedup / num_clients (1.0 = perfect scaling)\n\n")

            f.write("=" * 80 + "\n\n")

            # Startup times section
            f.write("SERVER STARTUP TIMES\n")
            f.write("-" * 80 + "\n\n")

            baseline_startup = startup_times.get("jvm-local", 0.0)
            f.write(
                f"{'Variant':<20} | {'Startup Time (s)':<18} | {'Overhead vs Baseline':<20}\n"
            )
            f.write("-" * 80 + "\n")

            for variant_name in sorted(startup_times.keys()):
                startup = startup_times[variant_name]
                if baseline_startup > 0 and variant_name != "jvm-local":
                    overhead = ((startup - baseline_startup) / baseline_startup) * 100
                    overhead_str = f"{overhead:+.1f}%"
                else:
                    overhead_str = "baseline" if variant_name == "jvm-local" else "N/A"

                f.write(
                    f"{variant_name:<20} | {startup:>16.2f}s | {overhead_str:<20}\n"
                )

            f.write("\n" + "=" * 80 + "\n\n")

            # Strong scaling section
            f.write("STRONG SCALING RESULTS\n")
            f.write("-" * 80 + "\n\n")

            for variant_name in sorted(variants.keys()):
                variant_data = variants[variant_name]
                f.write(f"\n{variant_name.upper()}\n")
                f.write("-" * 40 + "\n")

                f.write(
                    f"{'Clients':<8} | {'Throughput':<20} | {'Latency (ms)':<20} | {'Speedup':<10}\n"
                )
                f.write(
                    f"{'':<8} | {'Mean ± StDev':<20} | {'Mean ± StDev':<20} | {'(vs base)':<10}\n"
                )
                f.write("-" * 80 + "\n")

                baseline_lookup = {}
                if baseline:
                    for agg in baseline.get("strong", {}).get("aggregated", []):
                        nc = agg["num_clients"]
                        baseline_lookup[nc] = agg.get("throughput_mean")

                for agg in variant_data.get("strong", {}).get("aggregated", []):
                    nc = agg["num_clients"]
                    tp_mean = agg.get("throughput_mean", 0)
                    tp_std = agg.get("throughput_stdev", 0)
                    lat_mean = agg.get("latency_mean", 0)
                    lat_std = agg.get("latency_stdev", 0)

                    speedup_str = "N/A"
                    if nc in baseline_lookup and baseline_lookup[nc]:
                        speedup = tp_mean / baseline_lookup[nc]
                        speedup_str = f"{speedup:.3f}"

                    f.write(
                        f"{nc:<8} | {tp_mean:>8.2f} ± {tp_std:<8.2f} | "
                        f"{lat_mean:>8.2f} ± {lat_std:<8.2f} | {speedup_str:<10}\n"
                    )

                f.write("\n")

            f.write("\n" + "=" * 80 + "\n\n")

            # Weak scaling section
            f.write("WEAK SCALING RESULTS\n")
            f.write("-" * 80 + "\n\n")

            for variant_name in sorted(variants.keys()):
                variant_data = variants[variant_name]
                f.write(f"\n{variant_name.upper()}\n")
                f.write("-" * 40 + "\n")

                f.write(
                    f"{'Clients':<8} | {'Total Msg':<10} | {'Throughput':<20} | {'Latency (ms)':<20} | {'Speedup':<10}\n"
                )
                f.write(
                    f"{'':<8} | {'':<10} | {'Mean ± StDev':<20} | {'Mean ± StDev':<20} | {'(vs base)':<10}\n"
                )
                f.write("-" * 90 + "\n")

                baseline_lookup = {}
                if baseline:
                    for agg in baseline.get("weak", {}).get("aggregated", []):
                        nc = agg["num_clients"]
                        baseline_lookup[nc] = agg.get("throughput_mean")

                for agg in variant_data.get("weak", {}).get("aggregated", []):
                    nc = agg["num_clients"]
                    total = agg.get("total_messages", 0)
                    tp_mean = agg.get("throughput_mean", 0)
                    tp_std = agg.get("throughput_stdev", 0)
                    lat_mean = agg.get("latency_mean", 0)
                    lat_std = agg.get("latency_stdev", 0)

                    speedup_str = "N/A"
                    if nc in baseline_lookup and baseline_lookup[nc]:
                        speedup = tp_mean / baseline_lookup[nc]
                        speedup_str = f"{speedup:.3f}"

                    f.write(
                        f"{nc:<8} | {total:<10} | {tp_mean:>8.2f} ± {tp_std:<8.2f} | "
                        f"{lat_mean:>8.2f} ± {lat_std:<8.2f} | {speedup_str:<10}\n"
                    )

                f.write("\n")

            f.write("\n" + "=" * 80 + "\n")
            f.write("END OF REPORT\n")
            f.write("=" * 80 + "\n")

        print_success(f"Text report: {report_file}")

        # Display summary
        with open(report_file, "r") as f:
            print("\n" + f.read())


# Helper function to ensure sudo access
def ensure_sudo_access(needs_sudo: bool) -> bool:
    """
    Ensure sudo access is available for SGX operations.
    Prompts user for password if needed and validates sudo access.
    """
    if not needs_sudo:
        return True

    print_info("This benchmark requires sudo access for Gramine-SGX operations.")
    print_info("Checking sudo access...")

    # Check if we already have sudo access
    result = subprocess.run(
        ["sudo", "-n", "true"],
        capture_output=True,
    )

    if result.returncode == 0:
        print_success("Sudo access already available")
        return True

    # Need to authenticate
    print_info("Please enter your sudo password:")
    result = subprocess.run(
        ["sudo", "-v"],
        capture_output=False,
    )

    if result.returncode != 0:
        print_error("Failed to obtain sudo access")
        return False

    print_success("Sudo access granted")

    # Start a background process to keep sudo alive
    # This prevents password prompts during the benchmark
    def keep_sudo_alive():
        while True:
            time.sleep(60)
            subprocess.run(["sudo", "-n", "true"], capture_output=True)

    import threading

    sudo_thread = threading.Thread(target=keep_sudo_alive, daemon=True)
    sudo_thread.start()

    return True


# Main function
def main():
    parser = argparse.ArgumentParser(
        description="Scientific Scaling Benchmark Suite for TLS Servers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Server Variants:
  jvm-local       - JVM on local machine (baseline)
  jvm-gramine     - JVM inside Gramine-SGX
  native-dynamic  - GraalVM native (glibc) inside Gramine-SGX
  native-static   - GraalVM native (musl) inside Gramine-SGX

Scaling Studies:
  Strong scaling: Fixed total workload (default: 1000 messages)
                  Clients: 1, 2, 4, 8, 16
                  Messages per client: 1000/N

  Weak scaling:   Fixed per-client workload (default: 100 messages)
                  Clients: 1, 2, 4, 8, 16
                  Messages per client: 100 (constant)

Examples:
  %(prog)s --all                    # Run all variants
  %(prog)s --variants jvm-local jvm-gramine  # Run specific variants
  %(prog)s --all --runs 5           # Run 5 iterations per configuration
  %(prog)s --all --strong-total 2000 --weak-per-client 200
        """,
    )

    parser.add_argument(
        "--all", action="store_true", help="Run benchmarks for all 4 variants"
    )

    parser.add_argument(
        "--variants",
        nargs="+",
        choices=["jvm-local", "jvm-gramine", "native-dynamic", "native-static"],
        help="Specific variants to benchmark",
    )

    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of runs per configuration (default: 3)",
    )

    parser.add_argument(
        "--strong-total",
        type=int,
        default=1000,
        help="Total messages for strong scaling (default: 1000)",
    )

    parser.add_argument(
        "--weak-per-client",
        type=int,
        default=100,
        help="Messages per client for weak scaling (default: 100)",
    )

    args = parser.parse_args()

    # Determine which variants to run
    variants_to_run = []
    if args.all:
        variants_to_run = [
            "jvm-local",
            "jvm-gramine",
            "native-dynamic",
            "native-static",
        ]
    elif args.variants:
        variants_to_run = args.variants
    else:
        print_error("Must specify --all or --variants")
        parser.print_help()
        sys.exit(1)

    # Create configuration
    config = Config()
    server_manager = ServerManager(config)
    benchmark = ScalingBenchmark(config, server_manager)
    analyzer = ScalingAnalyzer(config)

    # Setup cleanup handler
    def cleanup(signum: Optional[int] = None, frame: Any = None):
        print("\n")
        print_info("Received interrupt signal, cleaning up...")
        try:
            server_manager.stop_server()
        except Exception as e:
            print_error(f"Error during cleanup: {e}")
        finally:
            print_info("Cleanup complete")
            sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        # Check if we need sudo (any Gramine variant)
        needs_sudo = any(
            v in variants_to_run
            for v in ["jvm-gramine", "native-dynamic", "native-static"]
        )

        if needs_sudo and not ensure_sudo_access(True):
            print_error("Sudo access is required for Gramine-SGX benchmarks")
            sys.exit(1)

        print_header("SCIENTIFIC SCALING BENCHMARK SUITE")
        print_info(f"Variants to test: {', '.join(variants_to_run)}")
        print_info(f"Client counts: {config.client_counts}")
        print_info(f"Runs per configuration: {args.runs}")
        print_info(f"Strong scaling total messages: {args.strong_total}")
        print_info(f"Weak scaling messages per client: {args.weak_per_client}")
        print_info(f"Results will be saved to: {config.results_dir}/{config.timestamp}")

        if "jvm-local" not in variants_to_run:
            print_warning("WARNING: 'jvm-local' is not in the variant list.")
            print_warning(
                "Speedup and efficiency calculations require jvm-local as baseline."
            )

        # Run benchmarks for each variant
        all_results = []

        for i, variant in enumerate(variants_to_run, 1):
            print_header(f"VARIANT {i}/{len(variants_to_run)}: {variant.upper()}")
            try:
                result = benchmark.run_variant_benchmarks(
                    variant,
                    strong_total=args.strong_total,
                    weak_per_client=args.weak_per_client,
                    num_runs=args.runs,
                )
                all_results.append(result)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print_error(f"Error benchmarking {variant}: {e}")
                import traceback

                traceback.print_exc()

        # Generate analysis report
        if all_results:
            print_header("GENERATING ANALYSIS REPORTS")
            analyzer.generate_scaling_report(all_results)
            print_success("\n✓ Benchmark suite completed successfully!")
            print_info(f"Results location: {config.results_dir}/{config.timestamp}")
        else:
            print_error("No results collected")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n")
        print_info("Interrupted by user")
        cleanup()
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        cleanup()
        sys.exit(1)


if __name__ == "__main__":
    main()
