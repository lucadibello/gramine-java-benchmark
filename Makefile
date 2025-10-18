# SOURCE: https://github.com/gramineproject/examples/blob/master/openjdk/Makefile

ARCH_LIBDIR ?= /lib/$(shell $(CC) -dumpmachine)
# Find Java installation root by locating java executable and removing /bin/java suffix
# Use realpath to resolve symlinks and ensure consistent paths in manifest
JAVA_HOME = /usr/local/sdkman/candidates/java/21-tem
APP_NAME = bench

# SGX signing key - can be overridden by user
SGX_SIGNER_KEY ?= $(HOME)/.config/gramine/enclave-key.pem

ifeq ($(DEBUG),1)
GRAMINE_LOG_LEVEL = debug
else
GRAMINE_LOG_LEVEL = error
endif

TARGET_DIR = target
CLASSES_DIR = $(TARGET_DIR)/classes

SOURCE_FILES = \
	src/hello_world/HelloWorld.java

SERVER_SOURCE_FILES = \
	src/server/BenchServer.java

CLIENT_SOURCE_FILES = \
	src/client/BenchClient.java

CLASS_FILES = $(patsubst src/%.java,$(CLASSES_DIR)/%.class,$(SOURCE_FILES))
SERVER_CLASS_FILES = $(patsubst src/%.java,$(CLASSES_DIR)/%.class,$(SERVER_SOURCE_FILES))
CLIENT_CLASS_FILES = $(patsubst src/%.java,$(CLASSES_DIR)/%.class,$(CLIENT_SOURCE_FILES))

$(CLASSES_DIR)/%.class: src/%.java | $(CLASSES_DIR)
	@echo "-- Compiling Java source: $< --"
	javac -d $(CLASSES_DIR) -cp $(CLASSES_DIR) $<

$(TARGET_DIR):
	@echo "-- Creating target directory: $(TARGET_DIR) --"
	@mkdir -p $(TARGET_DIR)

$(CLASSES_DIR):
	@echo "-- Creating classes directory: $(CLASSES_DIR) --"
	@mkdir -p $(CLASSES_DIR)

.PHONY: all
all: $(CLASS_FILES) $(SERVER_CLASS_FILES) $(CLIENT_CLASS_FILES) ${APP_NAME}.manifest
ifeq ($(SGX),1)
all: ${APP_NAME}.manifest.sgx java.sig
endif

.PHONY: server
server: $(SERVER_CLASS_FILES)

.PHONY: client
client: $(CLIENT_CLASS_FILES)

.PHONY: certs
certs:
	@echo "-- Generating TLS certificates --"
	@chmod +x tools/generate-certs.sh
	@./tools/generate-certs.sh

${APP_NAME}.manifest: ${APP_NAME}.manifest.template
	@echo "-- Generating Gramine manifest from template --"
	gramine-manifest \
		-Dlog_level=$(GRAMINE_LOG_LEVEL) \
		-Darch_libdir=$(ARCH_LIBDIR) \
		-Djava_home=$(JAVA_HOME) \
		-Dentrypoint="$(realpath $(shell sh -c "command -v java"))" \
		$< >$@

# Make on Ubuntu <= 20.04 doesn't support "Rules with Grouped Targets" (`&:`),
# for details on this workaround see
# https://github.com/gramineproject/gramine/blob/e8735ea06c/CI-Examples/helloworld/Makefile
${APP_NAME}.manifest.sgx java.sig: sgx_sign
	@:

.INTERMEDIATE: sgx_sign
sgx_sign: ${APP_NAME}.manifest $(SGX_SIGNER_KEY)
	@echo "-- Signing SGX enclave with key: $(SGX_SIGNER_KEY) --"
	gramine-sgx-sign \
		--manifest $< \
		--output $<.sgx

# Generate SGX signing key if it doesn't exist
$(SGX_SIGNER_KEY):
	@if [ -f "$(SGX_SIGNER_KEY)" ]; then \
		echo "SGX signing key already exists at $(SGX_SIGNER_KEY), skipping generation..."; \
		exit 0; \
	fi; \
	@echo "-- Generating SGX signing key at $(SGX_SIGNER_KEY) --"
	mkdir -p $(dir $(SGX_SIGNER_KEY)); \
	gramine-sgx-gen-private-key $(SGX_SIGNER_KEY)

.PHONY: clean
clean:
	@echo "-- Cleaning build artifacts --"
	$(RM) *.token *.sig *.manifest.sgx *.manifest
	$(RM) -r $(TARGET_DIR)
	@echo "-- Clean complete --"

.PHONY: clean-certs
clean-certs:
	@echo "-- Removing TLS certificates --"
	$(RM) server.keystore client.truststore server.cer

.PHONY: clean-sgx-key
clean-sgx-key:
	@echo "WARNING: Removing SGX signing key at $(SGX_SIGNER_KEY)"
	@echo "This key may be shared across multiple Gramine projects!"
	@$(RM) $(SGX_SIGNER_KEY)

.PHONY: run
run:
	gramine-sgx ${APP_NAME}

.PHONY: run-server
run-server: server certs
	@echo "-- Running BenchServer --"
	java -cp $(CLASSES_DIR) server.BenchServer

.PHONY: run-server-sgx
run-server-sgx:
	@echo "-- Running BenchServer in SGX --"
	gramine-sgx ${APP_NAME} -cp /app/classes server.BenchServer

.PHONY: run-client
run-client: client certs
	@echo "-- Running BenchClient --"
	java -cp $(CLASSES_DIR) client.BenchClient

.PHONY: distclean
distclean: clean
	@echo "-- Deep clean complete --"
