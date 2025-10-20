#!/usr/bin/env python3

"""
Benchmark Test Runner for TLS Server - Normal JVM vs Gramine-SGX Comparison
This script runs benchmarks against both normal JVM and Gramine-SGX to measure overhead
"""

import argparse
import csv
import re
import signal
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ANSI color codes
class Colors:
    RED: str = "\033[0;31m"
    GREEN: str = "\033[0;32m"
    YELLOW: str = "\033[1;33m"
    BLUE: str = "\033[0;34m"
    NC: str = "\033[0m"  # No Color


# Configuration
class Config:
    def __init__(self):
        self.script_dir: Path = Path(__file__).parent.resolve()
        self.project_dir: Path = self.script_dir.parent
        self.classes_dir: Path = self.project_dir / "target" / "classes"

        self.server_host: str = "localhost"
        self.normal_server_port: int = 9443
        self.sgx_server_port: int = 9444
        self.results_dir: Path = self.project_dir / "benchmark-results"
        self.comparison_dir: Path = self.results_dir / "comparison"

        self.normal_server_process: subprocess.Popen[bytes] | None = None
        self.sgx_server_process: subprocess.Popen[bytes] | None = None


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
    print(f"\n{Colors.GREEN}{'=' * 40}{Colors.NC}")
    print(f"{Colors.GREEN}{msg}{Colors.NC}")
    print(f"{Colors.GREEN}{'=' * 40}{Colors.NC}\n")


