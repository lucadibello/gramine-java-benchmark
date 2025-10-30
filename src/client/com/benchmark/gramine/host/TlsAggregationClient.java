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
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * TLS-backed implementation of the aggregation service. The Teaclave benchmark performs ECALLs
 * concurrently, so to mimic that behaviour we establish a dedicated TLS session per worker thread.
 * This avoids serialising every request on a single socket and allows real parallel scaling.
 */
final class TlsAggregationClient implements AggregationService {

    private static final String TRUSTSTORE_TYPE = "JKS";
    private static final String TLS_PROTOCOL = "TLSv1.2";
    private static final String CMD_QUIT = "QUIT";

    private final String host;
    private final int port;
    private final SSLSocketFactory socketFactory;

    private final CopyOnWriteArrayList<TlsSession> openSessions = new CopyOnWriteArrayList<>();
    private final TlsSession controlSession;
    private volatile VariantSessionPool currentPool;

    private volatile boolean closed;

    TlsAggregationClient(String host,
                         int port,
                         String truststorePath,
                         String truststorePassword) {
        this.host = Objects.requireNonNull(host, "host");
        this.port = port;
        Objects.requireNonNull(truststorePath, "truststorePath");
        Objects.requireNonNull(truststorePassword, "truststorePassword");
        try {
            SSLContext sslContext = createSSLContext(truststorePath, truststorePassword);
            this.socketFactory = sslContext.getSocketFactory();
            this.closed = false;
            this.controlSession = registerSession(createSession());
            this.currentPool = null;
        } catch (Exception ex) {
            throw new IllegalStateException("Failed to initialise TLS client: " + ex.getMessage(), ex);
        }
    }

    private TlsSession registerSession(TlsSession session) {
        openSessions.add(session);
        return session;
    }

    private TlsSession createSession() {
        ensureOpen();
        try {
            SSLSocket socket = (SSLSocket) socketFactory.createSocket(host, port);
            socket.setEnabledProtocols(new String[]{TLS_PROTOCOL});
            return new TlsSession(socket);
        } catch (IOException ioe) {
            throw new IllegalStateException("Failed to open TLS session: " + ioe.getMessage(), ioe);
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
    public void initBinaryAggregation(int n, double sigma) {
        ensureOpen();
        VariantSessionPool previousPool = currentPool;
        if (previousPool != null) {
            previousPool.closeAll();
        }
        VariantSessionPool nextPool = new VariantSessionPool();
        String command = String.format(Locale.US, "INIT|%d|%.12f", n, sigma);
        String response = controlSession.sendCommand(command);
        if (!"OK".equalsIgnoreCase(response)) {
            nextPool.closeAll();
            throw new IllegalStateException("Server rejected INIT: " + response);
        }
        currentPool = nextPool;
    }

    @Override
    public double addToBinaryAggregation(double value) {
        ensureOpen();
        VariantSessionPool pool = currentPool;
        if (pool == null) {
            throw new IllegalStateException("Binary aggregation not initialised");
        }
        TlsSession session = pool.getOrCreateSession();
        String command = String.format(Locale.US, "ADD|%.12f", value);
        String response = session.sendCommand(command);
        if (response == null || !response.startsWith("SUM|")) {
            throw new IllegalStateException("Unexpected response to ADD: " + response);
        }
        return parseSum(response);
    }

    @Override
    public double getBinaryAggregationSum() {
        ensureOpen();
        String response = controlSession.sendCommand("GET");
        if (response == null || !response.startsWith("SUM|")) {
            throw new IllegalStateException("Unexpected response to GET: " + response);
        }
        VariantSessionPool pool = currentPool;
        if (pool != null) {
            pool.closeAll();
            currentPool = null;
        }
        return parseSum(response);
    }

    @Override
    public void resetBinaryAggregation() {
        ensureOpen();
        VariantSessionPool pool = currentPool;
        if (pool != null) {
            pool.closeAll();
            currentPool = null;
        }
        String response = controlSession.sendCommand("RESET");
        if (!"OK".equalsIgnoreCase(response)) {
            throw new IllegalStateException("Server rejected RESET: " + response);
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
        VariantSessionPool pool = currentPool;
        if (pool != null) {
            pool.closeAll();
            currentPool = null;
        }
        for (TlsSession session : openSessions) {
            session.closeQuietly();
        }
        openSessions.clear();
    }

    private static final class TlsSession {
        private final SSLSocket socket;
        private final BufferedReader reader;
        private final BufferedWriter writer;
        private volatile boolean closed;

        private TlsSession(SSLSocket socket) throws IOException {
            this.socket = socket;
            this.reader = new BufferedReader(new InputStreamReader(socket.getInputStream()));
            this.writer = new BufferedWriter(new OutputStreamWriter(socket.getOutputStream()));
            String readiness = reader.readLine();
            if (readiness == null || !"READY".equalsIgnoreCase(readiness.trim())) {
                try {
                    socket.close();
                } catch (IOException ignored) {
                    // Ignore close failures during handshake.
                }
                throw new IllegalStateException("Expected READY from server, got: " + readiness);
            }
            this.closed = false;
        }

        private String sendCommand(String command) {
            if (closed) {
                throw new IllegalStateException("Session already closed");
            }
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

        private synchronized void closeQuietly() {
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
    }

    private final class VariantSessionPool {
        private final ConcurrentHashMap<Long, TlsSession> sessions = new ConcurrentHashMap<>();
        private final AtomicBoolean closed = new AtomicBoolean(false);

        private TlsSession getOrCreateSession() {
            if (closed.get()) {
                throw new IllegalStateException("Binary aggregation already completed");
            }
            long threadId = Thread.currentThread().getId();
            return sessions.computeIfAbsent(threadId, id -> registerSession(createSession()));
        }

        private void closeAll() {
            if (!closed.compareAndSet(false, true)) {
                return;
            }
            for (TlsSession session : sessions.values()) {
                session.closeQuietly();
            }
            sessions.clear();
        }
    }
}
