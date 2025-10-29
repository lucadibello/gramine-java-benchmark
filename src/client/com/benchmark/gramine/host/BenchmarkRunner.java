package com.benchmark.gramine.host;

import com.benchmark.gramine.common.AggregationService;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Random;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

final class BenchmarkRunner {

    private static final double NANOS_IN_MILLI = 1_000_000.0;

    private final AggregationService service;
    private final Random random;
    private final int maxNativeParallelism;

    BenchmarkRunner(AggregationService service) {
        this(service, new Random(0L));
    }

    BenchmarkRunner(AggregationService service, int maxNativeParallelism) {
        this(service, new Random(0L), maxNativeParallelism);
    }

    BenchmarkRunner(AggregationService service, Random random) {
        this(service, random, Integer.MAX_VALUE);
    }

    BenchmarkRunner(AggregationService service, Random random, int maxNativeParallelism) {
        this.service = service;
        this.random = random;
        this.maxNativeParallelism = maxNativeParallelism <= 0 ? Integer.MAX_VALUE : maxNativeParallelism;
    }

    int getMaxNativeParallelism() {
        return maxNativeParallelism;
    }

    Workload prepareWorkload(WorkloadSettings settings, int threadCount) {
        int dataSize = Math.max(1, settings.getDataSize());
        int executedThreads = Math.max(1, Math.min(threadCount, maxNativeParallelism));
        double[] dataset = createDataset(dataSize);
        double averageMillis = measureAverageMillis(dataset, settings.getSigma(), settings.getWarmupIterations(),
            settings.getMeasureIterations(), executedThreads);
        return new Workload(dataSize, settings.getSigma(), settings.getWarmupIterations(),
            settings.getMeasureIterations(), averageMillis, threadCount, executedThreads);
    }

    List<WeakScalingResult> runWeakScaling(Workload workload, int[] threadCounts) {
        int[] counts = Arrays.copyOf(threadCounts, threadCounts.length);
        Arrays.sort(counts);
        List<WeakScalingResult> results = new ArrayList<>(counts.length);
        double perThreadWorkload = Math.max(1.0, (double) workload.getDataSize() / workload.getExecutedThreads());
        for (int threads : counts) {
            int executedThreads = Math.max(1, Math.min(threads, maxNativeParallelism));
            int dataSize = Math.max(1, (int) Math.round(perThreadWorkload * executedThreads));
            double[] dataset = createDataset(dataSize);
            double averageMillis = measureAverageMillis(dataset, workload.getSigma(), workload.getWarmupIterations(),
                workload.getMeasureIterations(), executedThreads);
            results.add(new WeakScalingResult(threads, executedThreads, dataSize, workload.getMeasureIterations(), averageMillis));
        }
        return results;
    }

    List<StrongScalingResult> runStrongScaling(Workload workload, int[] threadCounts) {
        int[] counts = Arrays.copyOf(threadCounts, threadCounts.length);
        Arrays.sort(counts);
        int totalSize = workload.getDataSize();
        double[] baseDataset = createDataset(totalSize);

        List<StrongScalingResult> results = new ArrayList<>(counts.length);
        for (int threads : counts) {
            int executedThreads = Math.max(1, Math.min(threads, maxNativeParallelism));
            double averageMillis = measureAverageMillis(baseDataset, workload.getSigma(), workload.getWarmupIterations(),
                workload.getMeasureIterations(), executedThreads);
            results.add(new StrongScalingResult(threads, executedThreads, totalSize, workload.getMeasureIterations(), averageMillis));
        }
        return results;
    }

    private double measureAverageMillis(double[] dataset, double sigma, int warmupIterations,
                                        int measureIterations, int threadCount) {
        if (warmupIterations > 0) {
            double[] warmupCopy = Arrays.copyOf(dataset, dataset.length);
            executeIterations(warmupCopy, sigma, warmupIterations, threadCount);
        }
        double[] measureCopy = Arrays.copyOf(dataset, dataset.length);
        return executeIterations(measureCopy, sigma, measureIterations, threadCount);
    }

    private double executeIterations(double[] dataset, double sigma, int iterations, int threadCount) {
        long start = System.nanoTime();
        double lastResult = 0.0;
        for (int i = 0; i < iterations; i++) {
            lastResult = runDataset(dataset, sigma, threadCount);
        }
        long duration = System.nanoTime() - start;
        double averageMillis = duration / (iterations * NANOS_IN_MILLI);
        if (Double.isNaN(lastResult)) {
            throw new IllegalStateException("Computation produced NaN");
        }
        return averageMillis;
    }

