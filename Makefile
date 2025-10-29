# SOURCE: https://github.com/gramineproject/examples/blob/master/openjdk/Makefile
ARCH_LIBDIR ?= /lib/$(shell $(CC) -dumpmachine)
# Find Java installation root by locating java executable and removing /bin/java suffix
# Use realpath to resolve symlinks and ensure consistent paths in manifest
JAVA_HOME = /usr/java/graalvm
JAVAC = $(JAVA_HOME)/bin/javac
NATIVE_IMAGE = $(JAVA_HOME)/bin/native-image
APP_NAME ?= bench

# Build static native images (requires musl libc: apt install musl-tools zlib1g-dev:amd64)
# Set to 1 for static builds with musl, 0 for dynamic linking (default)
STATIC_NATIVE ?= 0

# Default enclave size (can be overridden by user)
ifeq ($(STATIC_NATIVE),1)
ENCLAVE_SIZE ?= 16G
else
ENCLAVE_SIZE ?= 8G
endif

# SGX signing key - can be overridden by user
SGX_SIGNER_KEY ?= $(HOME)/.config/gramine/enclave-key.pem

ifeq ($(DEBUG),1)
GRAMINE_LOG_LEVEL = debug
else
GRAMINE_LOG_LEVEL = error
endif

TARGET_DIR = target
CLASSES_DIR = $(TARGET_DIR)/classes
BIN_DIR = $(TARGET_DIR)/bin

SERVER_SOURCE_FILES := $(shell find src/server -name '*.java')
CLIENT_SOURCE_FILES := $(shell find src/client -name '*.java')

SERVER_CLASS_FILES = $(CLASSES_DIR)/com/benchmark/gramine/enclave/BenchServer.class
CLIENT_CLASS_FILES = $(CLASSES_DIR)/com/benchmark/gramine/host/BenchClient.class

# Native image targets (only for native-bench)
NATIVE_SERVER = $(BIN_DIR)/BenchServer
NATIVE_CLIENT = $(BIN_DIR)/BenchClient

# Compile server Java files
$(CLASSES_DIR)/com/benchmark/gramine/enclave/BenchServer.class: $(SERVER_SOURCE_FILES) | $(CLASSES_DIR)
	@echo "-- Compiling server sources --"
	$(JAVAC) -d $(CLASSES_DIR) $(SERVER_SOURCE_FILES)

# Compile client Java files
$(CLASSES_DIR)/com/benchmark/gramine/host/BenchClient.class: $(CLIENT_SOURCE_FILES) | $(CLASSES_DIR)
	@echo "-- Compiling client sources --"
	$(JAVAC) -d $(CLASSES_DIR) $(CLIENT_SOURCE_FILES)

$(TARGET_DIR):
	@echo "-- Creating target directory: $(TARGET_DIR) --"
	@mkdir -p $(TARGET_DIR)

$(CLASSES_DIR):
	@echo "-- Creating classes directory: $(CLASSES_DIR) --"
	@mkdir -p $(CLASSES_DIR)

$(BIN_DIR):
	@echo "-- Creating bin directory: $(BIN_DIR) --"
	@mkdir -p $(BIN_DIR)

.PHONY: all
all: $(SERVER_CLASS_FILES) $(CLIENT_CLASS_FILES) ${APP_NAME}.manifest
ifeq ($(SGX),1)
all: ${APP_NAME}.manifest.sgx java.sig
endif
# Build native images for any native-bench variant
ifneq (,$(findstring native-bench,$(APP_NAME)))
all: $(NATIVE_SERVER) $(NATIVE_CLIENT)
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

# Native image targets - Static (musl) or Dynamic (glibc)
$(NATIVE_SERVER): $(SERVER_CLASS_FILES) | $(BIN_DIR)
	@echo "-- Building native image for BenchServer (static=$(STATIC_NATIVE)) --"
