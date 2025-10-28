package com.benchmark.teaclave.host;

import org.apache.teaclave.javasdk.host.Enclave;
import org.apache.teaclave.javasdk.host.EnclaveFactory;
import org.apache.teaclave.javasdk.host.EnclaveType;

import com.benchmark.teaclave.common.Service;
import com.benchmark.teaclave.common.Ack;

import java.util.Iterator;

public class Main {
    public static void main(String[] args) throws Exception {
        /*  this is just for reference!
          EnclaveType[] enclaveTypes = {
                EnclaveType.MOCK_IN_JVM,
                EnclaveType.MOCK_IN_SVM,
                EnclaveType.TEE_SDK};
        */

        // create hardware enclave 
        Enclave enclave = EnclaveFactory.create(EnclaveType.TEE_SDK);
        // load enclave from service
        Iterator<Service> services = enclave.load(Service.class);

        // call methods inside enclave from host
        Service s = services.next();
        System.out.println(s.sayHelloWorld());
        for (int i = 0;i<10;i++) {
          Ack resp = s.pushValue(69+i);
          System.out.println(resp);
        }

        // destroy everything
        enclave.destroy();
    }
}
