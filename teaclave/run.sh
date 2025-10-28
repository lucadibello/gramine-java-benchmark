#/bin/bash

mvn -Pnative clean package

ENABLE_OCCULUM=false

OCCLUM_RELEASE_ENCLAVE=$ENABLE_OCCULUM $JAVA_HOME/bin/java -cp host/target/host-1.0-SNAPSHOT-jar-with-dependencies.jar:enclave/target/enclave-1.0-SNAPSHOT-jar-with-dependencies.jar com.benchmark.teaclave.host.Main
