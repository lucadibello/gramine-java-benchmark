#!/bin/bash

# Benchmark Test Runner for TLS Server - Normal JVM vs Gramine-SGX Comparison
# This script runs benchmarks against both normal JVM and Gramine-SGX to measure overhead

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CLASSES_DIR="$PROJECT_DIR/target/classes"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
SERVER_HOST="localhost"
NORMAL_SERVER_PORT=9443
SGX_SERVER_PORT=9444
RESULTS_DIR="$PROJECT_DIR/benchmark-results"
COMPARISON_DIR="$RESULTS_DIR/comparison"

# Server process IDs for cleanup
NORMAL_SERVER_PID=""

# Print colored message
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}$1${NC}"
    echo -e "${GREEN}========================================${NC}\n"
}

# Cleanup function to kill servers on exit
cleanup() {
    print_info "Cleaning up server processes..."
    if [ ! -z "$NORMAL_SERVER_PID" ] && kill -0 "$NORMAL_SERVER_PID" 2>/dev/null; then
        print_info "Stopping normal JVM server (PID: $NORMAL_SERVER_PID)"
        kill "$NORMAL_SERVER_PID" 2>/dev/null || true
        wait "$NORMAL_SERVER_PID" 2>/dev/null || true
    fi
    # Note: SGX servers are started manually by user and not automatically cleaned up
}

# Set up cleanup on script exit
trap cleanup EXIT INT TERM

# Check if server is running with proper TLS connection test
check_server() {
    local port="${1:-$NORMAL_SERVER_PORT}"

    # Try to connect using openssl s_client to test TLS connectivity
    if command -v openssl >/dev/null 2>&1; then
        # Test TLS connection, check for successful connection despite self-signed cert
        if timeout 3 openssl s_client -connect "$SERVER_HOST:$port" \
            -verify_return_error </dev/null 2>&1 | grep -q "CONNECTED\|BEGIN CERTIFICATE"; then
            return 0
        else
            return 1
        fi
    elif command -v nc >/dev/null 2>&1; then
        # Try netcat as secondary option
        if timeout 2 nc -z "$SERVER_HOST" "$port" >/dev/null 2>&1; then
            return 0
        else
            return 1
        fi
    else
        # Fallback to Java client test if neither openssl nor nc available
        if [ -f "$CLASSES_DIR/client/BenchClient.class" ] && [ -f "$PROJECT_DIR/client.truststore" ]; then
            if timeout 3 java -cp "$CLASSES_DIR" client.BenchClient \
                --host "$SERVER_HOST" \
                --port "$port" \
                --messages 1 \
                --truststore "$PROJECT_DIR/client.truststore" \
                --truststore-password "changeit" >/dev/null 2>&1; then
                return 0
            else
                return 1
            fi
        else
            print_error "Cannot check server: no suitable tools available (openssl, nc, or compiled client with truststore)"
            return 1
        fi
    fi
}

# Check server with detailed feedback
check_server_verbose() {
    local port="${1:-$NORMAL_SERVER_PORT}"
    print_info "Checking if server is running on $SERVER_HOST:$port..."

    if check_server "$port"; then
        print_success "Server is running and accepting TLS connections"
        return 0
    else
        print_error "Server is not running or not accepting connections on port $port"
        return 1
    fi
}

# Wait for server to start
wait_for_server() {
    local max_attempts=30
    local attempt=1

    print_info "Waiting for server to start..."

    while [ $attempt -le $max_attempts ]; do
        if check_server "$NORMAL_SERVER_PORT"; then
            print_success "Server is ready"
            sleep 2  # Give it extra time to be fully ready
            return 0
        fi

        # Show progress every 5 attempts
        if [ $((attempt % 5)) -eq 0 ]; then
            print_info "Still waiting... (attempt $attempt/$max_attempts)"
        fi

        sleep 1
        attempt=$((attempt + 1))
    done

    print_error "Server did not start within $max_attempts seconds"
    return 1
}

