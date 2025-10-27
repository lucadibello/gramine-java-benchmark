# syntax=docker/dockerfile:1.4

FROM gramineproject/gramine:stable-noble

ENV DEBIAN_FRONTEND=noninteractive

ARG REMOTE_USER=dev
ARG REMOTE_GROUP=${REMOTE_USER}
ARG REMOTE_HOME=/home/${REMOTE_USER}

# Ensure the remote user/group exist so later chowns succeed
RUN if ! getent group "${REMOTE_GROUP}" >/dev/null; then \
        groupadd "${REMOTE_GROUP}"; \
    fi \
    && if ! id -u "${REMOTE_USER}" >/dev/null 2>&1; then \
        useradd --create-home --shell /bin/bash --gid "${REMOTE_GROUP}" "${REMOTE_USER}"; \
    fi

# Base tooling required before features run
RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client ca-certificates sudo python3-pynvim \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Provide entrypoint that keeps the headless Neovim server alive
COPY .devcontainer/devcontainer-entrypoint.sh /usr/local/bin/devcontainer-entrypoint
RUN chmod +x /usr/local/bin/devcontainer-entrypoint

# Install Neovim configuration for the remote user
RUN git clone https://github.com/lucadibello/neovim.git /tmp/nvim-config \
    && mkdir -p ${REMOTE_HOME}/.config \
    && rm -rf ${REMOTE_HOME}/.config/nvim \
    && cp -a /tmp/nvim-config ${REMOTE_HOME}/.config/nvim \
    && chown -R ${REMOTE_USER}:${REMOTE_GROUP} ${REMOTE_HOME}/.config/nvim \
    && rm -rf /tmp/nvim-config

# Ensure cache directory exists for headless Neovim logs
RUN mkdir -p ${REMOTE_HOME}/.cache \
    && chown ${REMOTE_USER}:${REMOTE_GROUP} ${REMOTE_HOME}/.cache

EXPOSE 22 6666

ENTRYPOINT ["/usr/local/bin/devcontainer-entrypoint"]
