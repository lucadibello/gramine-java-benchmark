# TLS Benchmark Server (Confidential Computing)

A multi-threaded TLS socket server that runs inside **Gramine** for confidential computing. The server processes data in a hardware-protected Trusted Execution Environment (TEE), ensuring that all stream processing happens in isolation from the host OS, hypervisor, and infrastructure.

**Why this matters:** When running in Intel SGX or similar TEEs via Gramine, your data is encrypted in memory and protected by hardware. Even someone with root access to the host can't inspect the data being processed.

## Confidential Computing with Gramine

This benchmark is designed to run in [Gramine](https://gramine.readthedocs.io/), a library OS that enables unmodified applications to run in Trusted Execution Environments like Intel SGX.

**What you get:**
- **Memory encryption** - All data in the enclave is encrypted by the CPU
- **Isolation** - The application runs isolated from the host OS and other processes
- **Attestation** - Clients can cryptographically verify they're talking to the real server running in a genuine TEE
- **Confidentiality** - Even cloud providers can't see your data

This makes the TLS server truly confidential - the entire stream processing pipeline (checksums, transformations, pattern matching) happens inside the protected enclave.

## Components

**BenchServer** (`src/server/BenchServer.java`)
- Multi-threaded TLS server using ExecutorService
- Simulates stream processing: CRC32 checksums, data transformation, pattern matching, statistical analysis
- Returns detailed acknowledgments with processing metrics
- **Runs entirely inside the Gramine enclave**

**BenchClient** (`src/client/BenchClient.java`)
- TLS client with single-client and load-testing modes
- Measures latency and throughput
- Configurable payload sizes
- Can run outside the enclave to test performance

## Getting Started

You'll need Java 8 or later and Gramine installed (!! the devcontainer already providers a working environment !!).

### Generate Certificates

```bash
cd /workspaces/gramine-java-benchmark
chmod +x tools/generate-certs.sh
./tools/generate-certs.sh
```

This creates `server.keystore` and `client.truststore` with the default password `changeit`.

**Note:** These are self-signed certificates for testing only. In production with Gramine, you'd typically use attestation to establish trust instead of (or in addition to) traditional certificate verification.

### Compile

```bash
make clean && build all SGX=1
```

## Running the Server (in Gramine)

The server is meant to run inside Gramine. You'll need a Gramine manifest file configured for Java. See the Gramine documentation for details on creating manifests.

Typical Gramine command:
```bash
gramine-sgx java -cp target/classes server.BenchServer --port 8443
```

Or for testing without SGX:
```bash
gramine-direct java -cp target/classes server.BenchServer --port 8443
```

**Options:**
- `-p, --port` - Server port (default: 8443)
- `-k, --keystore` - Keystore path (default: server.keystore)
- `-pw, --password` - Keystore password (default: changeit)

## Running the Client

The client typically runs outside the enclave (native execution):

Send 100 messages:
```bash
java -cp target/classes client.BenchClient --host localhost --port 8443 --messages 100
```

Load test with 10 concurrent clients:
```bash
java -cp target/classes client.BenchClient --load-test --clients 10 --messages 50
```

**Options:**
- `-h, --host` - Server hostname (default: localhost)
- `-p, --port` - Server port (default: 8443)
- `-t, --truststore` - Truststore path (default: client.truststore)
- `-pw, --password` - Truststore password (default: changeit)
- `-m, --messages` - Messages to send (default: 100)
- `-l, --load-test` - Enable load testing mode
- `-c, --clients` - Concurrent clients for load test (default: 10)

## Protocol

Clients send newline-terminated text messages. The server responds with:
```
ACK|checksum=<crc32>|size=<bytes>|processing_time_ms=<ms>|status=<status>
```

Example:
```
ACK|checksum=1234567890|size=256|processing_time_ms=15|status=SUCCESS
```

## Customization

Change the thread pool size in `BenchServer.java`:
```java
private static final int THREAD_POOL_SIZE = 10;
```

Modify stream processing in the `processData()` method of `BenchServer.ClientHandler`.

Switch TLS versions (both server and client):
```java
private static final String TLS_PROTOCOL = "TLSv1.3";
```

## Security & Confidential Computing

**This is the whole point of the project.** The server runs in Gramine/SGX, which means:

- Data is encrypted in memory by the CPU (AES-128)
- The host OS can't inspect or modify the enclave
- Cloud providers are effectively blind to your data
- You can prove to clients that the code is running in a real TEE (via attestation)

For production confidential computing deployments:
- Use remote attestation to verify the enclave
- Implement sealed storage for persistent data
- Get certificates from a trusted CA or use attestation-based trust
- Never pass secrets via command-line (use sealed files or secret provisioning)
- Monitor enclave exits and performance carefully

The self-signed certificates here are just for benchmarking. In real deployments, clients would typically verify SGX quotes and measurements instead of (or alongside) traditional TLS certificate chains.

## License

Use this however you want. It's a benchmarking tool for confidential computing workloads.
