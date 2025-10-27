# syntax=docker/dockerfile:1.4
FROM gramineproject/gramine:stable-noble

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends software-properties-common git openssh-client ca-certificates \
    && add-apt-repository -y ppa:neovim-ppa/stable \
    && apt-get update \
    && apt-get install -y --no-install-recommends neovim python3-neovim \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/lucadibello/neovim.git /tmp/nvim-config \
    && mkdir -p /home/dev/.config \
    && rm -rf /home/dev/.config/nvim \
    && cp -a /tmp/nvim-config /home/dev/.config/nvim \
    && chown -R dev:dev /home/dev/.config/nvim \
    && rm -rf /tmp/nvim-config

RUN mkdir -p /home/dev/.cache \
    && chown dev:dev /home/dev/.cache
