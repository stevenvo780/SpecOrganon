# Build docker/release/Dockerfile first. This image uses a separate, fresh profile.
ARG SPECORGANON_IMAGE=specorganon-release:0.2.0rc3.dev10
FROM node@sha256:25330af3531fb5e23318554a0aa911125b6e91b1b777edf7655501d207c067a2 AS node
FROM ${SPECORGANON_IMAGE}
USER root
ARG CODEX_VERSION=0.160.0
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && npm install -g "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force \
    && usermod -l codex -d /home/codex -m ubuntu \
    && groupmod -n codex ubuntu \
    && mkdir -p /workspace /home/codex/.codex \
    && chown -R codex:codex /workspace /home/codex
COPY scripts /opt/specorganon/scripts
COPY workflows /opt/specorganon/workflows
COPY docs /opt/specorganon/docs
COPY .agents /opt/specorganon/.agents
COPY docker/codex /opt/codex-lab
RUN ln -s /opt/specorganon/venv /opt/specorganon/.venv \
    && chmod -R a+rX /opt/specorganon /opt/codex-lab \
    && chmod +x /opt/codex-lab/entrypoint.sh
ENV ORGANON_ROOT=/workspace
USER codex
WORKDIR /workspace
ENTRYPOINT ["/opt/codex-lab/entrypoint.sh"]
CMD ["codex"]