# Test server health with a simple message
test_server_health() {
    print_info "Testing server health..."

    if [ -f "$CLASSES_DIR/client/BenchClient.class" ] && [ -f "$PROJECT_DIR/client.truststore" ]; then
        local port="${1:-$NORMAL_SERVER_PORT}"
        if timeout 5 java -cp "$CLASSES_DIR" client.BenchClient \
            --host "$SERVER_HOST" \
            --port "$port" \
            --messages 3 \
            --truststore "$PROJECT_DIR/client.truststore" \
            --truststore-password "changeit" >/dev/null 2>&1; then
            print_success "Server health check passed"
            return 0
        else
            print_error "Server health check failed"
            return 1
        fi
    else
        print_warning "Cannot perform health check: client classes or truststore not found"
        return 0  # Don't fail if we can't test
    fi
}

# Check for existing server processes
check_existing_server_processes() {
    local existing_pids=""

    # Check for Java BenchServer processes
    if command -v pgrep >/dev/null 2>&1; then
        existing_pids=$(pgrep -f "server.BenchServer" 2>/dev/null || true)
    elif command -v ps >/dev/null 2>&1; then
        existing_pids=$(ps aux | grep "server.BenchServer" | grep -v grep | awk '{print $2}' || true)
    fi

    # Check for Gramine processes
    local gramine_pids=""
    if command -v pgrep >/dev/null 2>&1; then
        gramine_pids=$(pgrep -f "gramine-sgx.*bench" 2>/dev/null || true)
    elif command -v ps >/dev/null 2>&1; then
        gramine_pids=$(ps aux | grep "gramine-sgx.*bench" | grep -v grep | awk '{print $2}' || true)
    fi

    # Combine all PIDs
    local all_pids=""
    if [ ! -z "$existing_pids" ]; then
        all_pids="$existing_pids"
    fi
    if [ ! -z "$gramine_pids" ]; then
        if [ ! -z "$all_pids" ]; then
            all_pids="$all_pids $gramine_pids"
        else
            all_pids="$gramine_pids"
        fi
    fi

    echo "$all_pids"
}


# Start normal JVM server
start_normal_server() {
    print_info "Starting normal JVM server on port $NORMAL_SERVER_PORT..."

    # Check if SGX server is running on the wrong port
    if check_server "$SGX_SERVER_PORT"; then
        print_info "SGX server detected on port $SGX_SERVER_PORT (correct)"
    fi

    # Check if a server is already running on normal port
    if check_server "$NORMAL_SERVER_PORT"; then
        print_warning "A server is already running on port $NORMAL_SERVER_PORT"
        print_info "Attempting to use existing server..."
        if test_server_health "$NORMAL_SERVER_PORT"; then
            print_success "Existing normal JVM server is healthy and will be used"
            return 0
        fi
    fi

    # Check if certificates exist
    if [ ! -f "$PROJECT_DIR/server.keystore" ] || [ ! -f "$PROJECT_DIR/client.truststore" ]; then
        print_info "Generating TLS certificates..."
        cd "$PROJECT_DIR"
        make certs
    fi

    cd "$PROJECT_DIR"
    java -cp "$CLASSES_DIR" server.BenchServer --port "$NORMAL_SERVER_PORT" > "$RESULTS_DIR/normal_server.log" 2>&1 &
    NORMAL_SERVER_PID=$!

    if wait_for_server; then
        print_success "Normal JVM server started (PID: $NORMAL_SERVER_PID)"
        # Additional health check
        if test_server_health "$NORMAL_SERVER_PORT"; then
            return 0
        else
            print_error "Normal JVM server started but failed health check"
            return 1
        fi
    else
        print_error "Failed to start normal JVM server"
        return 1
    fi
}

