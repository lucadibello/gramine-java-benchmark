#!/bin/bash

# Benchmark Test Runner for TLS Server
# This script runs various benchmark scenarios to test the TLS server performance

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
SERVER_PORT=8443
RESULTS_DIR="$PROJECT_DIR/benchmark-results"

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

# Check if server is running
check_server() {
    print_info "Checking if server is running on $SERVER_HOST:$SERVER_PORT..."
    if timeout 2 bash -c "echo > /dev/tcp/$SERVER_HOST/$SERVER_PORT" 2>/dev/null; then
        print_success "Server is running"
        return 0
    else
        print_error "Server is not running on port $SERVER_PORT"
        return 1
    fi
}

# Wait for server to start
wait_for_server() {
    local max_attempts=30
    local attempt=1

    print_info "Waiting for server to start..."

    while [ $attempt -le $max_attempts ]; do
        if timeout 1 bash -c "echo > /dev/tcp/$SERVER_HOST/$SERVER_PORT" 2>/dev/null; then
            print_success "Server is ready"
            sleep 2  # Give it extra time to be fully ready
            return 0
        fi
        sleep 1
        attempt=$((attempt + 1))
    done

    print_error "Server did not start within $max_attempts seconds"
    return 1
}

# Run a benchmark scenario
run_benchmark() {
    local name="$1"
    local clients="$2"
    local messages="$3"
    local output_file="$RESULTS_DIR/${name}_$(date +%Y%m%d_%H%M%S).txt"

    print_header "Running: $name"
    print_info "Clients: $clients, Messages per client: $messages"
    print_info "Results will be saved to: $output_file"

    if [ "$clients" -eq 1 ]; then
        java -cp "$CLASSES_DIR" client.BenchClient \
            --host "$SERVER_HOST" \
            --port "$SERVER_PORT" \
            --messages "$messages" \
            2>&1 | tee "$output_file"
    else
        java -cp "$CLASSES_DIR" client.BenchClient \
            --host "$SERVER_HOST" \
            --port "$SERVER_PORT" \
            --load-test \
            --clients "$clients" \
            --messages "$messages" \
            2>&1 | tee "$output_file"
    fi

    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        print_success "Benchmark completed: $name"
    else
        print_error "Benchmark failed: $name"
        return 1
    fi
}

# Run all benchmark scenarios
run_all_benchmarks() {
    print_header "Running All Benchmark Scenarios"

    mkdir -p "$RESULTS_DIR"

    # Warmup
    print_info "Running warmup..."
    run_benchmark "warmup" 1 10 || true
    sleep 2

    # Scenario 1: Single client, low volume
    run_benchmark "scenario1_single_client_low" 1 50
    sleep 2

    # Scenario 2: Single client, medium volume
    run_benchmark "scenario2_single_client_medium" 1 200
    sleep 2

    # Scenario 3: Single client, high volume
    run_benchmark "scenario3_single_client_high" 1 500
    sleep 2

    # Scenario 4: Low concurrency
    run_benchmark "scenario4_low_concurrency" 5 100
    sleep 2

    # Scenario 5: Medium concurrency
    run_benchmark "scenario5_medium_concurrency" 10 100
    sleep 2

    # Scenario 6: High concurrency
    run_benchmark "scenario6_high_concurrency" 20 100
    sleep 2

    # Scenario 7: Very high concurrency
    run_benchmark "scenario7_very_high_concurrency" 50 50
    sleep 2

    # Scenario 8: Stress test
    print_warning "Starting stress test - this may take a while..."
    run_benchmark "scenario8_stress_test" 100 100

    print_header "All Benchmarks Complete"
    print_success "Results saved to: $RESULTS_DIR"

    # Generate summary
    generate_summary
}

# Generate summary report
generate_summary() {
    local summary_file="$RESULTS_DIR/summary_$(date +%Y%m%d_%H%M%S).txt"

    print_info "Generating summary report..."

    {
        echo "========================================="
        echo "Benchmark Summary Report"
        echo "Generated: $(date)"
        echo "========================================="
        echo ""

        for result_file in "$RESULTS_DIR"/scenario*.txt; do
            if [ -f "$result_file" ]; then
                echo "--- $(basename "$result_file") ---"
                grep -E "(Total messages|Average latency|Throughput|Total time)" "$result_file" 2>/dev/null || echo "No statistics found"
                echo ""
            fi
        done
    } > "$summary_file"

    cat "$summary_file"
    print_success "Summary saved to: $summary_file"
}