    private double[] createDataset(int size) {
        double[] data = new double[size];
        for (int i = 0; i < size; i++) {
            data[i] = i + 1;
        }
        return data;
    }

    private void perturbDataset(double[] dataset) {
        for (int i = 0; i < dataset.length; i++) {
            dataset[i] += random.nextGaussian() * 0.001;
        }
    }

    private double runDataset(double[] dataset, double sigma, int threadCount) {
        int effectiveThreads = Math.max(1, Math.min(threadCount, maxNativeParallelism));
        service.initBinaryAggregation(dataset.length, sigma);
        int chunkSize = Math.max(1, (dataset.length + effectiveThreads - 1) / effectiveThreads);
        List<Future<?>> futures = new ArrayList<>(effectiveThreads);
        ExecutorService executor = createExecutor(effectiveThreads);
        try {
            for (int t = 0; t < effectiveThreads; t++) {
                int start = t * chunkSize;
                int end = Math.min(dataset.length, start + chunkSize);
                if (start >= end) {
                    break;
                }
                final int sliceStart = start;
                final int sliceEnd = end;
                futures.add(executor.submit(() -> {
                    for (int idx = sliceStart; idx < sliceEnd; idx++) {
                        service.addToBinaryAggregation(dataset[idx]);
                    }
                }));
            }

            Throwable failure = null;
            for (Future<?> future : futures) {
                try {
                    future.get();
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    cancelFutures(futures);
                    throw new IllegalStateException("Benchmark interrupted", ie);
                } catch (ExecutionException ee) {
                    failure = ee.getCause() == null ? ee : ee.getCause();
                    cancelFutures(futures);
                    break;
                }
            }

            if (failure != null) {
                if (failure instanceof RuntimeException) {
                    throw (RuntimeException) failure;
                }
                throw new IllegalStateException("Worker thread failed", failure);
            }

            double total = service.getBinaryAggregationSum();
            perturbDataset(dataset);
            if (Double.isNaN(total)) {
                throw new IllegalStateException("Aggregation sum produced NaN");
            }
            return total;
        } finally {
            // await termination of executor
            try {
                executor.shutdown();
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                }
            } catch (InterruptedException ie) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }

    private ExecutorService createExecutor(int nativeParallelism) {
        ThreadFactory threadFactory = new ThreadFactory() {
            private final AtomicInteger counter = new AtomicInteger();

            @Override
            public Thread newThread(Runnable runnable) {
                Thread thread = new Thread(runnable);
                thread.setName("benchmark-worker-" + counter.getAndIncrement());
                thread.setDaemon(true);
                return thread;
            }
        };
        if (nativeParallelism == Integer.MAX_VALUE) {
            ThreadPoolExecutor cached = new ThreadPoolExecutor(
                0,
                Integer.MAX_VALUE,
                60L,
                TimeUnit.SECONDS,
                new SynchronousQueue<>(),
                threadFactory);
            cached.allowCoreThreadTimeOut(true);
            return cached;
        }
        ThreadPoolExecutor fixed = new ThreadPoolExecutor(
            nativeParallelism,
            nativeParallelism,
            0L,
            TimeUnit.MILLISECONDS,
            new LinkedBlockingQueue<>(),
            threadFactory);
        fixed.prestartAllCoreThreads();
        return fixed;
    }

    private void cancelFutures(List<Future<?>> futures) {
        for (Future<?> future : futures) {
            future.cancel(true);
        }
    }

    static final class WorkloadSettings {
        private static final String ENV_DATA_SIZE = "GRAMINE_BENCH_DATA_SIZE";
        private static final String ENV_WARMUP = "GRAMINE_BENCH_WARMUP";
        private static final String ENV_MEASURE = "GRAMINE_BENCH_MEASURE";

        private final int dataSize;
        private final int warmupIterations;
        private final int measureIterations;
        private final double sigma;

        WorkloadSettings(int dataSize,
                         int warmupIterations,
                         int measureIterations,
                         double sigma) {
            this.dataSize = dataSize;
            this.warmupIterations = warmupIterations;
            this.measureIterations = measureIterations;
            this.sigma = sigma;
        }

        static WorkloadSettings fromEnvironment(double sigma) {
            int dataSize = parseIntEnv(ENV_DATA_SIZE, 1024);
            int warmupIterations = parseIntEnv(ENV_WARMUP, 3);
            int measureIterations = parseIntEnv(ENV_MEASURE, 5);
            return new WorkloadSettings(dataSize, warmupIterations, measureIterations, sigma);
        }

        int getDataSize() {
            return dataSize;
        }

        int getWarmupIterations() {
            return warmupIterations;
        }

        int getMeasureIterations() {
            return measureIterations;
        }

