#!/bin/sh
set -eu
umask 077
mkdir -p /home/codex/.codex /workspace/cases /workspace/results
if [ ! -f /home/codex/.codex/config.toml ]; then
    cp /opt/codex-lab/config.toml /home/codex/.codex/config.toml
fi
if [ ! -f /workspace/AGENTS.md ]; then
    cp /opt/codex-lab/AGENTS.md /workspace/AGENTS.md
fi
if [ ! -d /workspace/.agents/skills/specorganon ]; then
    mkdir -p /workspace/.agents/skills
    cp -R /opt/specorganon/.agents/skills/specorganon /workspace/.agents/skills/
fi
if [ ! -d /workspace/docs ]; then
    cp -R /opt/specorganon/docs /workspace/docs
fi
# API keys are supplied only at runtime. Never echo or save the key in the image.
if [ -n "${OPENAI_API_KEY:-}" ] && [ ! -f /home/codex/.codex/auth.json ]; then
    printf '%s' "$OPENAI_API_KEY" | codex login --with-api-key
fi
exec "$@"