# Interactive menu
show_menu() {
    clear
    print_header "TLS Benchmark Test Runner"
    echo "1. Run warmup test"
    echo "2. Run single client test (100 messages)"
    echo "3. Run low concurrency test (5 clients, 100 messages each)"
    echo "4. Run medium concurrency test (10 clients, 100 messages each)"
    echo "5. Run high concurrency test (20 clients, 100 messages each)"
    echo "6. Run stress test (50 clients, 200 messages each)"
    echo "7. Run ALL benchmark scenarios"
    echo "8. Check server status"
    echo "9. View results directory"
    echo "0. Exit"
    echo ""
}

# Interactive mode
interactive_mode() {
    while true; do
        show_menu
        read -p "Select option [0-9]: " choice

        case $choice in
            1)
                run_benchmark "warmup" 1 10
                read -p "Press Enter to continue..."
                ;;
            2)
                run_benchmark "single_client" 1 100
                read -p "Press Enter to continue..."
                ;;
            3)
                run_benchmark "low_concurrency" 5 100
                read -p "Press Enter to continue..."
                ;;
            4)
                run_benchmark "medium_concurrency" 10 100
                read -p "Press Enter to continue..."
                ;;
            5)
                run_benchmark "high_concurrency" 20 100
                read -p "Press Enter to continue..."
                ;;
            6)
                run_benchmark "stress_test" 50 200
                read -p "Press Enter to continue..."
                ;;
            7)
                run_all_benchmarks
                read -p "Press Enter to continue..."
                ;;
            8)
                check_server
                read -p "Press Enter to continue..."
                ;;
            9)
                ls -lh "$RESULTS_DIR"
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
  all             Run all benchmark scenarios
  single          Run single client test
  warmup          Run warmup test
  low             Run low concurrency test
  medium          Run medium concurrency test
  high            Run high concurrency test
  stress          Run stress test
  interactive     Run interactive menu (default)
  custom          Run custom benchmark

Options:
  --host <host>           Server host (default: localhost)
  --port <port>           Server port (default: 8443)
  --clients <n>           Number of concurrent clients (for custom)
  --messages <n>          Number of messages per client (for custom)
  --wait-server           Wait for server to start before running
  --help                  Show this help message

Examples:
  $0                                    # Interactive mode
  $0 all                                # Run all scenarios
  $0 stress                             # Run stress test
  $0 --wait-server all                  # Wait for server, then run all
  $0 custom --clients 15 --messages 50  # Custom test

EOF
}

# Main script
main() {
    # Parse command line arguments
    WAIT_FOR_SERVER=false
    COMMAND="interactive"
    CUSTOM_CLIENTS=10
    CUSTOM_MESSAGES=100

    while [[ $# -gt 0 ]]; do
        case $1 in
            --host)
                SERVER_HOST="$2"
                shift 2
                ;;
            --port)
                SERVER_PORT="$2"
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
            --wait-server)
                WAIT_FOR_SERVER=true
                shift
                ;;
            --help|-h)
                print_usage
                exit 0
                ;;
            all|single|warmup|low|medium|high|stress|interactive|custom)
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
    if [ ! -d "$CLASSES_DIR" ] || [ ! -f "$CLASSES_DIR/client/BenchClient.class" ]; then
        print_error "Classes not found. Please run 'make all' first."
        exit 1
    fi

    # Wait for server if requested
    if [ "$WAIT_FOR_SERVER" = true ]; then
        wait_for_server || exit 1
    fi

    # Create results directory
    mkdir -p "$RESULTS_DIR"

    # Execute command
    case $COMMAND in
        all)
            check_server || exit 1
            run_all_benchmarks
            ;;
        single)
            check_server || exit 1
            run_benchmark "single_client" 1 100
            ;;
        warmup)
            check_server || exit 1
            run_benchmark "warmup" 1 10
            ;;
        low)
            check_server || exit 1
            run_benchmark "low_concurrency" 5 100
            ;;
        medium)
            check_server || exit 1
            run_benchmark "medium_concurrency" 10 100
            ;;
        high)
            check_server || exit 1
            run_benchmark "high_concurrency" 20 100
            ;;
        stress)
            check_server || exit 1
            run_benchmark "stress_test" 50 200
            ;;
        custom)
            check_server || exit 1
            run_benchmark "custom" "$CUSTOM_CLIENTS" "$CUSTOM_MESSAGES"
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