# Wait for user to start Gramine-SGX server
wait_for_sgx_server() {
    print_header "Gramine-SGX Server Setup Required"

    # Check if a server is already running on SGX port
    if check_server "$SGX_SERVER_PORT"; then
        print_info "A server is already running on port $SGX_SERVER_PORT"
        if test_server_health "$SGX_SERVER_PORT"; then
            print_success "Existing SGX server is healthy and will be used"
            return 0
        else
            print_warning "Existing server exists but failed health check"
            print_info "Please stop the existing server and start a fresh Gramine-SGX server"
        fi
    fi

    # Check if there's a server running on the wrong port (normal JVM port)
    if check_server "$NORMAL_SERVER_PORT"; then
        print_error "Found a server running on port $NORMAL_SERVER_PORT (normal JVM port)"
        print_error "Gramine-SGX server should use port $SGX_SERVER_PORT"
        print_info "Please stop any servers on port $NORMAL_SERVER_PORT and start SGX server on $SGX_SERVER_PORT"
        echo ""
    fi

    # Check if SGX manifest is built
    if [ ! -f "$PROJECT_DIR/bench.manifest.sgx" ]; then
        print_warning "Gramine-SGX manifest not found. Building it now..."
        cd "$PROJECT_DIR"
        make all SGX=1 || {
            print_error "Failed to build SGX manifest"
            return 1
        }
    fi

    echo ""
    print_info "Please start the Gramine-SGX server manually in another terminal:"
    echo ""
    echo "  cd $PROJECT_DIR"
    echo "  gramine-sgx bench -cp /app/classes server.BenchServer --port $SGX_SERVER_PORT"
    echo ""
    print_warning "IMPORTANT: Use port $SGX_SERVER_PORT (NOT $NORMAL_SERVER_PORT)"
    print_warning "Note: Gramine-SGX startup can take 1-2 minutes"
    print_info "Port separation:"
    print_info "  - Normal JVM server: $NORMAL_SERVER_PORT"
    print_info "  - Gramine-SGX server: $SGX_SERVER_PORT"
    echo ""

    # Wait for user confirmation and server availability
    while true; do
        read -p "Press Enter when the Gramine-SGX server is running, or 'q' to quit: " response

        if [ "$response" = "q" ] || [ "$response" = "Q" ]; then
            print_info "Cancelled by user"
            return 1
        fi

        print_info "Checking if Gramine-SGX server is ready on port $SGX_SERVER_PORT..."
        if check_server "$SGX_SERVER_PORT"; then
            if test_server_health "$SGX_SERVER_PORT"; then
                print_success "Gramine-SGX server is running and healthy!"
                return 0
            else
                print_error "Server is running but failed health check"
                print_info "Please check the server logs and try again"
            fi
        else
            print_error "Cannot connect to server on port $SGX_SERVER_PORT"
            print_info "Make sure the server started successfully"
        fi
        echo ""
    done
}

# Stop server
stop_server() {
    local server_type="$1"

    if [ "$server_type" = "normal" ]; then
        local pid_var="$NORMAL_SERVER_PID"

        if [ ! -z "$pid_var" ] && kill -0 "$pid_var" 2>/dev/null; then
            print_info "Stopping $server_type server (PID: $pid_var)"
            kill "$pid_var" 2>/dev/null || true

            # Wait up to 10 seconds for graceful shutdown
            local count=0
            while [ $count -lt 10 ] && kill -0 "$pid_var" 2>/dev/null; do
                sleep 1
                count=$((count + 1))
            done

            # Force kill if still running
            if kill -0 "$pid_var" 2>/dev/null; then
                print_warning "Force killing $server_type server"
                kill -9 "$pid_var" 2>/dev/null || true
            fi

            wait "$pid_var" 2>/dev/null || true
            print_success "$server_type server stopped"
            NORMAL_SERVER_PID=""
        fi

        # Wait for port to be released
        sleep 2
    elif [ "$server_type" = "sgx" ]; then
        print_info "SGX servers are started manually - please stop them manually if needed"
        print_info "You can use: pkill -f 'gramine-sgx.*bench' to stop all SGX benchmark servers"
    fi
}

