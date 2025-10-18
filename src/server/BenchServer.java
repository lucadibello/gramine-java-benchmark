package server;

import javax.net.ssl.*;
import java.io.*;
import java.net.ServerSocket;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.concurrent.*;
import java.util.zip.CRC32;

public class BenchServer {
    private static final int DEFAULT_PORT = 8443;
    private static final int THREAD_POOL_SIZE = 10;
    private static final String KEYSTORE_TYPE = "JKS";
    private static final String TLS_PROTOCOL = "TLSv1.2";

    private final int port;
    private final ExecutorService executorService;
    private volatile boolean running = false;
    private SSLServerSocket serverSocket;

    public BenchServer(int port) {
        this.port = port;
        this.executorService = Executors.newFixedThreadPool(THREAD_POOL_SIZE);
    }

    /**
     * Initialize SSL context with keystore
     */
    private SSLContext createSSLContext(String keystorePath, String keystorePassword) throws Exception {
        KeyStore keyStore = KeyStore.getInstance(KEYSTORE_TYPE);
        try (FileInputStream fis = new FileInputStream(keystorePath)) {
            keyStore.load(fis, keystorePassword.toCharArray());
        }

        KeyManagerFactory kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keyStore, keystorePassword.toCharArray());

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(keyStore);

        SSLContext sslContext = SSLContext.getInstance(TLS_PROTOCOL);
        sslContext.init(kmf.getKeyManagers(), tmf.getTrustManagers(), new SecureRandom());

        return sslContext;
    }

    /**
     * Start the TLS server
     */
    public void start(String keystorePath, String keystorePassword) throws Exception {
        SSLContext sslContext = createSSLContext(keystorePath, keystorePassword);
        SSLServerSocketFactory sslServerSocketFactory = sslContext.getServerSocketFactory();

        serverSocket = (SSLServerSocket) sslServerSocketFactory.createServerSocket(port);
        serverSocket.setEnabledProtocols(new String[]{TLS_PROTOCOL});

        running = true;
        System.out.println("TLS Server started on port " + port);

        while (running) {
            try {
                SSLSocket clientSocket = (SSLSocket) serverSocket.accept();
                System.out.println("Client connected: " + clientSocket.getInetAddress().getHostAddress());
                executorService.submit(new ClientHandler(clientSocket));
            } catch (IOException e) {
                if (running) {
                    System.err.println("Error accepting client connection: " + e.getMessage());
                }
            }
        }
    }

    /**
     * Stop the server
     */
    public void stop() {
        running = false;
        try {
            if (serverSocket != null && !serverSocket.isClosed()) {
                serverSocket.close();
            }
        } catch (IOException e) {
            System.err.println("Error closing server socket: " + e.getMessage());
        }
        executorService.shutdown();
        try {
            if (!executorService.awaitTermination(5, TimeUnit.SECONDS)) {
                executorService.shutdownNow();
            }
        } catch (InterruptedException e) {
            executorService.shutdownNow();
        }
        System.out.println("Server stopped");
    }

    /**
     * Client handler - processes each client connection in a separate thread
     */
    private static class ClientHandler implements Runnable {
        private final SSLSocket socket;

        public ClientHandler(SSLSocket socket) {
            this.socket = socket;
        }

        @Override
        public void run() {
            try (
                BufferedReader reader = new BufferedReader(new InputStreamReader(socket.getInputStream()));
                PrintWriter writer = new PrintWriter(socket.getOutputStream(), true)
            ) {
                String clientInfo = socket.getInetAddress().getHostAddress() + ":" + socket.getPort();
                System.out.println("Handling client: " + clientInfo);

                String line;
                while ((line = reader.readLine()) != null) {
                    long startTime = System.nanoTime();

                    // Simulate stream processing
                    ProcessingResult result = processData(line);

                    long endTime = System.nanoTime();
                    long processingTimeMs = (endTime - startTime) / 1_000_000;

                    // Send acknowledgment back to client
                    String ack = String.format("ACK|checksum=%d|size=%d|processing_time_ms=%d|status=%s",
                            result.checksum, result.dataSize, processingTimeMs, result.status);
                    writer.println(ack);

                    System.out.println("Processed data from " + clientInfo +
                            " (size: " + result.dataSize + " bytes, time: " + processingTimeMs + " ms)");
                }

            } catch (IOException e) {
                System.err.println("Error handling client: " + e.getMessage());
            } finally {
                try {
                    socket.close();
                    System.out.println("Client disconnected: " + socket.getInetAddress().getHostAddress());
                } catch (IOException e) {
                    System.err.println("Error closing client socket: " + e.getMessage());
                }
            }
        }

        /**
         * Simulate stream processing with various operations
         */
        private ProcessingResult processData(String data) {
            ProcessingResult result = new ProcessingResult();
            result.dataSize = data.length();

            try {
                // Simulate various processing operations

                // 1. Compute checksum (CRC32)
                CRC32 crc = new CRC32();
                crc.update(data.getBytes());
                result.checksum = crc.getValue();

                // 2. Data transformation (simulated)
                String transformed = data.toUpperCase();

                // 3. Pattern matching simulation
                int wordCount = data.split("\\s+").length;

                // 4. Statistical computation
                double avgCharValue = data.chars().average().orElse(0.0);

                // 5. Simulate some CPU-intensive work
                simulateCPUWork(data.length());

                result.status = "SUCCESS";

            } catch (Exception e) {
                result.status = "ERROR: " + e.getMessage();
            }

            return result;
        }

        /**
         * Simulate CPU-intensive work based on data size
         */
        private void simulateCPUWork(int dataSize) {
            // Simulate processing complexity proportional to data size
            long iterations = Math.min(dataSize * 100L, 100000L);
            double result = 0;
            for (long i = 0; i < iterations; i++) {
                result += Math.sqrt(i) * Math.sin(i);
            }
        }
    }

    /**
     * Result of data processing
     */
    private static class ProcessingResult {
        long checksum;
        int dataSize;
        String status;
    }

    /**
     * Main method to run the server
     */
    public static void main(String[] args) {
        int port = DEFAULT_PORT;
        String keystorePath = "server.keystore";
        String keystorePassword = "changeit";

        // Parse command line arguments
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--port":
                case "-p":
                    if (i + 1 < args.length) {
                        port = Integer.parseInt(args[++i]);
                    }
                    break;
                case "--keystore":
                case "-k":
                    if (i + 1 < args.length) {
                        keystorePath = args[++i];
                    }
                    break;
                case "--password":
                case "-pw":
                    if (i + 1 < args.length) {
                        keystorePassword = args[++i];
                    }
                    break;
                case "--help":
                case "-h":
                    printUsage();
                    return;
            }
        }

        BenchServer server = new BenchServer(port);

        // Add shutdown hook for graceful shutdown
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.out.println("\nShutdown signal received...");
            server.stop();
        }));

        try {
            server.start(keystorePath, keystorePassword);
        } catch (Exception e) {
            System.err.println("Failed to start server: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }

    private static void printUsage() {
        System.out.println("Usage: java server.BenchServer [OPTIONS]");
        System.out.println("\nOptions:");
        System.out.println("  -p, --port <port>           Server port (default: 8443)");
        System.out.println("  -k, --keystore <path>       Path to keystore file (default: server.keystore)");
        System.out.println("  -pw, --password <password>  Keystore password (default: changeit)");
        System.out.println("  -h, --help                  Display this help message");
        System.out.println("\nExample:");
        System.out.println("  java server.BenchServer --port 8443 --keystore server.keystore --password mypassword");
    }
}