# Server management
class ServerManager:
    def __init__(self, config: Config):
        self.config: Config = config

    def check_server(self, port: int, timeout: int = 3) -> bool:
        """Check if server is running and accepting TLS connections"""
        try:
            # Try to establish a TLS connection
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

    def check_server_verbose(self, port: int) -> bool:
        """Check server with detailed feedback"""
        print_info(
            f"Checking if server is running on {self.config.server_host}:{port}..."
        )

        if self.check_server(port):
            print_success("Server is running and accepting TLS connections")
            return True
        else:
            print_error(
                f"Server is not running or not accepting connections on port {port}"
            )
            return False

    def wait_for_server(self, port: int, max_attempts: int = 60) -> bool:
        """Wait for server to start (increased timeout for SGX)"""
        print_info("Waiting for server to start...")
        print_info("Press Ctrl+C to cancel")

        try:
            for attempt in range(1, max_attempts + 1):
                if self.check_server(port):
                    print_success("Server is ready")
                    time.sleep(2)  # Give it extra time to be fully ready
                    return True

                if attempt % 10 == 0:
                    print_info(f"Still waiting... (attempt {attempt}/{max_attempts})")

                # Use shorter sleep intervals to be more responsive to Ctrl+C
                for _ in range(10):
                    time.sleep(0.1)

            print_error(f"Server did not start within {max_attempts} seconds")
            return False
        except KeyboardInterrupt:
            print("\n")
            print_info("Server startup interrupted by user")
            return False

    def test_server_health(self, port: int) -> bool:
        """Test server health with a simple message"""
        print_info("Testing server health...")

        client_class = self.config.classes_dir / "client" / "BenchClient.class"
        truststore = self.config.project_dir / "client.truststore"

        if not client_class.exists() or not truststore.exists():
            print_warning(
                "Cannot perform health check: client classes or truststore not found"
            )
            return True  # Don't fail if we can't test

        try:
            result = subprocess.run(
                [
                    "java",
                    "-cp",
                    str(self.config.classes_dir),
                    "client.BenchClient",
                    "--host",
                    self.config.server_host,
                    "--port",
                    str(port),
                    "--messages",
                    "3",
                    "--truststore",
                    str(truststore),
                    "--truststore-password",
                    "changeit",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )

            if result.returncode == 0:
                print_success("Server health check passed")
                return True
            else:
                print_error("Server health check failed")
                return False
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            print_error("Server health check failed")
            return False

    def start_normal_server(self) -> bool:
        """Start normal JVM server"""
        print_info(
            f"Starting normal JVM server on port {self.config.normal_server_port}..."
        )

        try:
            # Check if server is already running
            if self.check_server(self.config.normal_server_port):
                print_warning(
                    f"A server is already running on port {self.config.normal_server_port}"
                )
                print_info("Please stop the existing server to continue with testing.")
                return False

            # Check if certificates exist
            keystore = self.config.project_dir / "server.keystore"
            truststore = self.config.project_dir / "client.truststore"

            if not keystore.exists() or not truststore.exists():
                print_info("Generating TLS certificates...")
                _ = subprocess.run(
                    ["make", "certs"], cwd=self.config.project_dir, check=True
                )

            # Start server
            self.config.results_dir.mkdir(parents=True, exist_ok=True)
            log_file = self.config.results_dir / "normal_server.log"

            with open(log_file, "w") as log:
                self.config.normal_server_process = subprocess.Popen(
                    [
                        "java",
                        "-cp",
                        str(self.config.classes_dir),
                        "server.BenchServer",
                        "--port",
                        str(self.config.normal_server_port),
                    ],
                    cwd=self.config.project_dir,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )

            try:
                if self.wait_for_server(self.config.normal_server_port):
                    print_success(
                        f"Normal JVM server started (PID: {self.config.normal_server_process.pid})"
                    )
                    if self.test_server_health(self.config.normal_server_port):
                        return True
                    else:
                        print_error("Normal JVM server started but failed health check")
                        self.stop_normal_server()
                        return False
                else:
                    print_error("Failed to start normal JVM server")
                    if self.config.normal_server_process:
                        self.stop_normal_server()
                    return False
            except KeyboardInterrupt:
                print("\n")
                print_info("Normal server startup interrupted by user")
                if self.config.normal_server_process:
                    self.stop_normal_server()
                raise
        except KeyboardInterrupt:
            print("\n")
            print_info("Normal server startup cancelled by user")
            return False

    def stop_normal_server(self):
        """Stop normal JVM server"""
        if self.config.normal_server_process is None:
            return

        try:
            print_info(
                f"Stopping normal JVM server (PID: {self.config.normal_server_process.pid})"
            )
            self.config.normal_server_process.terminate()

            # Wait up to 10 seconds for graceful shutdown
            try:
                _ = self.config.normal_server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print_warning("Force killing normal JVM server")
                self.config.normal_server_process.kill()
                _ = self.config.normal_server_process.wait()

            print_success("Normal server stopped")
            self.config.normal_server_process = None
            time.sleep(2)  # Wait for port to be released
        except Exception as e:
            print_error(f"Error stopping normal server: {e}")

    def start_sgx_server(self) -> bool:
        """Start Gramine-SGX server with sudo"""
        print_info(
            f"Starting Gramine-SGX server on port {self.config.sgx_server_port}..."
        )

        try:
            # Check if server is already running
            if self.check_server(self.config.sgx_server_port):
                print_warning(
                    f"A server is already running on port {self.config.sgx_server_port}"
                )
                print_info("The existing SGX server will be used for this test.")
                return True

            # Check if SGX manifest is built
            manifest = self.config.project_dir / "bench.manifest.sgx"
            if not manifest.exists():
                print_warning("Gramine-SGX manifest not found. Building it now...")
                try:
                    _ = subprocess.run(
                        ["make", "all", "SGX=1"],
                        cwd=self.config.project_dir,
                        check=True,
                    )
                except subprocess.CalledProcessError:
                    print_error("Failed to build SGX manifest")
                    return False

            # Start server with sudo
            self.config.results_dir.mkdir(parents=True, exist_ok=True)
            log_file = self.config.results_dir / "sgx_server.log"

            print_info("Starting SGX server (this may take 1-2 minutes)...")
            print_info("Note: sudo password may be required")

            with open(log_file, "w") as log:
                self.config.sgx_server_process = subprocess.Popen(
                    [
                        "sudo",
                        "gramine-sgx",
                        "bench",
                        "-cp",
                        "/app/classes",
                        "server.BenchServer",
                        "--port",
                        str(self.config.sgx_server_port),
                    ],
                    cwd=self.config.project_dir,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )

            try:
                if self.wait_for_server(self.config.sgx_server_port, max_attempts=360):
                    print_success(
                        f"Gramine-SGX server started (PID: {self.config.sgx_server_process.pid})"
                    )
                    if self.test_server_health(self.config.sgx_server_port):
                        return True
                    else:
                        print_error(
                            "Gramine-SGX server started but failed health check"
                        )
                        self.stop_sgx_server()
                        return False
                else:
                    print_error("Failed to start Gramine-SGX server")
                    if self.config.sgx_server_process:
                        self.stop_sgx_server()
                    return False
            except KeyboardInterrupt:
                print("\n")
                print_info("SGX server startup interrupted by user")
                if self.config.sgx_server_process:
                    self.stop_sgx_server()
                raise
        except KeyboardInterrupt:
            print("\n")
            print_info("SGX server startup cancelled by user")
            return False

    def stop_sgx_server(self):
        """Stop Gramine-SGX server"""
        if self.config.sgx_server_process is None:
            return

        try:
            print_info(
                f"Stopping Gramine-SGX server (PID: {self.config.sgx_server_process.pid})"
            )

            # Use sudo to kill the process since it was started with sudo
            _ = subprocess.run(
                ["sudo", "kill", str(self.config.sgx_server_process.pid)], check=False
            )

            # Wait up to 15 seconds for graceful shutdown
            try:
                _ = self.config.sgx_server_process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                print_warning("Force killing Gramine-SGX server")
                _ = subprocess.run(
                    ["sudo", "kill", "-9", str(self.config.sgx_server_process.pid)],
                    check=False,
                )
                try:
                    _ = self.config.sgx_server_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass

            print_success("Gramine-SGX server stopped")
            self.config.sgx_server_process = None
            time.sleep(2)  # Wait for port to be released
        except Exception as e:
            print_error(f"Error stopping SGX server: {e}")


# Benchmark runner
class BenchmarkRunner:
    def __init__(self, config: Config, server_manager: ServerManager):
        self.config: Config = config
        self.server_manager: ServerManager = server_manager

    def run_benchmark(
        self, server_type: str, name: str, clients: int, messages: int
    ) -> bool:
        """Run a benchmark scenario"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = self.config.results_dir / server_type
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{name}_{timestamp}.txt"

        # Determine port
        port = (
            self.config.normal_server_port
            if server_type == "normal"
            else self.config.sgx_server_port
        )

        print_header(f"Running [{server_type}]: {name}")
        print_info(f"Clients: {clients}, Messages per client: {messages}")
        print_info(f"Server port: {port}")
        print_info(f"Results will be saved to: {output_file}")

        truststore = self.config.project_dir / "client.truststore"

        # Build command
        cmd = [
            "java",
            "-cp",
            str(self.config.classes_dir),
            "client.BenchClient",
            "--host",
            self.config.server_host,
            "--port",
            str(port),
            "--messages",
            str(messages),
            "--truststore",
            str(truststore),
            "--truststore-password",
            "changeit",
        ]

        if clients > 1:
            cmd.extend(["--load-test", "--clients", str(clients)])

        # Run benchmark
        try:
            with open(output_file, "w") as f:
                result = subprocess.run(
                    cmd,
                    cwd=self.config.project_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                # Write to file and display
                output = result.stdout
                _ = f.write(output)
                print(output)

                if result.returncode == 0:
                    print_success(f"Benchmark completed [{server_type}]: {name}")
                    return True
                else:
                    print_error(f"Benchmark failed [{server_type}]: {name}")
                    return False
        except KeyboardInterrupt:
            print("\n")
            print_info("Benchmark interrupted by user")
            return False
        except Exception as e:
            print_error(f"Error running benchmark: {e}")
            return False

    def run_comparison_benchmark(self, name: str, clients: int, messages: int) -> bool:
        """Run benchmark against both server types"""
        print_header(f"Comparison Benchmark: {name}")

        # Test normal JVM
        print_info("Testing with normal JVM...")
        if not self.server_manager.start_normal_server():
            return False

        time.sleep(2)  # Stabilization time
        normal_result = self.run_benchmark("normal", name, clients, messages)
        self.server_manager.stop_normal_server()
        time.sleep(3)  # Cool-down

        # Test Gramine-SGX
        print_info("Testing with Gramine-SGX...")
        if not self.server_manager.start_sgx_server():
            return False

        time.sleep(2)  # Stabilization time
        sgx_result = self.run_benchmark("sgx", name, clients, messages)
        self.server_manager.stop_sgx_server()
        time.sleep(3)  # Cool-down

        if normal_result and sgx_result:
            print_success(f"Comparison benchmark completed: {name}")
            return True
        else:
            print_error(f"One or both benchmarks failed: {name}")
            return False

    def run_all_benchmarks(self) -> bool:
        """Run all comparison benchmarks"""
        print_header("Running All Comparison Benchmarks: Normal JVM vs Gramine-SGX")

        (self.config.results_dir / "normal").mkdir(parents=True, exist_ok=True)
        (self.config.results_dir / "sgx").mkdir(parents=True, exist_ok=True)
        self.config.comparison_dir.mkdir(parents=True, exist_ok=True)

        # Check dependencies
        if not (self.config.classes_dir / "client" / "BenchClient.class").exists():
            print_error("Classes not found. Please run 'make all' first.")
            return False

        # Warmup
        print_info("Running warmup test with normal JVM...")
        if self.server_manager.start_normal_server():
            _ = self.run_benchmark("normal", "warmup", 1, 10)
            self.server_manager.stop_normal_server()
            time.sleep(3)

        # Benchmark scenarios
        scenarios = [
            ("scenario1_single_client_low", 1, 50),
            ("scenario2_single_client_medium", 1, 200),
            ("scenario3_single_client_high", 1, 500),
            ("scenario4_low_concurrency", 5, 100),
            ("scenario5_medium_concurrency", 10, 100),
            ("scenario6_high_concurrency", 20, 100),
            ("scenario7_very_high_concurrency", 50, 50),
        ]

        for name, clients, messages in scenarios:
            _ = self.run_comparison_benchmark(name, clients, messages)

        print_warning("Starting stress test - this may take a while...")
        _ = self.run_comparison_benchmark("scenario8_stress_test", 100, 100)

        print_header("All Comparison Benchmarks Complete")
        print_success(f"Results saved to: {self.config.results_dir}")

        # Generate comparison report
        reporter = ReportGenerator(self.config)
        reporter.generate_comparison_report()

        return True


# Report generator
class ReportGenerator:
    def __init__(self, config: Config):
        self.config: Config = config

    def extract_metrics(self, file_path: Path) -> dict[str, Optional[float]]:
        """Extract performance metrics from benchmark result file"""
        metrics: dict[str, Optional[float]] = {
            "throughput": None,
            "avg_latency": None,
            "total_time": None,
            "total_messages": None,
        }

        if not file_path.exists():
            return metrics

        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Extract throughput
            match = re.search(r"Throughput:\s+(\d+\.?\d*)", content)
            if match:
                metrics["throughput"] = float(match.group(1))
            else:
                match = re.search(r"(\d+\.?\d*)\s+messages/second", content)
                if match:
                    metrics["throughput"] = float(match.group(1))

            # Extract average latency
            match = re.search(r"Average latency:\s+(\d+\.?\d*)\s+ms", content)
            if match:
                metrics["avg_latency"] = float(match.group(1))

            # Extract total time
            match = re.search(r"Total time:\s+(\d+\.?\d*)\s+ms", content)
            if match:
                metrics["total_time"] = float(match.group(1))

            # Extract total messages
            match = re.search(r"Total messages (?:sent|processed):\s+(\d+)", content)
            if match:
                metrics["total_messages"] = float(match.group(1))

            # Calculate throughput if not found
            if (
                metrics["throughput"] is None
                and metrics["total_time"]
                and metrics["total_messages"]
            ):
                metrics["throughput"] = (metrics["total_messages"] * 1000.0) / metrics[
                    "total_time"
                ]

        except Exception as e:
            print_error(f"Error extracting metrics from {file_path}: {e}")

        return metrics

    def calculate_overhead(
        self, baseline: Optional[float], test: Optional[float], metric_type: str
    ) -> Optional[float]:
        """Calculate overhead percentage"""
        if baseline is None or test is None or baseline == 0:
            return None

        if metric_type == "throughput":
            # Throughput: lower is worse
            return ((baseline - test) / baseline) * 100
        else:
            # Latency/Time: higher is worse
            return ((test - baseline) / baseline) * 100

    def generate_comparison_report(self):
        """Generate comparison report from benchmark results"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.config.comparison_dir / f"comparison_report_{timestamp}.txt"
        csv_file = self.config.comparison_dir / f"comparison_data_{timestamp}.csv"

        print_info("Generating comparison report...")

        # Collect results
        normal_dir = self.config.results_dir / "normal"
        sgx_dir = self.config.results_dir / "sgx"

        results: list[dict[str, float | str | None]] = []

        # Find all normal result files
        if normal_dir.exists():
            for normal_file in sorted(normal_dir.glob("scenario*_*.txt")):
                # Extract scenario name without timestamp
                scenario_base = re.sub(r"_\d{8}_\d{6}$", "", normal_file.stem)
                scenario_name = re.sub(r"^scenario\d+_", "", scenario_base)

                # Find corresponding SGX file
                sgx_files = list(sgx_dir.glob(f"{scenario_base}_*.txt"))
                if sgx_files:
                    sgx_file = sgx_files[0]

                    normal_metrics = self.extract_metrics(normal_file)
                    sgx_metrics = self.extract_metrics(sgx_file)

                    result: dict[str, float | None | str] = {
                        "scenario": scenario_name,
                        "normal_throughput": normal_metrics["throughput"],
                        "sgx_throughput": sgx_metrics["throughput"],
                        "normal_latency": normal_metrics["avg_latency"],
                        "sgx_latency": sgx_metrics["avg_latency"],
                        "normal_time": normal_metrics["total_time"],
                        "sgx_time": sgx_metrics["total_time"],
                    }

                    normal_throughput = result["normal_throughput"]
                    sgx_throughput = result["sgx_throughput"]
                    result["throughput_overhead"] = self.calculate_overhead(
                        normal_throughput
                        if isinstance(normal_throughput, (float, int, type(None)))
                        else None,
                        sgx_throughput
                        if isinstance(sgx_throughput, (float, int, type(None)))
                        else None,
                        "throughput",
                    )

                    normal_latency = result["normal_latency"]
                    sgx_latency = result["sgx_latency"]
                    result["latency_overhead"] = self.calculate_overhead(
                        normal_latency
                        if isinstance(normal_latency, (float, int, type(None)))
                        else None,
                        sgx_latency
                        if isinstance(sgx_latency, (float, int, type(None)))
                        else None,
                        "latency",
                    )

                    normal_time = result["normal_time"]
                    sgx_time = result["sgx_time"]
                    result["time_overhead"] = self.calculate_overhead(
                        normal_time
                        if isinstance(normal_time, (float, int, type(None)))
                        else None,
                        sgx_time
                        if isinstance(sgx_time, (float, int, type(None)))
                        else None,
                        "latency",
                    )

                    results.append(result)

        # Generate text report
        with open(report_file, "w") as f:
            _ = f.write("=" * 50 + "\n")
            _ = f.write("GRAMINE-SGX OVERHEAD ANALYSIS REPORT\n")
            _ = f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            _ = f.write("=" * 50 + "\n\n")

            _ = f.write("This report compares performance between:\n")
            _ = f.write("- Normal JVM (Baseline)\n")
            _ = f.write("- Gramine-SGX (Confidential Computing)\n\n")

            _ = f.write("Overhead is calculated as:\n")
            _ = f.write("- Throughput overhead: (Normal - SGX) / Normal * 100%\n")
            _ = f.write("- Latency/Time overhead: (SGX - Normal) / Normal * 100%\n\n")
            _ = f.write("=" * 50 + "\n\n")

            for result in results:
                scenario = result.get("scenario", "unknown")
                _ = f.write(f"--- {scenario} ---\n")
                _ = f.write(
                    f"{'Metric':<20} | {'Normal JVM':<12} | {'Gramine-SGX':<12} | {'Overhead %':<12}\n"
                )
                _ = f.write(f"{'-' * 20}-+-{'-' * 12}-+-{'-' * 12}-+-{'-' * 12}\n")

                normal_throughput = result.get("normal_throughput")
                sgx_throughput = result.get("sgx_throughput")
                throughput_overhead = result.get("throughput_overhead")
                if (
                    normal_throughput
                    and sgx_throughput
                    and throughput_overhead is not None
                ):
                    _ = f.write(
                        f"{'Throughput (msg/s)':<20} | "
                        + f"{float(normal_throughput):<12.2f} | "
                        + f"{float(sgx_throughput):<12.2f} | "
                        + f"{float(throughput_overhead):+11.2f}%\n"
                    )

                normal_latency = result.get("normal_latency")
                sgx_latency = result.get("sgx_latency")
                latency_overhead = result.get("latency_overhead")
                if normal_latency and sgx_latency and latency_overhead is not None:
                    _ = f.write(
                        f"{'Avg Latency (ms)':<20} | "
                        + f"{float(normal_latency):<12.2f} | "
                        + f"{float(sgx_latency):<12.2f} | "
                        + f"{float(latency_overhead):+11.2f}%\n"
                    )

                normal_time = result.get("normal_time")
                sgx_time = result.get("sgx_time")
                time_overhead = result.get("time_overhead")
                if normal_time and sgx_time and time_overhead is not None:
                    _ = f.write(
                        f"{'Total Time (ms)':<20} | "
                        + f"{float(normal_time):<12.2f} | "
                        + f"{float(sgx_time):<12.2f} | "
                        + f"{float(time_overhead):+11.2f}%\n"
                    )

                _ = f.write("\n")

            _ = f.write("\n" + "=" * 50 + "\n")
            _ = f.write("SUMMARY\n")
            _ = f.write("=" * 50 + "\n\n")
            _ = f.write("Key Findings:\n")
            _ = f.write("- Positive overhead % indicates Gramine-SGX is slower\n")
            _ = f.write(
                "- Negative overhead % indicates Gramine-SGX is faster (rare)\n\n"
            )
            _ = f.write("Raw result files located at:\n")
            _ = f.write(f"- Normal JVM: {self.config.results_dir / 'normal'}\n")
            _ = f.write(f"- Gramine-SGX: {self.config.results_dir / 'sgx'}\n\n")
            _ = f.write("For detailed analysis, examine individual result files.\n\n")

        # Generate CSV report
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "scenario",
                    "normal_throughput",
                    "sgx_throughput",
                    "throughput_overhead",
                    "normal_latency",
                    "sgx_latency",
                    "latency_overhead",
                    "normal_time",
                    "sgx_time",
                    "time_overhead",
                ],
            )
            writer.writeheader()
            writer.writerows(results)

        # Display the report
        with open(report_file, "r") as f:
            print(f.read())

        print_success(f"Comparison report saved to: {report_file}")
        print_success(f"CSV data saved to: {csv_file}")


