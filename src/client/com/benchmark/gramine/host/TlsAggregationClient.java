package com.benchmark.gramine.host;

import com.benchmark.gramine.common.AggregationService;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
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
import java.util.Objects;

final class TlsAggregationClient implements AggregationService {

    private static final String TRUSTSTORE_TYPE = "JKS";
    private static final String TLS_PROTOCOL = "TLSv1.2";

    private final SSLSocket socket;
    private final BufferedReader reader;
    private final BufferedWriter writer;
    private volatile boolean closed;

    TlsAggregationClient(String host,
                         int port,
                         String truststorePath,
                         String truststorePassword) {
        Objects.requireNonNull(host, "host");
        Objects.requireNonNull(truststorePath, "truststorePath");
        Objects.requireNonNull(truststorePassword, "truststorePassword");
        try {
            SSLContext sslContext = createSSLContext(truststorePath, truststorePassword);
            SSLSocketFactory sslSocketFactory = sslContext.getSocketFactory();
            this.socket = (SSLSocket) sslSocketFactory.createSocket(host, port);
            socket.setEnabledProtocols(new String[] { TLS_PROTOCOL });
            this.reader = new BufferedReader(new InputStreamReader(socket.getInputStream()));
            this.writer = new BufferedWriter(new OutputStreamWriter(socket.getOutputStream()));
            String readiness = reader.readLine();
            if (readiness == null || !"READY".equalsIgnoreCase(readiness.trim())) {
                throw new IllegalStateException("Expected READY from server, got: " + readiness);
            }
            this.closed = false;
        } catch (Exception ex) {
            throw new IllegalStateException("Failed to establish TLS connection: " + ex.getMessage(), ex);
        }
    }

    private static SSLContext createSSLContext(String truststorePath, String truststorePassword) throws Exception {
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

    @Override
    public synchronized void initBinaryAggregation(int n, double sigma) {
        ensureOpen();
        String command = String.format(Locale.US, "INIT|%d|%.12f", n, sigma);
        String response = sendCommand(command);
        if (!"OK".equalsIgnoreCase(response)) {
            throw new IllegalStateException("Server rejected INIT: " + response);
        }
    }

    @Override
    public synchronized double addToBinaryAggregation(double value) {
        ensureOpen();
        String command = String.format(Locale.US, "ADD|%.12f", value);
        String response = sendCommand(command);
        if (response == null || !response.startsWith("SUM|")) {
            throw new IllegalStateException("Unexpected response to ADD: " + response);
        }
        return parseSum(response);
    }

    @Override
    public synchronized double getBinaryAggregationSum() {
        ensureOpen();
        String response = sendCommand("GET");
        if (response == null || !response.startsWith("SUM|")) {
            throw new IllegalStateException("Unexpected response to GET: " + response);
        }
        return parseSum(response);
    }

    private String sendCommand(String command) {
        try {
            writer.write(command);
            writer.write('\n');
            writer.flush();
            String response = reader.readLine();
            if (response == null) {
                throw new IllegalStateException("Server closed connection unexpectedly");
            }
            if (response.startsWith("ERROR|")) {
                throw new IllegalStateException("Server error: " + response.substring("ERROR|".length()));
            }
            return response.trim();
        } catch (IOException ioe) {
            throw new IllegalStateException("I/O failure during command '" + command + "': " + ioe.getMessage(), ioe);
        }
    }

    private static double parseSum(String response) {
        String[] parts = response.split("\\|", 2);
        if (parts.length != 2) {
            throw new IllegalStateException("Cannot parse SUM response: " + response);
        }
        try {
            return Double.parseDouble(parts[1]);
        } catch (NumberFormatException nfe) {
            throw new IllegalStateException("Invalid SUM payload: " + response, nfe);
        }
    }

    private void ensureOpen() {
        if (closed) {
            throw new IllegalStateException("Service already closed");
        }
    }

    @Override
    public synchronized void close() {
        if (closed) {
            return;
        }
        closed = true;
        try {
            try {
                writer.write(CMD_QUIT);
                writer.write('\n');
                writer.flush();
            } catch (IOException ignored) {
                // Connection might already be gone.
            }
            socket.close();
        } catch (IOException ignored) {
            // Best effort shutdown.
        }
    }

    private static final String CMD_QUIT = "QUIT";
}
