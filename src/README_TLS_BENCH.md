# TLS Benchmark Server and Client

This project implements a TLS socket server that receives data from clients, simulates stream processing, and sends acknowledgments back.

## Overview

### Components

1. **BenchServer** (`src/server/BenchServer.java`)
   - TLS-enabled socket server
   - Multi-threaded connection handling using ExecutorService
   - Simulates stream processing with:
     - CRC32 checksum computation
     - Data transformation
     - Pattern matching
     - Statistical computation
     - CPU-intensive work simulation
   - Sends detailed acknowledgments with processing metrics

2. **BenchClient** (`src/client/BenchClient.java`)
   - TLS-enabled client for testing
   - Supports single-client mode and load testing mode
   - Measures latency and throughput
   - Variable payload size generation

## Prerequisites

- Java Development Kit (JDK) 8 or higher
- `keytool` (included with JDK)

## Setup

### 1. Generate TLS Certificates

First, generate the required TLS certificates and keystores:

```bash
cd /workspaces/gramine-java-benchmark
chmod +x tools/generate-certs.sh
./tools/generate-certs.sh
```

This will create:
- `server.keystore` - Contains the server's private key and certificate
- `client.truststore` - Contains the trusted server certificate for client verification

Default password: `changeit`

### 2. Compile the Code

```bash
# Compile server
javac -d target/classes src/server/BenchServer.java

# Compile client
javac -d target/classes src/client/BenchClient.java
```

Or compile both at once:

```bash
mkdir -p target/classes
javac -d target/classes src/server/BenchServer.java src/client/BenchClient.java
```

## Usage

### Running the Server

Basic usage with default settings (port 8443):

```bash
java -cp target/classes server.BenchServer
```

With custom options:

```bash
java -cp target/classes server.BenchServer \
  --port 8443 \
  --keystore server.keystore \
  --password changeit
```

#### Server Options

- `-p, --port <port>` - Server port (default: 8443)
- `-k, --keystore <path>` - Path to keystore file (default: server.keystore)
- `-pw, --password <password>` - Keystore password (default: changeit)
- `-h, --help` - Display help message

### Running the Client

#### Single Client Mode

Send 100 messages to the server:

```bash
java -cp target/classes client.BenchClient \
  --host localhost \
  --port 8443 \
  --messages 100
```

#### Load Test Mode

Run a load test with 10 concurrent clients, each sending 50 messages:

```bash
java -cp target/classes client.BenchClient \
  --load-test \
  --clients 10 \
  --messages 50
```

#### Client Options

- `-h, --host <host>` - Server host (default: localhost)
- `-p, --port <port>` - Server port (default: 8443)
- `-t, --truststore <path>` - Path to truststore file (default: client.truststore)
- `-pw, --password <password>` - Truststore password (default: changeit)
- `-m, --messages <count>` - Number of messages to send (default: 100)
- `-l, --load-test` - Run load test with multiple clients
- `-c, --clients <count>` - Number of concurrent clients for load test (default: 10)
- `--help` - Display help message

## Protocol

### Message Format

**Client → Server:**
```
Plain text message (newline-terminated)
```

**Server → Client (Acknowledgment):**
```
ACK|checksum=<crc32>|size=<bytes>|processing_time_ms=<ms>|status=<status>
```

Example:
```
ACK|checksum=1234567890|size=256|processing_time_ms=15|status=SUCCESS
```

## Stream Processing Simulation

The server simulates realistic stream processing with the following operations:

1. **Checksum Calculation** - Computes CRC32 checksum of incoming data
2. **Data Transformation** - Converts data to uppercase (simulates normalization)
3. **Pattern Matching** - Counts words in the data stream
4. **Statistical Computation** - Calculates average character value
5. **CPU-Intensive Work** - Performs mathematical operations proportional to data size

Processing time is measured in nanoseconds and reported back to the client in milliseconds.

## Performance Metrics

The server reports:
- Processing time per message
- Data size processed
- Checksum validation

The client reports:
- Round-trip latency
- Success rate
- Throughput (messages/second in load test mode)

## Example Session

### Terminal 1 (Server)
```bash
$ java -cp target/classes server.BenchServer
TLS Server started on port 8443
Client connected: 127.0.0.1
Handling client: 127.0.0.1:54321
Processed data from 127.0.0.1:54321 (size: 150 bytes, time: 12 ms)
Processed data from 127.0.0.1:54321 (size: 175 bytes, time: 14 ms)
...
```

### Terminal 2 (Client)
```bash
$ java -cp target/classes client.BenchClient --messages 10
Connected to server: localhost:8443
Message 1 - Latency: 25 ms - Response: ACK|checksum=1234567890|size=150|processing_time_ms=12|status=SUCCESS
Message 2 - Latency: 27 ms - Response: ACK|checksum=9876543210|size=175|processing_time_ms=14|status=SUCCESS
...
=== Statistics ===
Total messages sent: 10
Successful acknowledgments: 10
Average latency: 26 ms
Total time: 260 ms
```

## Security Notes

⚠️ **Important**: The generated certificates are self-signed and intended for development/testing only. 

For production use:
- Use certificates from a trusted Certificate Authority (CA)
- Implement proper certificate validation
- Use stronger key sizes (4096-bit RSA or ECDSA)
- Enable mutual TLS (mTLS) authentication
- Store passwords securely (not in command-line arguments)

## Troubleshooting

### Connection Refused
- Ensure the server is running
- Check firewall settings
- Verify the port number matches

### Certificate Errors
- Regenerate certificates using `generate-certs.sh`
- Verify keystore/truststore paths are correct
- Ensure passwords match

### Out of Memory
- Reduce thread pool size in `BenchServer.java`
- Decrease number of concurrent clients
- Adjust JVM heap size: `java -Xmx512m -cp target/classes ...`

## Customization

### Adjusting Thread Pool Size

Edit `BenchServer.java`:
```java
private static final int THREAD_POOL_SIZE = 10; // Change as needed
```

### Modifying Stream Processing

Edit the `processData()` method in `BenchServer.ClientHandler` to add your own processing logic.

### Changing TLS Protocol

Edit both server and client:
```java
private static final String TLS_PROTOCOL = "TLSv1.3"; // Or TLSv1.2
```

## License

This is a benchmark/testing tool. Use at your own discretion.