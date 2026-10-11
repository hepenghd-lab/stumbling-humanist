FROM node:24.21.0-bookworm-slim

# Only the base OS dependency is downloaded; no project or npm code runs here.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/codex-zh-test
COPY package.json package-lock.json install.sh uninstall.sh LICENSE ./
COPY bin/ ./bin/
COPY lib/ ./lib/
COPY data/ ./data/
COPY scripts/ ./scripts/
COPY tests/ ./tests/

ENV PYTHONDONTWRITEBYTECODE=1 \
    CODEX_ZH_HOME=/tmp/codex-zh-test-settings \
    TERM=xterm-256color
USER 1000:1000
ENTRYPOINT ["bash", "/opt/codex-zh-test/scripts/container-entry.sh"]