ifeq ($(STATIC_NATIVE),1)
	@echo "-- Using musl-gcc for static build --"
		$(NATIVE_IMAGE) -cp $(CLASSES_DIR) \
			-o $(NATIVE_SERVER) \
			--no-fallback \
			--static --libc=musl \
			--native-compiler-path=/usr/bin/musl-gcc \
			--native-compiler-options=-no-pie \
			--native-compiler-options=-L/usr/local/musl/lib \
			--native-compiler-options=-Wl,-z,max-page-size=4096 \
			--native-compiler-options=-Wl,-z,common-page-size=4096 \
			-H:CLibraryPath=/usr/local/musl/lib \
			-H:+ReportExceptionStackTraces \
			-H:-UseCompressedReferences \
			-R:MaxHeapSize=2g \
			BenchServer
else
	@echo "-- Using gcc for dynamic build with glibc --"
		$(NATIVE_IMAGE) -cp $(CLASSES_DIR) \
			-o $(NATIVE_SERVER) \
			--no-fallback \
			--native-compiler-options=-Wl,-z,max-page-size=4096 \
			--native-compiler-options=-Wl,-z,common-page-size=4096 \
			-H:+ReportExceptionStackTraces \
			-H:-UseCompressedReferences \
			-R:MaxHeapSize=2g \
			BenchServer
endif

$(NATIVE_CLIENT): $(CLIENT_CLASS_FILES) | $(BIN_DIR)
	@echo "-- Building native image for BenchClient (static=$(STATIC_NATIVE)) --"
ifeq ($(STATIC_NATIVE),1)
	@echo "-- Using musl-gcc for static build --"
		$(NATIVE_IMAGE) -cp $(CLASSES_DIR) \
			-o $(NATIVE_CLIENT) \
			--no-fallback \
			--static --libc=musl \
			--native-compiler-path=/usr/bin/musl-gcc \
			--native-compiler-options=-no-pie \
			--native-compiler-options=-L/usr/local/musl/lib \
			--native-compiler-options=-Wl,-z,max-page-size=4096 \
			--native-compiler-options=-Wl,-z,common-page-size=4096 \
			-H:CLibraryPath=/usr/local/musl/lib \
			-H:+ReportExceptionStackTraces \
			-H:-UseCompressedReferences \
			-R:MaxHeapSize=2g \
			BenchClient
else
	@echo "-- Using gcc for dynamic build with glibc --"
		$(NATIVE_IMAGE) -cp $(CLASSES_DIR) \
			-o $(NATIVE_CLIENT) \
			--no-fallback \
			--native-compiler-options=-Wl,-z,max-page-size=4096 \
			--native-compiler-options=-Wl,-z,common-page-size=4096 \
			-H:+ReportExceptionStackTraces \
			-H:-UseCompressedReferences \
			-R:MaxHeapSize=2g \
			BenchClient
endif

.PHONY: native
native: $(NATIVE_SERVER) $(NATIVE_CLIENT)

# Manifest generation - depends on native images for native-bench variants
ifneq (,$(findstring native-bench,$(APP_NAME)))
${APP_NAME}.manifest: ${APP_NAME}.manifest.template $(NATIVE_SERVER) $(NATIVE_CLIENT)
else
${APP_NAME}.manifest: ${APP_NAME}.manifest.template
endif
	@echo "-- Generating Gramine manifest from template --"
	STATIC_NATIVE=$(STATIC_NATIVE) gramine-manifest \
		-Dlog_level=$(GRAMINE_LOG_LEVEL) \
		-Darch_libdir=$(ARCH_LIBDIR) \
		-Djava_home=$(JAVA_HOME) \
		-Denclave_size=$(ENCLAVE_SIZE) \
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
	fi
	@echo "-- Generating SGX signing key at $(SGX_SIGNER_KEY) --"
	@mkdir -p $(dir $(SGX_SIGNER_KEY))
	@gramine-sgx-gen-private-key $(SGX_SIGNER_KEY)

.PHONY: clean
clean:
	@echo "-- Cleaning build artifacts --"
	$(RM) *.token *.sig *.manifest.sgx *.manifest
	$(RM) -r $(TARGET_DIR)
	$(RM) $(NATIVE_SERVER) $(NATIVE_CLIENT)
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
