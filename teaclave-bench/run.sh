#/bin/bash

mvn -Pnative clean package
#org.apache.teaclave.javasdk.samples.helloworld.host.Main

OCCLUM_RELEASE_ENCLAVE=true $JAVA_HOME/bin/java -cp host/target/host-1.0-SNAPSHOT-jar-with-dependencies.jar:enclave/target/enclave-1.0-SNAPSHOT-jar-with-dependencies.jar com.benchmark.teaclave.bench.host.Main