        double getSigma() {
            return sigma;
        }

        private static int parseIntEnv(String key, int defaultValue) {
            String raw = System.getenv(key);
            if (raw == null || raw.isEmpty()) {
                return defaultValue;
            }
            try {
                return Integer.parseInt(raw.trim());
            } catch (NumberFormatException nfe) {
                throw new IllegalArgumentException("Unable to parse integer from " + key + "=" + raw, nfe);
            }
        }

    }

    static final class Workload {
        private final int dataSize;
        private final double sigma;
        private final int warmupIterations;
        private final int measureIterations;
        private final double averageMillis;
        private final int requestedThreads;
        private final int executedThreads;

        Workload(int dataSize, double sigma, int warmupIterations, int measureIterations,
                 double averageMillis, int requestedThreads, int executedThreads) {
            this.dataSize = dataSize;
            this.sigma = sigma;
            this.warmupIterations = warmupIterations;
            this.measureIterations = measureIterations;
            this.averageMillis = averageMillis;
            this.requestedThreads = requestedThreads;
            this.executedThreads = executedThreads;
        }

        int getDataSize() {
            return dataSize;
        }

        double getSigma() {
            return sigma;
        }

        int getWarmupIterations() {
            return warmupIterations;
        }

        int getMeasureIterations() {
            return measureIterations;
        }

        double getAverageMillis() {
            return averageMillis;
        }

        int getRequestedThreads() {
            return requestedThreads;
        }

        int getExecutedThreads() {
            return executedThreads;
        }

        @Override
        public String toString() {
            return "Workload{" +
                "dataSize=" + dataSize +
                ", sigma=" + sigma +
                ", warmupIterations=" + warmupIterations +
                ", measureIterations=" + measureIterations +
                ", avgTimeMillis=" + String.format("%.3f", averageMillis) +
                ", requestedThreads=" + requestedThreads +
                ", executedThreads=" + executedThreads +
                '}';
        }
    }

    static final class WeakScalingResult {
        private final int requestedThreadCount;
        private final int executedThreadCount;
        private final int dataSize;
        private final int iterations;
        private final double averageMillis;

        WeakScalingResult(int requestedThreadCount, int executedThreadCount, int dataSize, int iterations, double averageMillis) {
            this.requestedThreadCount = requestedThreadCount;
            this.executedThreadCount = executedThreadCount;
            this.dataSize = dataSize;
            this.iterations = iterations;
            this.averageMillis = averageMillis;
        }

        int getRequestedThreadCount() {
            return requestedThreadCount;
        }

        int getExecutedThreadCount() {
            return executedThreadCount;
        }

        int getDataSize() {
            return dataSize;
        }

        int getIterations() {
            return iterations;
        }

        double getAverageMillis() {
            return averageMillis;
        }
    }

    static final class StrongScalingResult {
        private final int requestedThreadCount;
        private final int executedThreadCount;
        private final int totalSize;
        private final int iterations;
        private final double averageMillis;

        StrongScalingResult(int requestedThreadCount, int executedThreadCount, int totalSize, int iterations, double averageMillis) {
            this.requestedThreadCount = requestedThreadCount;
            this.executedThreadCount = executedThreadCount;
            this.totalSize = totalSize;
            this.iterations = iterations;
            this.averageMillis = averageMillis;
        }

        int getRequestedThreadCount() {
            return requestedThreadCount;
        }

        int getExecutedThreadCount() {
            return executedThreadCount;
        }

        int getTotalSize() {
            return totalSize;
        }

        int getIterations() {
            return iterations;
        }

        double getAverageMillis() {
            return averageMillis;
        }
    }

    static final class BenchmarkSummary {
        private final WorkloadSettings settings;
        private final Workload workload;
        private final int[] weakThreadCounts;
        private final int[] strongThreadCounts;
        private final List<WeakScalingResult> weakScalingResults;
        private final List<StrongScalingResult> strongScalingResults;
        private final int maxNativeThreadsSupported;
        private final int maxNativeThreadsUsed;

        BenchmarkSummary(WorkloadSettings settings,
                         Workload workload,
                         int[] weakThreadCounts,
                         List<WeakScalingResult> weakScalingResults,
                         int[] strongThreadCounts,
                         List<StrongScalingResult> strongScalingResults,
                         int maxNativeThreadsUsed) {
            this.settings = settings;
            this.workload = workload;
            this.weakThreadCounts = Arrays.copyOf(weakThreadCounts, weakThreadCounts.length);
            this.strongThreadCounts = Arrays.copyOf(strongThreadCounts, strongThreadCounts.length);
            this.weakScalingResults = Collections.unmodifiableList(new ArrayList<>(weakScalingResults));
            this.strongScalingResults = Collections.unmodifiableList(new ArrayList<>(strongScalingResults));
            this.maxNativeThreadsSupported = computeMaxNativeThreadsSupported(workload, weakScalingResults, strongScalingResults);
            this.maxNativeThreadsUsed = maxNativeThreadsUsed;
        }