# Run a benchmark scenario for a specific server type
run_benchmark() {
    local server_type="$1"
    local name="$2"
    local clients="$3"
    local messages="$4"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local output_file="$RESULTS_DIR/${server_type}/${name}_${timestamp}.txt"

    # Determine which port to use based on server type
    local port
    if [ "$server_type" = "normal" ]; then
        port="$NORMAL_SERVER_PORT"
    else
        port="$SGX_SERVER_PORT"
    fi

    print_header "Running [$server_type]: $name"
    print_info "Clients: $clients, Messages per client: $messages"
    print_info "Server port: $port"
    print_info "Results will be saved to: $output_file"

    # Ensure output directory exists
    mkdir -p "$(dirname "$output_file")"

    if [ "$clients" -eq 1 ]; then
        java -cp "$CLASSES_DIR" client.BenchClient \
            --host "$SERVER_HOST" \
            --port "$port" \
            --messages "$messages" \
            --truststore "$PROJECT_DIR/client.truststore" \
            --truststore-password "changeit" \
            2>&1 | tee "$output_file"
    else
        java -cp "$CLASSES_DIR" client.BenchClient \
            --host "$SERVER_HOST" \
            --port "$port" \
            --load-test \
            --clients "$clients" \
            --messages "$messages" \
            --truststore "$PROJECT_DIR/client.truststore" \
            --truststore-password "changeit" \
            2>&1 | tee "$output_file"
    fi

    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        print_success "Benchmark completed [$server_type]: $name"
        return 0
    else
        print_error "Benchmark failed [$server_type]: $name"
        return 1
    fi
}

# Run benchmark scenario against both server types
run_comparison_benchmark() {
    local name="$1"
    local clients="$2"
    local messages="$3"
    local timestamp=$(date +%Y%m%d_%H%M%S)

    print_header "Comparison Benchmark: $name"

    # Test normal JVM
    print_info "Testing with normal JVM..."
    start_normal_server || return 1
    sleep 2  # Stabilization time
    run_benchmark "normal" "$name" "$clients" "$messages"
    local normal_result=$?
    stop_server "normal"

    sleep 3  # Cool-down between tests

    # Test Gramine-SGX
    print_info "Testing with Gramine-SGX..."

    wait_for_sgx_server || return 1

    sleep 2  # Stabilization time
    run_benchmark "sgx" "$name" "$clients" "$messages"
    local sgx_result=$?
    # Note: We don't stop SGX server since it was started manually

    sleep 3  # Cool-down between tests

    if [ $normal_result -eq 0 ] && [ $sgx_result -eq 0 ]; then
        print_success "Comparison benchmark completed: $name"
        return 0
    else
        print_error "One or both benchmarks failed: $name"
        return 1
    fi
}

# Run all comparison benchmarks
run_all_benchmarks() {
    print_header "Running All Comparison Benchmarks: Normal JVM vs Gramine-SGX"

    mkdir -p "$RESULTS_DIR/normal"
    mkdir -p "$RESULTS_DIR/sgx"
    mkdir -p "$COMPARISON_DIR"

    # Check dependencies
    if [ ! -d "$CLASSES_DIR" ] || [ ! -f "$CLASSES_DIR/client/BenchClient.class" ]; then
        print_error "Classes not found. Please run 'make all' first."
        return 1
    fi

    # Warmup (optional, single run)
    print_info "Running warmup test with normal JVM..."
    start_normal_server || return 1
    run_benchmark "normal" "warmup" 1 10 || true
    stop_server "normal"
    sleep 3

    # Benchmark scenarios
    run_comparison_benchmark "scenario1_single_client_low" 1 50
    run_comparison_benchmark "scenario2_single_client_medium" 1 200
    run_comparison_benchmark "scenario3_single_client_high" 1 500
    run_comparison_benchmark "scenario4_low_concurrency" 5 100
    run_comparison_benchmark "scenario5_medium_concurrency" 10 100
    run_comparison_benchmark "scenario6_high_concurrency" 20 100
    run_comparison_benchmark "scenario7_very_high_concurrency" 50 50

    print_warning "Starting stress test - this may take a while..."
    run_comparison_benchmark "scenario8_stress_test" 100 100

    print_header "All Comparison Benchmarks Complete"
    print_success "Results saved to: $RESULTS_DIR"

    # Generate comparison report
    generate_comparison_report
}

