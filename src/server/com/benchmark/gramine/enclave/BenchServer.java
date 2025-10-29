package com.benchmark.gramine.enclave;

import com.benchmark.gramine.enclave.dp.BinaryAggregationTree;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLServerSocketFactory;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * TLS server exposing a Binary Aggregation Tree service to the benchmark client.
 */
public final class BenchServer {

    private static final int DEFAULT_PORT = 8443;
    private static final int THREAD_POOL_SIZE = 16;
    private static final String KEYSTORE_TYPE = "JKS";
    private static final String TLS_PROTOCOL = "TLSv1.2";

    private static final String CMD_INIT = "INIT";
    private static final String CMD_ADD = "ADD";
    private static final String CMD_GET = "GET";
    private static final String CMD_QUIT = "QUIT";

    private final int port;
    private final ExecutorService executor;
    private final AggregationContext aggregationContext;
    private volatile boolean running;
    private SSLServerSocket serverSocket;

    public BenchServer(int port) {
        this.port = port;
        this.executor = Executors.newFixedThreadPool(THREAD_POOL_SIZE);
        this.aggregationContext = new AggregationContext();
        this.running = false;
    }

    private SSLContext createSSLContext(String keystorePath, String keystorePassword) throws Exception {
        KeyStore keyStore = KeyStore.getInstance(KEYSTORE_TYPE);
        try (FileInputStream fis = new FileInputStream(keystorePath)) {
            keyStore.load(fis, keystorePassword.toCharArray());
        }

        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
            KeyManagerFactory.getDefaultAlgorithm()
        );
        kmf.init(keyStore, keystorePassword.toCharArray());

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm()
        );
        tmf.init(keyStore);

        SSLContext sslContext = SSLContext.getInstance(TLS_PROTOCOL);
        sslContext.init(kmf.getKeyManagers(), tmf.getTrustManagers(), new SecureRandom());
        return sslContext;
    }

    public void start(String keystorePath, String keystorePassword) throws Exception {
        SSLContext sslContext = createSSLContext(keystorePath, keystorePassword);
        SSLServerSocketFactory factory = sslContext.getServerSocketFactory();
        serverSocket = (SSLServerSocket) factory.createServerSocket(port);
        serverSocket.setEnabledProtocols(new String[] { TLS_PROTOCOL });
        running = true;
        System.out.println("Binary aggregation server listening on port " + port);

        while (running) {
            try {
                SSLSocket clientSocket = (SSLSocket) serverSocket.accept();
                executor.submit(new ClientHandler(clientSocket, aggregationContext));
            } catch (IOException ioe) {
                if (running) {
                    System.err.println("Failed to accept client connection: " + ioe.getMessage());
                }
            }
        }
    }

    public void stop() {
        running = false;
        try {
            if (serverSocket != null && !serverSocket.isClosed()) {
                serverSocket.close();
            }
        } catch (IOException ioe) {
            System.err.println("Failed to close server socket: " + ioe.getMessage());
        }
        executor.shutdown();
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException ie) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
        System.out.println("Server stopped");
    }

    public static void main(String[] args) {
        int port = DEFAULT_PORT;
        String keystorePath = "server.keystore";
        String keystorePassword = "changeit";

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
                    printUsage();
                    return;
                default:
                    System.err.println("Unknown argument: " + args[i]);
                    printUsage();
                    return;
            }
        }

        BenchServer server = new BenchServer(port);
        Runtime.getRuntime().addShutdownHook(new Thread(server::stop));

        try {
            server.start(keystorePath, keystorePassword);
        } catch (Exception e) {
            System.err.println("Server failed: " + e.getMessage());
            e.printStackTrace(System.err);
            server.stop();
            System.exit(1);
        }
    }

    private static void printUsage() {
        System.out.println("Usage: java com.benchmark.gramine.enclave.BenchServer [options]");
        System.out.println("  -p, --port <port>          TLS port (default: 8443)");
        System.out.println("  -k, --keystore <path>      Path to JKS keystore (default: server.keystore)");
        System.out.println("  -pw, --password <password> Keystore password (default: changeit)");
        System.out.println("  --help                     Show this help message");
    }

    private static final class ClientHandler implements Runnable {
        private final SSLSocket socket;
        private final AggregationContext context;

        private ClientHandler(SSLSocket socket, AggregationContext context) {
            this.socket = socket;
            this.context = context;
        }

        @Override
        public void run() {
            String remote = socket.getInetAddress() + ":" + socket.getPort();
            System.out.println("Client connected: " + remote);
            try (SSLSocket client = socket;
                 BufferedReader reader = new BufferedReader(new InputStreamReader(client.getInputStream()));
                 BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(client.getOutputStream()))) {
                writer.write("READY\n");
                writer.flush();

                String line;
                while ((line = reader.readLine()) != null) {
                    line = line.trim();
                    if (line.isEmpty()) {
                        continue;
                    }
                    handleCommand(line, writer);
                }
            } catch (IOException ioe) {
                System.err.println("Connection error: " + ioe.getMessage());
            } finally {
                System.out.println("Client disconnected: " + remote);
            }
        }

        private void handleCommand(String line, BufferedWriter writer) throws IOException {
            String[] parts = line.split("\\|");
            String command = parts[0].trim().toUpperCase(Locale.ROOT);
            switch (command) {
                case CMD_INIT:
                    handleInit(parts, writer);
                    break;
                case CMD_ADD:
                    handleAdd(parts, writer);
                    break;
                case CMD_GET:
                    handleGet(writer);
                    break;
                case CMD_QUIT:
                    writer.write("BYE\n");
                    writer.flush();
                    socket.close();
                    break;
                default:
                    sendError(writer, "Unknown command: " + command);
            }
        }

        private void handleInit(String[] parts, BufferedWriter writer) throws IOException {
            if (parts.length < 3) {
                sendError(writer, "INIT requires size and sigma");
                return;
            }
            try {
                int size = Integer.parseInt(parts[1]);
                double sigma = Double.parseDouble(parts[2]);
                context.init(size, sigma);
                writer.write("OK\n");
                writer.flush();
            } catch (NumberFormatException nfe) {
                sendError(writer, "Invalid numeric parameter in INIT: " + nfe.getMessage());
            } catch (IllegalArgumentException iae) {
                sendError(writer, iae.getMessage());
            }
        }

        private void handleAdd(String[] parts, BufferedWriter writer) throws IOException {
            if (parts.length < 2) {
                sendError(writer, "ADD requires a value");
                return;
            }
            try {
                double value = Double.parseDouble(parts[1]);
                double sum = context.add(value);
                writer.write(String.format(Locale.US, "SUM|%.12f%n", sum));
                writer.flush();
            } catch (NumberFormatException nfe) {
                sendError(writer, "Invalid numeric parameter in ADD: " + nfe.getMessage());
            } catch (IllegalStateException | IllegalArgumentException ex) {
                sendError(writer, ex.getMessage());
            }
        }

        private void handleGet(BufferedWriter writer) throws IOException {
            try {
                double sum = context.getSum();
                writer.write(String.format(Locale.US, "SUM|%.12f%n", sum));
                writer.flush();
            } catch (IllegalStateException ex) {
                sendError(writer, ex.getMessage());
            }
        }

        private void sendError(BufferedWriter writer, String message) throws IOException {
            writer.write("ERROR|" + message + "\n");
            writer.flush();
        }
    }

    private static final class AggregationContext {
        private BinaryAggregationTree tree;
        private int capacity;
        private int index;
        private double lastPrivateSum;

        synchronized void init(int size, double sigma) {
            if (size <= 0) {
                throw new IllegalArgumentException("Tree size must be positive");
            }
            if (sigma < 0.0) {
                throw new IllegalArgumentException("Sigma must be non-negative");
            }
            tree = new BinaryAggregationTree(size, sigma);
            capacity = size;
            index = 0;
            lastPrivateSum = 0.0;
        }

        synchronized double add(double value) {
            ensureInitialised();
            if (index >= capacity) {
                throw new IllegalStateException("Binary aggregation tree capacity exceeded");
            }
            lastPrivateSum = tree.addToTree(index, value);
            index++;
            return lastPrivateSum;
        }

        synchronized double getSum() {
            ensureInitialised();
            return lastPrivateSum;
        }

        private void ensureInitialised() {
            if (tree == null) {
                throw new IllegalStateException("Binary aggregation tree not initialised");
            }
        }
    }
}