        Workload getWorkload() {
            return workload;
        }

        List<WeakScalingResult> getWeakScalingResults() {
            return weakScalingResults;
        }

        List<StrongScalingResult> getStrongScalingResults() {
            return strongScalingResults;
        }

        String toPrettyString() {
            StringBuilder sb = new StringBuilder();
            sb.append("{\n");
            sb.append("  \"settings\": {\n");
            sb.append(String.format(Locale.US,
                "    \"sigma\": %.6f,%n    \"dataSize\": %d,%n    \"warmupIterations\": %d,%n    \"measureIterations\": %d,%n    \"weakThreadCounts\": %s,%n    \"strongThreadCounts\": %s,%n",
                settings.getSigma(), settings.getDataSize(), settings.getWarmupIterations(), settings.getMeasureIterations(),
                formatIntArray(weakThreadCounts), formatIntArray(strongThreadCounts)));
            sb.append(String.format(Locale.US, "    \"maxNativeThreadsSupported\": %d,%n", maxNativeThreadsSupported));
            sb.append(String.format(Locale.US, "    \"maxNativeThreadsUsed\": %d%n", maxNativeThreadsUsed));
            sb.append("  },\n");
            sb.append("  \"workload\": {\n");
            sb.append(String.format(Locale.US,
                "    \"dataSize\": %d,%n    \"sigma\": %.6f,%n    \"warmupIterations\": %d,%n    \"measureIterations\": %d,%n    \"avgTimeMillis\": %.3f,%n    \"requestedThreads\": %d,%n    \"executedThreads\": %d%n",
                workload.getDataSize(), workload.getSigma(), workload.getWarmupIterations(), workload.getMeasureIterations(),
                workload.getAverageMillis(), workload.getRequestedThreads(), workload.getExecutedThreads()));
            sb.append("  },\n");
            sb.append("  \"weakScaling\": [\n");
            for (int i = 0; i < weakScalingResults.size(); i++) {
                WeakScalingResult result = weakScalingResults.get(i);
                sb.append(String.format(Locale.US,
                    "    {\"threads\": %d, \"executedThreads\": %d, \"dataSize\": %d, \"iterations\": %d, \"avgTimeMillis\": %.3f}",
                    result.getRequestedThreadCount(), result.getExecutedThreadCount(), result.getDataSize(), result.getIterations(),
                    result.getAverageMillis()));
                if (i < weakScalingResults.size() - 1) {
                    sb.append(",");
                }
                sb.append("\n");
            }
            sb.append("  ],\n");
            sb.append("  \"strongScaling\": [\n");
            for (int i = 0; i < strongScalingResults.size(); i++) {
                StrongScalingResult result = strongScalingResults.get(i);
                sb.append(String.format(Locale.US,
                    "    {\"threads\": %d, \"executedThreads\": %d, \"totalSize\": %d, \"iterations\": %d, \"avgTimeMillis\": %.3f}",
                    result.getRequestedThreadCount(), result.getExecutedThreadCount(), result.getTotalSize(), result.getIterations(), result.getAverageMillis()));
                if (i < strongScalingResults.size() - 1) {
                    sb.append(",");
                }
                sb.append("\n");
            }
            sb.append("  ]\n");
            sb.append("}");
            return sb.toString();
        }

        int getMaxNativeThreadsSupported() {
            return maxNativeThreadsSupported;
        }

        int getMaxNativeThreadsUsed() {
            return maxNativeThreadsUsed;
        }

        private static String formatIntArray(int[] values) {
            StringBuilder builder = new StringBuilder("[");
            for (int i = 0; i < values.length; i++) {
                builder.append(values[i]);
                if (i < values.length - 1) {
                    builder.append(",");
                }
            }
            builder.append("]");
            return builder.toString();
        }

        private static int computeMaxNativeThreadsSupported(Workload workload,
                                                            List<WeakScalingResult> weakResults,
                                                            List<StrongScalingResult> strongResults) {
            int max = workload != null ? workload.getExecutedThreads() : 0;
            for (WeakScalingResult result : weakResults) {
                max = Math.max(max, result.getExecutedThreadCount());
            }
            for (StrongScalingResult result : strongResults) {
                max = Math.max(max, result.getExecutedThreadCount());
            }
            return max;
        }
    }
}
