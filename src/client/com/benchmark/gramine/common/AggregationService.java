package com.benchmark.gramine.common;

public interface AggregationService extends AutoCloseable {
    void initBinaryAggregation(int n, double sigma);
    double addToBinaryAggregation(double value);
    double getBinaryAggregationSum();

    @Override
    void close();
}
