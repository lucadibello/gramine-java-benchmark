# syntax=docker/dockerfile:1.4
# FROM gramineproject/gramine:stable-noble
FROM teaclave/teaclave-java-tee-sdk:v0.1.0-ubuntu18.04

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG REMOTE_USER=dev
ARG REMOTE_GROUP=${REMOTE_USER}
ARG REMOTE_UID=1000
ARG REMOTE_GID=${REMOTE_UID}
ARG REMOTE_HOME=/home/${REMOTE_USER}

ARG GIT_EMAIL=lucadibello@proton.me
ARG GIT_NAME="Luca Di Bello"

ARG GRADLE_VERSION=8.6
ARG MAVEN_VERSION=3.9.9
ARG NEOVIM_ARCHIVE_URL=https://github.com/neovim/neovim-releases/releases/download/v0.11.4/nvim-linux-x86_64.tar.gz
ARG GRAALVM_ARCHIVE_URL=https://download.oracle.com/graalvm/21/latest/graalvm-jdk-21_linux-x64_bin.tar.gz
# ARG NODE_VERSION=22.20.0
ARG NODE_VERSION=20.19.5
ARG NODE_ARCH=x64

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    JAVA_HOME=/usr/java/graalvm \
    GRAALVM_HOME=/usr/java/graalvm \
    PATH=/usr/java/graalvm/bin:/opt/gradle/bin:/opt/maven/bin:/opt/nvim/bin:${PATH} \
    NVIM_LISTEN_ADDRESS=127.0.0.1:6666 \
    DEVCONTAINER_USER=${REMOTE_USER} \
    REMOTE_USER=${REMOTE_USER} \
    REMOTE_HOME=${REMOTE_HOME} \
    GIT_NAME=${GIT_NAME} \
    GIT_EMAIL=${GIT_EMAIL}

# Base tooling and build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends software-properties-common \
    && add-apt-repository universe \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        autoconf \
        automake \
        build-essential \
        ca-certificates \
        cmake \
        curl \
        g++ \
        gcc \
        git \
        libtool \
        libtool-bin \
        locales \
        make \
        ninja-build \
        openssh-client \
        openssh-server \
        openssl \
        python3 \
        python3-pip \
        python3-venv \
        sudo \
        tar \
        tmux \
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
    elif getent group "${REMOTE_GROUP}" >/dev/null; then \
        groupmod --gid "${REMOTE_GID}" "${REMOTE_GROUP}"; \
    else \
        groupadd --gid "${REMOTE_GID}" "${REMOTE_GROUP}"; \
    fi \
    && EXISTING_UID_USER="$(getent passwd "${REMOTE_UID}" | cut -d: -f1 || true)" \
    && if ! id -u "${REMOTE_USER}" >/dev/null 2>&1 \
        && [ -n "${EXISTING_UID_USER}" ] \
        && [ "${EXISTING_UID_USER}" != "${REMOTE_USER}" ]; then \
        usermod --login "${REMOTE_USER}" "${EXISTING_UID_USER}"; \
    fi \
    && if id -u "${REMOTE_USER}" >/dev/null 2>&1; then \
        usermod --gid "${GROUP_NAME}" --shell /usr/bin/zsh "${REMOTE_USER}"; \
        CURRENT_UID="$(id -u "${REMOTE_USER}")"; \
        if [ "${CURRENT_UID}" -ne "${REMOTE_UID}" ] \
            && { [ -z "${EXISTING_UID_USER}" ] || [ "${EXISTING_UID_USER}" = "${REMOTE_USER}" ]; }; then \
            usermod --uid "${REMOTE_UID}" "${REMOTE_USER}"; \
        fi; \
        CURRENT_HOME="$(getent passwd "${REMOTE_USER}" | cut -d: -f6)"; \
        if [ "${CURRENT_HOME}" != "${REMOTE_HOME}" ]; then \
            usermod --home "${REMOTE_HOME}" --move-home "${REMOTE_USER}"; \
        fi; \
    else \
        useradd --create-home --shell /usr/bin/zsh --uid "${REMOTE_UID}" --gid "${GROUP_NAME}" "${REMOTE_USER}"; \
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
#RUN TARGET_GROUP="$(cat /etc/devcontainer-group 2>/dev/null || echo "${REMOTE_GROUP}")" \
#    && mkdir -p "${REMOTE_HOME}"/.cache "${REMOTE_HOME}"/.ssh \
#    && chown -R "${REMOTE_USER}:${TARGET_GROUP}" "${REMOTE_HOME}"/.cache "${REMOTE_HOME}"/.ssh \
#    && chmod 700 "${REMOTE_HOME}"/.ssh

