package com.benchmark.teaclave.enclave;

import com.benchmark.teaclave.common.Service;
import com.benchmark.teaclave.common.Ack;
import com.google.auto.service.AutoService;

@AutoService(Service.class)
public class ServiceImpl implements Service {

    private int id_counter = 0;

    @Override
    public String sayHelloWorld() {
        return "Hello World";
    }

    @Override
    public Ack pushValue(int value) {
      Ack resp = new Ack(id_counter++,value);
      return resp;
    }
}
