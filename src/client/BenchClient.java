import java.io.*;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;
import javax.net.ssl.*;

public class BenchClient {

    private static final String DEFAULT_HOST = "localhost";
    private static final int DEFAULT_PORT = 8443;
    private static final String TRUSTSTORE_TYPE = "JKS";
    private static final String TLS_PROTOCOL = "TLSv1.2";

    private final String host;
    private final int port;

    public BenchClient(String host, int port) {
        this.host = host;
        this.port = port;
    }

    /**
     * Initialize SSL context with truststore
     */
    private SSLContext createSSLContext(
        String truststorePath,
        String truststorePassword
    ) throws Exception {
        KeyStore trustStore = KeyStore.getInstance(TRUSTSTORE_TYPE);
        try (FileInputStream fis = new FileInputStream(truststorePath)) {
            trustStore.load(fis, truststorePassword.toCharArray());
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm()
        );
        tmf.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance(TLS_PROTOCOL);
        sslContext.init(null, tmf.getTrustManagers(), new SecureRandom());

        return sslContext;
    }

    /**
     * Connect to the server and send/receive data
     */
    public void connect(
        String truststorePath,
        String truststorePassword,
        int numMessages,
        String messagePrefix
    ) throws Exception {
        SSLContext sslContext = createSSLContext(
            truststorePath,
            truststorePassword
        );
        SSLSocketFactory sslSocketFactory = sslContext.getSocketFactory();

        try (
            SSLSocket socket = (SSLSocket) sslSocketFactory.createSocket(
                host,
                port
            )
        ) {
            socket.setEnabledProtocols(new String[] { TLS_PROTOCOL });

            System.out.println("Connected to server: " + host + ":" + port);

            try (
                PrintWriter writer = new PrintWriter(
                    socket.getOutputStream(),
                    true
                );
                BufferedReader reader = new BufferedReader(
                    new InputStreamReader(socket.getInputStream())
                )
            ) {
                long totalLatency = 0;
                int successCount = 0;

                for (int i = 1; i <= numMessages; i++) {
                    String message =
                        messagePrefix +
                        " - Message #" +
                        i +
                        " - " +
                        generatePayload(i);

                    long startTime = System.nanoTime();

                    // Send message
                    writer.println(message);

                    // Wait for acknowledgment
                    String ack = reader.readLine();

                    long endTime = System.nanoTime();
                    long latencyMs = (endTime - startTime) / 1_000_000;
                    totalLatency += latencyMs;

                    if (ack != null && ack.startsWith("ACK")) {
                        successCount++;
                        if (i % 10 == 0 || i <= 5) {
                            System.out.println(
                                "Message " +
                                    i +
                                    " - Latency: " +
                                    latencyMs +
                                    " ms - Response: " +
                                    ack
                            );
                        }
                    } else {
                        System.err.println(
                            "Unexpected response for message " + i + ": " + ack
                        );
                    }

                    // Optional: add a small delay between messages
                    if (i < numMessages) {
                        Thread.sleep(10);
                    }
                }

                // Print statistics
                System.out.println("\n=== Statistics ===");
                System.out.println("Total messages sent: " + numMessages);
                System.out.println(
                    "Successful acknowledgments: " + successCount
                );
                System.out.println(
                    "Average latency: " + (totalLatency / numMessages) + " ms"
                );
                System.out.println("Total time: " + totalLatency + " ms");
            }
        } catch (Exception e) {
            System.err.println("Error connecting to server: " + e.getMessage());
            throw e;
        }
    }

    /**
     * Generate variable-size payload for testing
     */
    private String generatePayload(int messageNumber) {
        StringBuilder sb = new StringBuilder();
        sb.append("Timestamp=").append(System.currentTimeMillis()).append(";");
        sb.append("Data=");

        // Variable payload size based on message number
        int payloadSize = 50 + (messageNumber % 200);
        for (int i = 0; i < payloadSize; i++) {
            sb.append((char) ('A' + (i % 26)));
        }

        return sb.toString();
    }

