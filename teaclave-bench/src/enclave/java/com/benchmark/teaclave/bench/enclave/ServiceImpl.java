package com.benchmark.teaclave.enclave;

import com.benchmark.teaclave.teaclave-bench.common.Service;
import com.google.auto.service.AutoService;

@AutoService(Service.class)
public class ServiceImpl implements Service {
    @Override
    public String sayHelloWorld() {
        return "Hello World";
    }
}
