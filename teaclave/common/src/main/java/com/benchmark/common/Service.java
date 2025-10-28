package com.benchmark.teaclave.common;

import org.apache.teaclave.javasdk.common.annotations.EnclaveService;

@EnclaveService
public interface Service {
    String sayHelloWorld();
    Ack pushValue(int value);
}