# Install GraalVM and native-image tooling
# NOTE: disabled as the image already includes the correct GraalVM image!
#RUN curl -fsSL "${GRAALVM_ARCHIVE_URL}" -o /tmp/graalvm.tar.gz \
#    && mkdir -p /usr/java/graalvm \
#    && tar -xf /tmp/graalvm.tar.gz --strip-components=1 -C /usr/java/graalvm \
#    && rm /tmp/graalvm.tar.gz \
#    && ln -sf /usr/java/graalvm/bin/java /usr/local/bin/java \
#    && ln -sf /usr/java/graalvm/bin/javac /usr/local/bin/javac

# Install Gradle
#RUN curl -fsSL "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" -o /tmp/gradle.zip \
#    && unzip -q /tmp/gradle.zip -d /opt \
#    && rm /tmp/gradle.zip \
#    && mv /opt/gradle-"${GRADLE_VERSION}" /opt/gradle \
#    && ln -sf /opt/gradle/bin/gradle /usr/local/bin/gradle

# Install Maven 
#RUN curl -fsSL "https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz" -o /tmp/maven.tar.gz \
#    && tar -xzf /tmp/maven.tar.gz -C /opt \
#    && rm /tmp/maven.tar.gz \
#    && mv /opt/apache-maven-${MAVEN_VERSION} /opt/maven \
#    && ln -sf /opt/maven/bin/mvn /usr/local/bin/mvn

# Install Neovim 0.11 (nightly channel) and Python support
RUN curl -fsSL "${NEOVIM_ARCHIVE_URL}" -o /tmp/nvim.tar.gz \
    && tar -xf /tmp/nvim.tar.gz -C /opt \
    && rm /tmp/nvim.tar.gz \
    && mv /opt/nvim-linux-x86_64 /opt/nvim \
    && ln -sf /opt/nvim/bin/nvim /usr/local/bin/nvim
# RUN python3 -m pip install --no-cache-dir pynvim

# Install ripgrep
RUN curl -fsSL https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep_14.1.1-1_amd64.deb -o /tmp/ripgrep.deb \
    && dpkg -i /tmp/ripgrep.deb \
    && rm /tmp/ripgrep.deb

# lazygit (binary release)
RUN LAZYGIT_VERSION=$(curl -s "https://api.github.com/repos/jesseduffield/lazygit/releases/latest" | \grep -Po '"tag_name": *"v\K[^"]*') && \
  curl -Lo lazygit.tar.gz "https://github.com/jesseduffield/lazygit/releases/download/v${LAZYGIT_VERSION}/lazygit_${LAZYGIT_VERSION}_Linux_x86_64.tar.gz" && \
  tar xf lazygit.tar.gz lazygit && \
  install lazygit -D -t /usr/local/bin/ && \
  echo "LazyGit installed successfully."

# install Node.JS LST (useful for tools!)
#RUN set -eux; \
#    echo "Installing Node.js v${NODE_VERSION} for ${NODE_ARCH}..." && \
#    curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" && \
#    tar -xf "node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" && \
#    mv "node-v${NODE_VERSION}-linux-${NODE_ARCH}" /usr/local/node-v${NODE_VERSION} && \
#    ln -sf /usr/local/node-v${NODE_VERSION}/bin/node /usr/local/bin/node && \
#    ln -sf /usr/local/node-v${NODE_VERSION}/bin/npm /usr/local/bin/npm && \
#    ln -sf /usr/local/node-v${NODE_VERSION}/bin/npx /usr/local/bin/npx && \
#    echo "Verifying Node.js installation..." && \
#    node -v && npm -v && \
#    rm -rf /tmp/node-v${NODE_VERSION}-linux-${NODE_ARCH}* && \
#    echo "Node.js installed successfully."

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

WORKDIR /workspaces/gramine-java-benchmark

ENTRYPOINT ["/usr/local/bin/devcontainer-entrypoint"]
CMD ["/usr/sbin/sshd", "-D", "-e"]