# Extract performance metrics from benchmark result file
extract_metrics() {
    local file="$1"
    local throughput=""
    local avg_latency=""
    local total_time=""
    local total_messages=""

    if [ -f "$file" ]; then
        # Try to extract throughput (may not exist for single-client tests)
        throughput=$(grep "Throughput:" "$file" | awk '{print $2}' | head -1)
        if [ -z "$throughput" ]; then
            # Check for messages/second format
            throughput=$(grep "messages/second" "$file" | awk '{print $2}' | head -1)
        fi

        # Extract other metrics
        avg_latency=$(grep "Average latency:" "$file" | awk '{print $3}' | head -1)

        # Try both formats for total time
        total_time=$(grep "Total time:" "$file" | awk '{print $3}' | head -1)
        if [ -z "$total_time" ]; then
            # Check load test format
            total_time=$(grep "Total time:" "$file" | tail -1 | awk '{print $3}' | head -1)
        fi

        # Try both formats for total messages
        total_messages=$(grep "Total messages sent:" "$file" | awk '{print $4}' | head -1)
        if [ -z "$total_messages" ]; then
            # Check load test format
            total_messages=$(grep "Total messages processed:" "$file" | awk '{print $4}' | head -1)
        fi

        # Calculate throughput if not found but we have time and messages
        if [ -z "$throughput" ] && [ ! -z "$total_time" ] && [ ! -z "$total_messages" ]; then
            throughput=$(awk "BEGIN {printf \"%.2f\", ($total_messages * 1000.0 / $total_time)}")
        fi
    fi

    echo "$throughput,$avg_latency,$total_time,$total_messages"
}

# Calculate overhead percentage
calculate_overhead() {
    local normal_val="$1"
    local sgx_val="$2"
    local metric_type="$3"  # "throughput" or "latency"

    "$SCRIPT_DIR/calc_overhead.sh" "$normal_val" "$sgx_val" "$metric_type"
}

