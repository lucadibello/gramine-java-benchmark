#!/bin/bash

# Script to generate TLS certificates for BenchServer and BenchClient
# This creates a self-signed certificate authority and certificates for testing

set -e

# Configuration
VALIDITY_DAYS=365
KEY_SIZE=2048
KEYSTORE_PASSWORD="changeit"
SERVER_KEYSTORE="server.keystore"
CLIENT_TRUSTSTORE="client.truststore"
SERVER_ALIAS="benchserver"

echo "=== Generating TLS Certificates for BenchServer ==="
echo ""

# Clean up old certificates
echo "Cleaning up old certificates..."
rm -f ${SERVER_KEYSTORE} ${CLIENT_TRUSTSTORE} server.cer

# Generate server keystore with self-signed certificate
echo "Generating server keystore..."
keytool -genkeypair \
    -alias ${SERVER_ALIAS} \
    -keyalg RSA \
    -keysize ${KEY_SIZE} \
    -validity ${VALIDITY_DAYS} \
    -keystore ${SERVER_KEYSTORE} \
    -storepass ${KEYSTORE_PASSWORD} \
    -keypass ${KEYSTORE_PASSWORD} \
    -dname "CN=localhost, OU=Development, O=BenchServer, L=City, ST=State, C=US" \
    -ext "SAN=dns:localhost,ip:127.0.0.1"

echo "Server keystore created: ${SERVER_KEYSTORE}"

# Export server certificate
echo "Exporting server certificate..."
keytool -exportcert \
    -alias ${SERVER_ALIAS} \
    -keystore ${SERVER_KEYSTORE} \
    -storepass ${KEYSTORE_PASSWORD} \
    -file server.cer

echo "Server certificate exported: server.cer"

# Create client truststore and import server certificate
echo "Creating client truststore..."
keytool -importcert \
    -alias ${SERVER_ALIAS} \
    -file server.cer \
    -keystore ${CLIENT_TRUSTSTORE} \
    -storepass ${KEYSTORE_PASSWORD} \
    -noprompt

echo "Client truststore created: ${CLIENT_TRUSTSTORE}"

# Clean up temporary files
rm -f server.cer

echo ""
echo "=== Certificate Generation Complete ==="
echo ""
echo "Files created:"
echo "  - ${SERVER_KEYSTORE}    (for server)"
echo "  - ${CLIENT_TRUSTSTORE}  (for client)"
echo ""
echo "Password: ${KEYSTORE_PASSWORD}"
echo ""
echo "To verify the keystore, run:"
echo "  keytool -list -v -keystore ${SERVER_KEYSTORE} -storepass ${KEYSTORE_PASSWORD}"
echo ""
echo "To verify the truststore, run:"
echo "  keytool -list -v -keystore ${CLIENT_TRUSTSTORE} -storepass ${KEYSTORE_PASSWORD}"
echo ""
