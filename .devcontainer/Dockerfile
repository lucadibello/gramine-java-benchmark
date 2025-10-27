# syntax=docker/dockerfile:1.4

FROM gramineproject/gramine:stable-noble

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG REMOTE_USER=dev
ARG REMOTE_GROUP=${REMOTE_USER}
ARG REMOTE_UID=1000
ARG REMOTE_GID=${REMOTE_UID}
ARG REMOTE_HOME=/home/${REMOTE_USER}

ARG GRADLE_VERSION=8.6
ARG MAVEN_VERSION=3.9.6
ARG NEOVIM_ARCHIVE_URL=https://github.com/neovim/neovim/releases/download/nightly/nvim-linux64.tar.gz
ARG GRAALVM_ARCHIVE_URL=https://download.oracle.com/graalvm/21/latest/graalvm-jdk-21_linux-x64_bin.tar.gz

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    JAVA_HOME=/usr/java/graalvm \
    GRAALVM_HOME=/usr/java/graalvm \
    PATH=/usr/java/graalvm/bin:/opt/gradle/bin:/opt/maven/bin:/opt/nvim/bin:${PATH} \
    NVIM_LISTEN_ADDRESS=127.0.0.1:6666 \
    DEVCONTAINER_USER=${REMOTE_USER} \
    REMOTE_USER=${REMOTE_USER} \
    REMOTE_HOME=${REMOTE_HOME}

# Base tooling and build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        autoconf \
        automake \
        build-essential \
        ca-certificates \
        cmake \
        curl \
        fd-find \
        g++ \
        gcc \
        gettext \
        git \
        git-lfs \
        gnupg2 \
        jq \
        less \
        libtool \
        libtool-bin \
        locales \
        make \
        musl-dev \
        musl-tools \
        ninja-build \
        openssh-client \
        openssh-server \
        openssl \
        procps \
        pkg-config \
        python3 \
        python3-pip \
        python3-setuptools \
        python3-venv \
        python3-wheel \
        ripgrep \
        rsync \
        sudo \
        tar \
        tmux \
        tree \
        unzip \
        wget \
        xz-utils \
        zlib1g-dev \
        zsh \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd

# Locale configuration
RUN sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen en_US.UTF-8

# Create non-root user with passwordless sudo
RUN GROUP_NAME="${REMOTE_GROUP}" \
    && EXISTING_GID_GROUP="$(getent group "${REMOTE_GID}" | cut -d: -f1 || true)" \
    && if [ -n "${EXISTING_GID_GROUP}" ]; then \
        GROUP_NAME="${EXISTING_GID_GROUP}"; \
    elif ! getent group "${REMOTE_GROUP}" >/dev/null; then \
        groupadd --gid "${REMOTE_GID}" "${REMOTE_GROUP}"; \
    fi \
    && if ! id -u "${REMOTE_USER}" >/dev/null 2>&1; then \
        useradd --create-home --shell /usr/bin/zsh --uid "${REMOTE_UID}" --gid "${GROUP_NAME}" "${REMOTE_USER}"; \
    else \
        usermod --gid "${GROUP_NAME}" "${REMOTE_USER}"; \
    fi \
    && usermod -aG sudo "${REMOTE_USER}" \
    && echo "${REMOTE_USER} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/90-"${REMOTE_USER}" \
    && chmod 0440 /etc/sudoers.d/90-"${REMOTE_USER}" \
    && echo "${GROUP_NAME}" > /etc/devcontainer-group

# SSH server configuration
RUN mkdir -p /var/run/sshd \
    && ssh-keygen -A \
    && sed -i 's/^#\?Port .*/Port 2222/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?UsePAM .*/UsePAM yes/' /etc/ssh/sshd_config \
    && grep -qxF 'AllowTcpForwarding yes' /etc/ssh/sshd_config || echo 'AllowTcpForwarding yes' >> /etc/ssh/sshd_config \
    && grep -qxF 'X11Forwarding yes' /etc/ssh/sshd_config || echo 'X11Forwarding yes' >> /etc/ssh/sshd_config