# Generate comparison report
generate_comparison_report() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local report_file="$COMPARISON_DIR/comparison_report_${timestamp}.txt"
    local csv_file="$COMPARISON_DIR/comparison_data_${timestamp}.csv"

    print_info "Generating comparison report..."

    # Create detailed text report
    {
        echo "=================================================="
        echo "GRAMINE-SGX OVERHEAD ANALYSIS REPORT"
        echo "Generated: $(date)"
        echo "=================================================="
        echo ""
        echo "This report compares performance between:"
        echo "- Normal JVM (Baseline)"
        echo "- Gramine-SGX (Confidential Computing)"
        echo ""
        echo "Overhead is calculated as:"
        echo "- Throughput overhead: (Normal - SGX) / Normal * 100%"
        echo "- Latency/Time overhead: (SGX - Normal) / Normal * 100%"
        echo ""
        echo "=================================================="
        echo ""

        # Process each scenario
        # Get unique scenario names from normal results
        for normal_file in "$RESULTS_DIR/normal"/scenario*_*.txt; do
            if [ -f "$normal_file" ]; then
                # Extract scenario name without timestamp
                scenario_base=$(basename "$normal_file" .txt | sed 's/_[0-9]\{8\}_[0-9]\{6\}$//')
                scenario_name=$(echo "$scenario_base" | sed 's/^scenario[0-9]*_//')

                # Find corresponding SGX file with same scenario base name
                sgx_file=$(find "$RESULTS_DIR/sgx/" -name "${scenario_base}_*.txt" | head -1)

                if [ -f "$sgx_file" ]; then
                    echo "--- $scenario_name ---"

                    # Extract metrics
                    normal_metrics=$(extract_metrics "$normal_file")
                    sgx_metrics=$(extract_metrics "$sgx_file")

                    IFS=',' read -r normal_throughput normal_latency normal_time normal_messages <<< "$normal_metrics"
                    IFS=',' read -r sgx_throughput sgx_latency sgx_time sgx_messages <<< "$sgx_metrics"

                    printf "%-20s | %-12s | %-12s | %-12s\n" "Metric" "Normal JVM" "Gramine-SGX" "Overhead %"
                    printf "%-20s-+-%-12s-+-%-12s-+-%-12s\n" "--------------------" "------------" "------------" "------------"

                    if [ ! -z "$normal_throughput" ] && [ ! -z "$sgx_throughput" ]; then
                        throughput_overhead=$(calculate_overhead "$normal_throughput" "$sgx_throughput" "throughput")
                        printf "%-20s | %-12s | %-12s | %+11s%%\n" "Throughput (msg/s)" "$normal_throughput" "$sgx_throughput" "$throughput_overhead"
                    fi

                    if [ ! -z "$normal_latency" ] && [ ! -z "$sgx_latency" ]; then
                        latency_overhead=$(calculate_overhead "$normal_latency" "$sgx_latency" "latency")
                        printf "%-20s | %-12s | %-12s | %+11s%%\n" "Avg Latency (ms)" "$normal_latency" "$sgx_latency" "$latency_overhead"
                    fi

                    if [ ! -z "$normal_time" ] && [ ! -z "$sgx_time" ]; then
                        time_overhead=$(calculate_overhead "$normal_time" "$sgx_time" "latency")
                        printf "%-20s | %-12s | %-12s | %+11s%%\n" "Total Time (ms)" "$normal_time" "$sgx_time" "$time_overhead"
                    fi

                    echo ""
                else
                    echo "--- $scenario_name ---"
                    echo "Missing corresponding SGX results for $scenario_name"
                    echo ""
                fi
            fi
        done

        echo ""
        echo "=================================================="
        echo "SUMMARY"
        echo "=================================================="
        echo ""
        echo "Key Findings:"
        echo "- Positive overhead % indicates Gramine-SGX is slower"
        echo "- Negative overhead % indicates Gramine-SGX is faster (rare)"
        echo ""
        echo "Raw result files located at:"
        echo "- Normal JVM: $RESULTS_DIR/normal/"
        echo "- Gramine-SGX: $RESULTS_DIR/sgx/"
        echo ""
        echo "For detailed analysis, examine individual result files."
        echo ""

    } > "$report_file"

    # Create CSV for easy import into spreadsheets
    {
        echo "Scenario,Normal_Throughput,SGX_Throughput,Throughput_Overhead_%,Normal_Latency,SGX_Latency,Latency_Overhead_%,Normal_Time,SGX_Time,Time_Overhead_%"

        # Get unique scenario names from normal results
        for normal_file in "$RESULTS_DIR/normal"/scenario*_*.txt; do
            if [ -f "$normal_file" ]; then
                # Extract scenario name without timestamp
                scenario_base=$(basename "$normal_file" .txt | sed 's/_[0-9]\{8\}_[0-9]\{6\}$//')
                scenario_name=$(echo "$scenario_base" | sed 's/^scenario[0-9]*_//')

                # Find corresponding SGX file with same scenario base name
                sgx_file=$(find "$RESULTS_DIR/sgx/" -name "${scenario_base}_*.txt" | head -1)

                if [ -f "$sgx_file" ]; then
                    normal_metrics=$(extract_metrics "$normal_file")
                    sgx_metrics=$(extract_metrics "$sgx_file")

                    IFS=',' read -r normal_throughput normal_latency normal_time normal_messages <<< "$normal_metrics"
                    IFS=',' read -r sgx_throughput sgx_latency sgx_time sgx_messages <<< "$sgx_metrics"

                    throughput_overhead=$(calculate_overhead "$normal_throughput" "$sgx_throughput" "throughput")
                    latency_overhead=$(calculate_overhead "$normal_latency" "$sgx_latency" "latency")
                    time_overhead=$(calculate_overhead "$normal_time" "$sgx_time" "latency")

                    echo "$scenario_name,$normal_throughput,$sgx_throughput,$throughput_overhead,$normal_latency,$sgx_latency,$latency_overhead,$normal_time,$sgx_time,$time_overhead"
                fi
            fi
        done
    } > "$csv_file"

    # Display the report
    cat "$report_file"

    print_success "Comparison report saved to: $report_file"
    print_success "CSV data saved to: $csv_file"
}