# Interactive menu
class InteractiveMenu:
    def __init__(
        self,
        config: Config,
        server_manager: ServerManager,
        runner: BenchmarkRunner,
        reporter: ReportGenerator,
    ):
        self.config: Config = config
        self.server_manager: ServerManager = server_manager
        self.runner: BenchmarkRunner = runner
        self.reporter: ReportGenerator = reporter

    def show_menu(self):
        """Display interactive menu"""
        print("\033[2J\033[H")  # Clear screen
        print_header("TLS Benchmark Comparison Tool - Normal JVM vs Gramine-SGX")
        print("1.  Run comparison warmup test")
        print("2.  Run single client comparison (100 messages)")
        print("3.  Run low concurrency comparison (5 clients, 100 messages each)")
        print("4.  Run medium concurrency comparison (10 clients, 100 messages each)")
        print("5.  Run high concurrency comparison (20 clients, 100 messages each)")
        print("6.  Run stress test comparison (50 clients, 200 messages each)")
        print("7.  Run ALL comparison benchmarks")
        print("8.  Test normal JVM server only")
        print("9.  Test Gramine-SGX server only")
        print("10. View results directory")
        print("11. Generate comparison report from existing results")
        print("0.  Exit")
        print()

    def run(self):
        """Run interactive menu"""
        print_info("Press Ctrl+C at any time to exit")
        while True:
            try:
                self.show_menu()
                choice = input("Select option [0-11]: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n")
                print_info("Exiting interactive mode...")
                break

            try:
                if choice == "1":
                    _ = self.runner.run_comparison_benchmark("warmup", 1, 10)

                elif choice == "2":
                    _ = self.runner.run_comparison_benchmark("single_client", 1, 100)

                elif choice == "3":
                    _ = self.runner.run_comparison_benchmark("low_concurrency", 5, 100)

                elif choice == "4":
                    _ = self.runner.run_comparison_benchmark(
                        "medium_concurrency", 10, 100
                    )

                elif choice == "5":
                    _ = self.runner.run_comparison_benchmark(
                        "high_concurrency", 20, 100
                    )

                elif choice == "6":
                    _ = self.runner.run_comparison_benchmark("stress_test", 50, 200)

                elif choice == "7":
                    _ = self.runner.run_all_benchmarks()

                elif choice == "8":
                    print_info("Testing normal JVM only...")
                    if self.server_manager.start_normal_server():
                        _ = self.server_manager.check_server_verbose(
                            self.config.normal_server_port
                        )
                        _ = self.runner.run_benchmark("normal", "test_normal", 1, 50)
                        self.server_manager.stop_normal_server()
                    else:
                        print_error("Failed to start normal JVM server")

                elif choice == "9":
                    print_info("Testing Gramine-SGX server only...")
                    if self.server_manager.start_sgx_server():
                        _ = self.server_manager.check_server_verbose(
                            self.config.sgx_server_port
                        )
                        _ = self.runner.run_benchmark("sgx", "test_sgx", 1, 50)
                        self.server_manager.stop_sgx_server()
                    else:
                        print_error("Failed to start Gramine-SGX server")

                elif choice == "10":
                    print(f"\nResults directory: {self.config.results_dir}")
                    if (self.config.results_dir / "normal").exists():
                        print("\nNormal JVM results:")
                        for f in sorted((self.config.results_dir / "normal").glob("*")):
                            print(f"  {f.name}")
                    if (self.config.results_dir / "sgx").exists():
                        print("\nGramine-SGX results:")
                        for f in sorted((self.config.results_dir / "sgx").glob("*")):
                            print(f"  {f.name}")
                    if self.config.comparison_dir.exists():
                        print("\nComparison reports:")
                        for f in sorted(self.config.comparison_dir.glob("*")):
                            print(f"  {f.name}")

                elif choice == "11":
                    self.reporter.generate_comparison_report()

                elif choice == "0":
                    print_info("Exiting...")
                    break

                else:
                    print_error("Invalid option")
                    time.sleep(1)

            except KeyboardInterrupt:
                print("\n")
                print_info("Operation interrupted, returning to menu...")
                time.sleep(1)
            except Exception as e:
                print_error(f"Error: {e}")
                import traceback

                traceback.print_exc()