# Ensure user directories exist with correct permissions
RUN TARGET_GROUP="$(cat /etc/devcontainer-group 2>/dev/null || echo "${REMOTE_GROUP}")" \
    && mkdir -p "${REMOTE_HOME}"/.cache "${REMOTE_HOME}"/.ssh \
    && chown -R "${REMOTE_USER}:${TARGET_GROUP}" "${REMOTE_HOME}"/.cache "${REMOTE_HOME}"/.ssh \
    && chmod 700 "${REMOTE_HOME}"/.ssh

# Install GraalVM and native-image tooling
RUN curl -fsSL "${GRAALVM_ARCHIVE_URL}" -o /tmp/graalvm.tar.gz \
    && mkdir -p /usr/java \
    && tar -xf /tmp/graalvm.tar.gz -C /usr/java \
    && rm /tmp/graalvm.tar.gz \
    && GRAAL_DIR="$(find /usr/java -maxdepth 1 -mindepth 1 -type d -name 'graalvm*' | head -n 1)" \
    && mv "${GRAAL_DIR}" /usr/java/graalvm \
    && /usr/java/graalvm/bin/gu install --no-progress native-image \
    && ln -sf /usr/java/graalvm/bin/java /usr/local/bin/java \
    && ln -sf /usr/java/graalvm/bin/javac /usr/local/bin/javac

# Install Gradle
RUN curl -fsSL "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" -o /tmp/gradle.zip \
    && unzip -q /tmp/gradle.zip -d /opt \
    && rm /tmp/gradle.zip \
    && mv /opt/gradle-"${GRADLE_VERSION}" /opt/gradle \
    && ln -sf /opt/gradle/bin/gradle /usr/local/bin/gradle

# Install Maven
RUN MAVEN_MAJOR="$(echo "${MAVEN_VERSION}" | cut -d. -f1)" \
    && curl -fsSL "https://dlcdn.apache.org/maven/maven-${MAVEN_MAJOR}/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz" -o /tmp/maven.tar.gz \
    && tar -xf /tmp/maven.tar.gz -C /opt \
    && rm /tmp/maven.tar.gz \
    && mv /opt/apache-maven-"${MAVEN_VERSION}" /opt/maven \
    && ln -sf /opt/maven/bin/mvn /usr/local/bin/mvn

# Install Neovim 0.11 (nightly channel) and Python support
RUN curl -fsSL "${NEOVIM_ARCHIVE_URL}" -o /tmp/nvim.tar.gz \
    && tar -xf /tmp/nvim.tar.gz -C /opt \
    && rm /tmp/nvim.tar.gz \
    && mv /opt/nvim-linux64 /opt/nvim \
    && ln -sf /opt/nvim/bin/nvim /usr/local/bin/nvim
RUN python3 -m pip install --no-cache-dir pynvim

# Provide entrypoint that keeps the headless Neovim server alive
COPY .devcontainer/devcontainer-entrypoint.sh /usr/local/bin/devcontainer-entrypoint
RUN chmod +x /usr/local/bin/devcontainer-entrypoint

# Install Neovim configuration for the remote user
RUN TARGET_GROUP="$(cat /etc/devcontainer-group 2>/dev/null || echo "${REMOTE_GROUP}")" \
    && git clone https://github.com/lucadibello/neovim.git /tmp/nvim-config \
    && mkdir -p "${REMOTE_HOME}"/.config \
    && rm -rf "${REMOTE_HOME}"/.config/nvim \
    && cp -a /tmp/nvim-config "${REMOTE_HOME}"/.config/nvim \
    && chown -R "${REMOTE_USER}:${TARGET_GROUP}" "${REMOTE_HOME}"/.config/nvim \
    && rm -rf /tmp/nvim-config

# Install Oh My Zsh for the remote user (non-interactive)
RUN su - "${REMOTE_USER}" -c 'export RUNZSH=no CHSH=no; sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"'

# Ensure cache directory exists for headless Neovim logs
RUN TARGET_GROUP="$(cat /etc/devcontainer-group 2>/dev/null || echo "${REMOTE_GROUP}")" \
    && mkdir -p "${REMOTE_HOME}"/.cache \
    && chown "${REMOTE_USER}:${TARGET_GROUP}" "${REMOTE_HOME}"/.cache

EXPOSE 2222 6666

ENTRYPOINT ["/usr/local/bin/devcontainer-entrypoint"]
