# Base digest observed on 2026-10-04; no credentials or author workspace included.
FROM ubuntu@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55
ARG UV_VERSION=0.12.22
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       python3=3.12.3-0ubuntu2.1 python3-venv=3.12.3-0ubuntu2.1 \
       poppler-utils=24.02.0-1ubuntu9.9 ca-certificates git libseccomp2 strace=6.8-0ubuntu2 \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/build-tools \
    && /opt/build-tools/bin/pip install --no-cache-dir "uv==${UV_VERSION}"
ENV PATH="/opt/specorganon/venv/bin:/opt/build-tools/bin:${PATH}" \
    UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
    SOURCE_DATE_EPOCH=1791230400
WORKDIR /opt/specorganon
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv export --frozen --extra dev --no-emit-project --format requirements-txt -o requirements.txt \
    && uv build --wheel --python /usr/bin/python3 --out-dir dist \
    && uv venv --python /usr/bin/python3 /opt/specorganon/venv \
    && uv pip install --python /opt/specorganon/venv/bin/python --require-hashes -r requirements.txt \
    && uv pip install --python /opt/specorganon/venv/bin/python --no-deps dist/*.whl \
    && uv pip check --python /opt/specorganon/venv/bin/python \
    && /opt/specorganon/venv/bin/python -c 'import os; assert hasattr(os, "memfd_create")' \
    && echo '0fb98ea179e19154a90202608c164f2a319b79f16576fa6534b2d601033565e7  /usr/bin/pdftotext' | sha256sum -c - \
    && dpkg-query -W > installed-debian-packages.txt \
    && sha256sum /usr/bin/pdftotext dist/*.whl > installed-pins.sha256
RUN cp -a /root/.cache/uv /opt/uv-cache-seed \
    && chmod -R a+rX /opt/uv-cache-seed
RUN mkdir -p /runs && chown ubuntu:ubuntu /runs
USER ubuntu
WORKDIR /runs
CMD ["organon", "--help"]