# Interactive menu
show_menu() {
    clear
    print_header "TLS Benchmark Comparison Tool - Normal JVM vs Gramine-SGX"
    echo "1. Run comparison warmup test"
    echo "2. Run single client comparison (100 messages)"
    echo "3. Run low concurrency comparison (5 clients, 100 messages each)"
    echo "4. Run medium concurrency comparison (10 clients, 100 messages each)"
    echo "5. Run high concurrency comparison (20 clients, 100 messages each)"
    echo "6. Run stress test comparison (50 clients, 200 messages each)"
    echo "7. Run ALL comparison benchmarks"
    echo "8. Test normal JVM server only"
    echo "9. Test with manual Gramine-SGX server"
    echo "10. View results directory"
    echo "11. Generate comparison report from existing results"
    echo "0. Exit"
    echo ""
}

# Interactive mode
interactive_mode() {
    while true; do
        show_menu
        read -p "Select option [0-11]: " choice

        case $choice in
            1)
                run_comparison_benchmark "warmup" 1 10
                read -p "Press Enter to continue..."
                ;;
            2)
                run_comparison_benchmark "single_client" 1 100
                read -p "Press Enter to continue..."
                ;;
            3)
                run_comparison_benchmark "low_concurrency" 5 100
                read -p "Press Enter to continue..."
                ;;
            4)
                run_comparison_benchmark "medium_concurrency" 10 100
                read -p "Press Enter to continue..."
                ;;
            5)
                run_comparison_benchmark "high_concurrency" 20 100
                read -p "Press Enter to continue..."
                ;;
            6)
                run_comparison_benchmark "stress_test" 50 200
                read -p "Press Enter to continue..."
                ;;
            7)
                run_all_benchmarks
                read -p "Press Enter to continue..."
                ;;
            8)
                print_info "Testing normal JVM only..."
                if start_normal_server; then
                    check_server_verbose
                    run_benchmark "normal" "test_normal" 1 50
                    stop_server "normal"
                else
                    print_error "Failed to start normal JVM server"
                fi
                read -p "Press Enter to continue..."
                ;;
            9)
                print_info "Testing with manual Gramine-SGX server..."
                if wait_for_sgx_server; then
                    check_server_verbose "$SGX_SERVER_PORT"
                    run_benchmark "sgx" "test_sgx" 1 50
                    print_info "Note: Gramine-SGX server left running (started manually)"
                else
                    print_error "Gramine-SGX server not available"
                fi
                read -p "Press Enter to continue..."
                ;;
            10)
                ls -lh "$RESULTS_DIR"
                echo ""
                echo "Normal JVM results:"
                ls -lh "$RESULTS_DIR/normal/" 2>/dev/null || echo "No normal JVM results found"
                echo ""
                echo "Gramine-SGX results:"
                ls -lh "$RESULTS_DIR/sgx/" 2>/dev/null || echo "No Gramine-SGX results found"
                echo ""
                echo "Comparison reports:"
                ls -lh "$COMPARISON_DIR/" 2>/dev/null || echo "No comparison reports found"
                read -p "Press Enter to continue..."
                ;;
            11)
                generate_comparison_report
                read -p "Press Enter to continue..."
                ;;
            0)
                print_info "Exiting..."
                exit 0
                ;;
            *)
                print_error "Invalid option"
                sleep 1
                ;;
        esac
    done
}

