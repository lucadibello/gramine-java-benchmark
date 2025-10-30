package com.benchmark.gramine.host;

import com.benchmark.gramine.common.AggregationService;

import java.util.Arrays;

public final class BenchClient {

    private static final String DEFAULT_HOST = "localhost";
    private static final int DEFAULT_PORT = 8443;
    private static final String DEFAULT_TRUSTSTORE = "client.truststore";
    private static final String DEFAULT_PASSWORD = "changeit";

    private static final String ENV_SIGMA = "GRAMINE_BENCH_SIGMA";
    private static final String ENV_WEAK_THREADS = "GRAMINE_BENCH_WEAK_SCALES";
    private static final String ENV_STRONG_THREADS = "GRAMINE_BENCH_STRONG_SCALES";
    private static final String ENV_NATIVE_PARALLELISM = "GRAMINE_BENCH_NATIVE_PARALLELISM";
    private static final String ENV_EXECUTION_MODE = "GRAMINE_BENCH_EXECUTION_MODE";

    private BenchClient() {
    }

    public static void main(String[] args) {
        String host = DEFAULT_HOST;
        int port = DEFAULT_PORT;
        String truststorePath = DEFAULT_TRUSTSTORE;
        String truststorePassword = DEFAULT_PASSWORD;
        Double sigmaOverride = null;
        int[] weakThreadOverride = null;
        int[] strongThreadOverride = null;
        Integer nativeParallelismOverride = null;

        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--host":
                case "-h":
                    if (i + 1 < args.length) {
                        host = args[++i];
                    } else {
                        exitUsage("Missing value for --host");
                    }
                    break;
                case "--port":
                case "-p":
                    if (i + 1 < args.length) {
                        port = Integer.parseInt(args[++i]);
                    } else {
                        exitUsage("Missing value for --port");
                    }
                    break;
                case "--truststore":
                case "-t":
                    if (i + 1 < args.length) {
                        truststorePath = args[++i];
                    } else {
                        exitUsage("Missing value for --truststore");
                    }
                    break;
                case "--password":
                case "-pw":
                    if (i + 1 < args.length) {
                        truststorePassword = args[++i];
                    } else {
                        exitUsage("Missing value for --password");
                    }
                    break;
                case "--sigma":
                    if (i + 1 < args.length) {
                        sigmaOverride = Double.parseDouble(args[++i]);
                    } else {
                        exitUsage("Missing value for --sigma");
                    }
                    break;
                case "--weak":
                    if (i + 1 < args.length) {
                        weakThreadOverride = parseThreadArray(args[++i]);
                    } else {
                        exitUsage("Missing value for --weak");
                    }
                    break;
                case "--strong":
                    if (i + 1 < args.length) {
                        strongThreadOverride = parseThreadArray(args[++i]);
                    } else {
                        exitUsage("Missing value for --strong");
                    }
                    break;
                case "--max-native":
                    if (i + 1 < args.length) {
                        nativeParallelismOverride = Integer.parseInt(args[++i]);
                    } else {
                        exitUsage("Missing value for --max-native");
                    }
                    break;
                case "--help":
                    printUsage();
                    return;
                default:
                    exitUsage("Unrecognised argument: " + args[i]);
            }
        }

        double sigma = sigmaOverride != null ? sigmaOverride : resolveSigma();
        int[] weakThreadCounts = weakThreadOverride != null ? weakThreadOverride
            : resolveThreadArray(ENV_WEAK_THREADS, new int[]{1, 2, 4, 8, 16, 32});
        int[] strongThreadCounts = strongThreadOverride != null ? strongThreadOverride
            : resolveThreadArray(ENV_STRONG_THREADS, new int[]{1, 2, 4, 8, 16, 32});
        int baselineThreads = Math.max(1, Math.min(
            Arrays.stream(weakThreadCounts).min().orElse(Integer.MAX_VALUE),
            Arrays.stream(strongThreadCounts).min().orElse(Integer.MAX_VALUE)));
        int nativeParallelism = nativeParallelismOverride != null ? nativeParallelismOverride
            : resolveNativeParallelism();

        try (AggregationService service = new TlsAggregationClient(host, port, truststorePath, truststorePassword);
            BenchmarkRunner runner = new BenchmarkRunner(service, nativeParallelism)) {
            BenchmarkRunner.WorkloadSettings workloadSettings =
                BenchmarkRunner.WorkloadSettings.fromEnvironment(sigma);
            BenchmarkRunner.Workload workload =
                runner.prepareWorkload(workloadSettings, baselineThreads);
            var weakResults = runner.runWeakScaling(workload, weakThreadCounts);
            var strongResults = runner.runStrongScaling(workload, strongThreadCounts);

            BenchmarkRunner.BenchmarkSummary summary =
                new BenchmarkRunner.BenchmarkSummary(workloadSettings, workload,
                    weakThreadCounts, weakResults, strongThreadCounts, strongResults, nativeParallelism);

            System.out.println("== Benchmark Summary ==");
            System.out.println(summary.toPrettyString());
            System.out.println();
        }
    }

    private static int[] parseThreadArray(String raw) {
        if (raw == null || raw.isEmpty()) {
            throw new IllegalArgumentException("Thread array cannot be empty");
        }
        String[] tokens = raw.split(",");
        int[] values = new int[tokens.length];
        for (int i = 0; i < tokens.length; i++) {
            String token = tokens[i].trim();
            if (token.isEmpty()) {
                throw new IllegalArgumentException("Empty thread token in '" + raw + "'");
            }
            values[i] = Integer.parseInt(token);
            if (values[i] <= 0) {
                throw new IllegalArgumentException("Thread counts must be positive: " + raw);
            }
        }
        return values;
    }

    private static int[] resolveThreadArray(String envKey, int[] defaults) {
        String raw = System.getenv(envKey);
        if (raw == null || raw.isEmpty()) {
            return defaults;
        }
        return parseThreadArray(raw);
    }

    private static double resolveSigma() {
        String raw = System.getenv(ENV_SIGMA);
        if (raw == null || raw.isEmpty()) {
            return 0.5;
        }
        try {
            return Double.parseDouble(raw.trim());
        } catch (NumberFormatException nfe) {
            throw new IllegalArgumentException("Unable to parse sigma from " + ENV_SIGMA + "=" + raw, nfe);
        }
    }

    private static int resolveNativeParallelism() {
        String raw = System.getenv(ENV_NATIVE_PARALLELISM);
        int defaultValue = Integer.MAX_VALUE;
        if (raw == null || raw.isEmpty()) {
            return defaultValue;
        }
        try {
            int value = Integer.parseInt(raw.trim());
            if (value <= 0) {
                return defaultValue;
            }
            return value;
        } catch (NumberFormatException nfe) {
            throw new IllegalArgumentException("Unable to parse " + ENV_NATIVE_PARALLELISM + "=" + raw, nfe);
        }
    }

    private static void exitUsage(String message) {
        System.err.println(message);
        printUsage();
        System.exit(1);
    }

    private static void printUsage() {
        System.out.println("Usage: java com.benchmark.gramine.host.BenchClient [options]");
        System.out.println("  -h, --host <host>           Benchmark server host (default: localhost)");
        System.out.println("  -p, --port <port>           Benchmark server port (default: 8443)");
        System.out.println("  -t, --truststore <path>     Path to truststore file (default: client.truststore)");
        System.out.println("  -pw, --password <password>  Truststore password (default: changeit)");
        System.out.println("  --sigma <value>             Override sigma (default from " + ENV_SIGMA + " or 0.5)");
        System.out.println("  --weak <a,b,c>              Comma-separated weak scaling thread counts");
        System.out.println("  --strong <a,b,c>            Comma-separated strong scaling thread counts");
        System.out.println("  --max-native <value>        Cap on native parallelism (default from " + ENV_NATIVE_PARALLELISM + ")");
        System.out.println("  --mode <name>               Execution mode descriptor (default from " + ENV_EXECUTION_MODE + ")");
        System.out.println("  --help                      Show this help message");
    }
}