# Main function
def main():
    parser = argparse.ArgumentParser(
        description="TLS Benchmark Comparison Tool - Normal JVM vs Gramine-SGX",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  all             Run all comparison benchmarks
  single          Run single client comparison test
  warmup          Run warmup comparison test
  low             Run low concurrency comparison test
  medium          Run medium concurrency comparison test
  high            Run high concurrency comparison test
  stress          Run stress test comparison
  interactive     Run interactive menu (default)
  custom          Run custom comparison benchmark
  normal-only     Test normal JVM only
  sgx-only        Test Gramine-SGX server only
  report          Generate comparison report from existing results

Examples:
  %(prog)s                                    # Interactive mode
  %(prog)s all                                # Run all comparison scenarios
  %(prog)s stress                             # Run stress test comparison
  %(prog)s custom --clients 15 --messages 50  # Custom comparison test
  %(prog)s normal-only                        # Test normal JVM only
  %(prog)s sgx-only                           # Test SGX server only
  %(prog)s report                             # Generate report from existing results

Note: SGX server will be started automatically with sudo.
      You may be prompted for your password.
      Press Ctrl+C to interrupt and cleanup gracefully.
        """,
    )

    _ = parser.add_argument(
        "command",
        nargs="?",
        default="interactive",
        choices=[
            "all",
            "single",
            "warmup",
            "low",
            "medium",
            "high",
            "stress",
            "interactive",
            "custom",
            "normal-only",
            "sgx-only",
            "report",
        ],
        help="Command to execute",
    )
    _ = parser.add_argument("--host", default="localhost", help="Server host")
    _ = parser.add_argument(
        "--normal-port", type=int, default=9443, help="Normal JVM server port"
    )
    _ = parser.add_argument(
        "--sgx-port", type=int, default=9444, help="Gramine-SGX server port"
    )
    _ = parser.add_argument(
        "--clients",
        type=int,
        default=10,
        help="Number of concurrent clients (for custom)",
    )
    _ = parser.add_argument(
        "--messages",
        type=int,
        default=100,
        help="Number of messages per client (for custom)",
    )

    args = parser.parse_args()

    # Create configuration
    config = Config()
    config.server_host = str(args.host)  # pyright: ignore[reportAny]
    config.normal_server_port = int(args.normal_port)  # pyright: ignore[reportAny]
    config.sgx_server_port = int(args.sgx_port)  # pyright: ignore[reportAny]

    # Create components
    server_manager = ServerManager(config)
    runner = BenchmarkRunner(config, server_manager)
    reporter = ReportGenerator(config)
    menu = InteractiveMenu(config, server_manager, runner, reporter)

    # Setup cleanup handler
    def cleanup(signum: int | None = None, frame: Any | None = None) -> None:  # pyright: ignore[reportUnusedParameter, reportExplicitAny]
        print("\n")
        print_info("Received interrupt signal, cleaning up...")
        try:
            server_manager.stop_normal_server()
            server_manager.stop_sgx_server()
        except Exception as e:
            print_error(f"Error during cleanup: {e}")
        finally:
            print_info("Cleanup complete")
            sys.exit(0)

    _ = signal.signal(signal.SIGINT, cleanup)
    _ = signal.signal(signal.SIGTERM, cleanup)

    try:
        # Check dependencies
        if args.command != "report":  # pyright: ignore[reportAny]
            if not (config.classes_dir / "client" / "BenchClient.class").exists():
                print_error("Classes not found. Please run 'make all' first.")
                sys.exit(1)

        # Create results directories
        config.results_dir.mkdir(parents=True, exist_ok=True)
        (config.results_dir / "normal").mkdir(parents=True, exist_ok=True)
        (config.results_dir / "sgx").mkdir(parents=True, exist_ok=True)
        config.comparison_dir.mkdir(parents=True, exist_ok=True)

        # Execute command
        if args.command == "all":
            _ = runner.run_all_benchmarks()

        elif args.command == "single":
            _ = runner.run_comparison_benchmark("single_client", 1, 100)

        elif args.command == "warmup":
            _ = runner.run_comparison_benchmark("warmup", 1, 10)

        elif args.command == "low":
            _ = runner.run_comparison_benchmark("low_concurrency", 5, 100)

        elif args.command == "medium":
            _ = runner.run_comparison_benchmark("medium_concurrency", 10, 100)

        elif args.command == "high":
            _ = runner.run_comparison_benchmark("high_concurrency", 20, 100)

        elif args.command == "stress":
            _ = runner.run_comparison_benchmark("stress_test", 50, 200)

        elif args.command == "custom":
            _ = runner.run_comparison_benchmark("custom", args.clients, args.messages)

        elif args.command == "normal-only":
            if server_manager.start_normal_server():
                _ = runner.run_benchmark("normal", "test_normal", 10, 100)
                server_manager.stop_normal_server()
            else:
                print_error("Failed to start normal JVM server")
                sys.exit(1)

        elif args.command == "sgx-only":
            if server_manager.start_sgx_server():
                _ = runner.run_benchmark("sgx", "test_sgx", 10, 100)
                server_manager.stop_sgx_server()
            else:
                print_error("Failed to start Gramine-SGX server")
                sys.exit(1)

        elif args.command == "report":
            reporter.generate_comparison_report()

        elif args.command == "interactive":
            menu.run()

        cleanup()

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
