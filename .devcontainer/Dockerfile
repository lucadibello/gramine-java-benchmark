# syntax=docker/dockerfile:1.4
FROM gramineproject/gramine:stable-noble

ENV DEBIAN_FRONTEND=noninteractive

ARG REMOTE_USER=dev
ARG REMOTE_GROUP=${REMOTE_USER}
ARG REMOTE_HOME=/home/${REMOTE_USER}

# Make sure to create the remote user with a home directory if it doesn't exist (needed for chown later in nvim installation)
RUN if ! getent group "${REMOTE_GROUP}" >/dev/null; then \
        groupadd "${REMOTE_GROUP}"; \
    fi \
    && if ! id -u "${REMOTE_USER}" >/dev/null 2>&1; then \
        useradd --create-home --shell /bin/bash --gid "${REMOTE_GROUP}" "${REMOTE_USER}"; \
    fi

RUN apt-get update \
    && apt-get install -y --no-install-recommends software-properties-common git openssh-client ca-certificates \
    && add-apt-repository -y ppa:neovim-ppa/stable \
    && apt-get update \
    && apt-get install -y --no-install-recommends neovim python3-neovim \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/lucadibello/neovim.git /tmp/nvim-config \
    && mkdir -p ${REMOTE_HOME}/.config \
    && rm -rf ${REMOTE_HOME}/.config/nvim \
    && cp -a /tmp/nvim-config ${REMOTE_HOME}/.config/nvim \
    && chown -R ${REMOTE_USER}:${REMOTE_GROUP} ${REMOTE_HOME}/.config/nvim \
    && rm -rf /tmp/nvim-config

RUN mkdir -p ${REMOTE_HOME}/.cache \
    && chown ${REMOTE_USER}:${REMOTE_GROUP} ${REMOTE_HOME}/.cache