    /**
     * Run concurrent load test
     */
    public static void runLoadTest(
        String host,
        int port,
        String truststorePath,
        String truststorePassword,
        int numClients,
        int messagesPerClient
    ) throws Exception {
        System.out.println(
            "Starting load test with " + numClients + " concurrent clients..."
        );

        CountDownLatch startLatch = new CountDownLatch(1);
        CountDownLatch finishLatch = new CountDownLatch(numClients);
        AtomicLong totalMessages = new AtomicLong(0);
        AtomicLong totalErrors = new AtomicLong(0);

        long startTime = System.currentTimeMillis();

        for (int i = 0; i < numClients; i++) {
            final int clientId = i + 1;
            new Thread(() -> {
                try {
                    startLatch.await(); // Wait for all threads to be ready
                    BenchClient client = new BenchClient(host, port);
                    client.connect(
                        truststorePath,
                        truststorePassword,
                        messagesPerClient,
                        "Client-" + clientId
                    );
                    totalMessages.addAndGet(messagesPerClient);
                } catch (Exception e) {
                    System.err.println(
                        "Client " + clientId + " error: " + e.getMessage()
                    );
                    totalErrors.incrementAndGet();
                } finally {
                    finishLatch.countDown();
                }
            })
                .start();
        }

        startLatch.countDown(); // Start all threads
        finishLatch.await(); // Wait for all to complete

        long endTime = System.currentTimeMillis();
        long totalTime = endTime - startTime;

        System.out.println("\n=== Load Test Results ===");
        System.out.println("Total clients: " + numClients);
        System.out.println("Messages per client: " + messagesPerClient);
        System.out.println("Total messages processed: " + totalMessages.get());
        System.out.println("Total errors: " + totalErrors.get());
        System.out.println("Total time: " + totalTime + " ms");
        System.out.println(
            "Throughput: " +
                ((totalMessages.get() * 1000.0) / totalTime) +
                " messages/second"
        );
    }

    /**
     * Main method
     */
    public static void main(String[] args) {
        String host = DEFAULT_HOST;
        int port = DEFAULT_PORT;
        String truststorePath = "client.truststore";
        String truststorePassword = "changeit";
        int numMessages = 100;
        boolean loadTest = false;
        int numClients = 10;

        // Parse command line arguments
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--host":
                case "-h":
                    if (i + 1 < args.length) {
                        host = args[++i];
                    }
                    break;
                case "--port":
                case "-p":
                    if (i + 1 < args.length) {
                        port = Integer.parseInt(args[++i]);
                    }
                    break;
                case "--truststore":
                case "-t":
                    if (i + 1 < args.length) {
                        truststorePath = args[++i];
                    }
                    break;
                case "--password":
                case "-pw":
                    if (i + 1 < args.length) {
                        truststorePassword = args[++i];
                    }
                    break;
                case "--messages":
                case "-m":
                    if (i + 1 < args.length) {
                        numMessages = Integer.parseInt(args[++i]);
                    }
                    break;
                case "--load-test":
                case "-l":
                    loadTest = true;
                    break;
                case "--clients":
                case "-c":
                    if (i + 1 < args.length) {
                        numClients = Integer.parseInt(args[++i]);
                    }
                    break;
                case "--help":
                    printUsage();
                    return;
            }
        }

        try {
            if (loadTest) {
                runLoadTest(
                    host,
                    port,
                    truststorePath,
                    truststorePassword,
                    numClients,
                    numMessages
                );
            } else {
                BenchClient client = new BenchClient(host, port);
                client.connect(
                    truststorePath,
                    truststorePassword,
                    numMessages,
                    "SingleClient"
                );
            }
        } catch (Exception e) {
            System.err.println("Client failed: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }

    private static void printUsage() {
        System.out.println("Usage: java client.BenchClient [OPTIONS]");
        System.out.println("\nOptions:");
        System.out.println(
            "  -h, --host <host>              Server host (default: localhost)"
        );
        System.out.println(
            "  -p, --port <port>              Server port (default: 8443)"
        );
        System.out.println(
            "  -t, --truststore <path>        Path to truststore file (default: client.truststore)"
        );
        System.out.println(
            "  -pw, --password <password>     Truststore password (default: changeit)"
        );
        System.out.println(
            "  -m, --messages <count>         Number of messages to send (default: 100)"
        );
        System.out.println(
            "  -l, --load-test                Run load test with multiple clients"
        );
        System.out.println(
            "  -c, --clients <count>          Number of concurrent clients for load test (default: 10)"
        );
        System.out.println(
            "  --help                         Display this help message"
        );
        System.out.println("\nExamples:");
        System.out.println("  Single client:");
        System.out.println(
            "    java client.BenchClient --host localhost --port 8443 --messages 50"
        );
        System.out.println("  Load test:");
        System.out.println(
            "    java client.BenchClient --load-test --clients 20 --messages 100"
        );
    }
}