# Print usage
print_usage() {
    cat << EOF
Usage: $0 [OPTIONS] [COMMAND]

Commands:
  all             Run all comparison benchmarks (Normal JVM vs Gramine-SGX)
  single          Run single client comparison test
  warmup          Run warmup comparison test
  low             Run low concurrency comparison test
  medium          Run medium concurrency comparison test
  high            Run high concurrency comparison test
  stress          Run stress test comparison
  interactive     Run interactive menu (default)
  custom          Run custom comparison benchmark
  normal-only     Test normal JVM only
  sgx-only        Test with manual Gramine-SGX server
  report          Generate comparison report from existing results

Options:
  --host <host>           Server host (default: localhost)
  --normal-port <port>    Normal JVM server port (default: 8443)
  --sgx-port <port>       Gramine-SGX server port (default: 8444)
  --clients <n>           Number of concurrent clients (for custom)
  --messages <n>          Number of messages per client (for custom)
  --help                  Show this help message

Examples:
  $0                                    # Interactive mode
  $0 all                                # Run all comparison scenarios
  $0 stress                             # Run stress test comparison
  $0 custom --clients 15 --messages 50  # Custom comparison test
  $0 normal-only                        # Test normal JVM only
  $0 sgx-only                           # Test with manual SGX server
  $0 report                             # Generate report from existing results

Results:
  - Raw results: $RESULTS_DIR/{normal,sgx}/
  - Comparison reports: $COMPARISON_DIR/

Note: For SGX testing, you must manually start the Gramine-SGX server:
  cd $PROJECT_DIR && gramine-sgx bench -cp /app/classes server.BenchServer --port $SGX_SERVER_PORT

Port Configuration:
  - Normal JVM server: $NORMAL_SERVER_PORT (started automatically)
  - Gramine-SGX server: $SGX_SERVER_PORT (started manually)

IMPORTANT: Always ensure SGX server uses port $SGX_SERVER_PORT to avoid conflicts!

EOF
}

# Main script
main() {
    # Parse command line arguments
    COMMAND="interactive"
    CUSTOM_CLIENTS=10
    CUSTOM_MESSAGES=100

    while [[ $# -gt 0 ]]; do
        case $1 in
            --host)
                SERVER_HOST="$2"
                shift 2
                ;;
            --normal-port)
                NORMAL_SERVER_PORT="$2"
                shift 2
                ;;
            --sgx-port)
                SGX_SERVER_PORT="$2"
                shift 2
                ;;
            --clients)
                CUSTOM_CLIENTS="$2"
                shift 2
                ;;
            --messages)
                CUSTOM_MESSAGES="$2"
                shift 2
                ;;
            --help|-h)
                print_usage
                exit 0
                ;;
            all|single|warmup|low|medium|high|stress|interactive|custom|normal-only|sgx-only|report)
                COMMAND="$1"
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                print_usage
                exit 1
                ;;
        esac
    done

    # Check if classes are compiled
    if [ "$COMMAND" != "report" ]; then
        if [ ! -d "$CLASSES_DIR" ] || [ ! -f "$CLASSES_DIR/client/BenchClient.class" ]; then
            print_error "Classes not found. Please run 'make all' first."
            exit 1
        fi
    fi

    # Create results directories
    mkdir -p "$RESULTS_DIR"
    mkdir -p "$RESULTS_DIR/normal"
    mkdir -p "$RESULTS_DIR/sgx"
    mkdir -p "$COMPARISON_DIR"

    # Execute command
    case $COMMAND in
        all)
            run_all_benchmarks
            ;;
        single)
            run_comparison_benchmark "single_client" 1 100
            ;;
        warmup)
            run_comparison_benchmark "warmup" 1 10
            ;;
        low)
            run_comparison_benchmark "low_concurrency" 5 100
            ;;
        medium)
            run_comparison_benchmark "medium_concurrency" 10 100
            ;;
        high)
            run_comparison_benchmark "high_concurrency" 20 100
            ;;
        stress)
            run_comparison_benchmark "stress_test" 50 200
            ;;
        custom)
            run_comparison_benchmark "custom" "$CUSTOM_CLIENTS" "$CUSTOM_MESSAGES"
            ;;
        normal-only)
            if start_normal_server; then
                run_benchmark "normal" "test_normal" 10 100
                stop_server "normal"
            else
                print_error "Failed to start normal JVM server"
                exit 1
            fi
            ;;
        sgx-only)
            if wait_for_sgx_server; then
                run_benchmark "sgx" "test_sgx" 10 100
                print_info "Note: Gramine-SGX server left running (started manually)"
            else
                print_error "Gramine-SGX server not available"
                exit 1
            fi
            ;;
        report)
            generate_comparison_report
            ;;
        interactive)
            interactive_mode
            ;;
        *)
            print_error "Unknown command: $COMMAND"
            print_usage
            exit 1
            ;;
    esac
}

# Run main
main "$@"
