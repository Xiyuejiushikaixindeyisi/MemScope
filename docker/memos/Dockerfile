ARG PYTHON_IMAGE=python:3.11.16-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84
FROM ${PYTHON_IMAGE}

ARG MEMOS_ARCHIVE=MemoryOS-v2.0.32-185ebdb.tar.gz

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/memos/src

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libffi-dev \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/vendor
COPY third_party/memos/${MEMOS_ARCHIVE} ./
COPY third_party/memos/SHA256SUMS ./
RUN sha256sum --check SHA256SUMS \
    && mkdir -p /opt/memos \
    && tar --extract --gzip --file "${MEMOS_ARCHIVE}" \
        --strip-components=1 --directory /opt/memos \
    && python -m pip install --no-cache-dir --requirement /opt/memos/docker/requirements.txt \
    && rm -rf /opt/vendor

COPY docker/memos/entrypoint.sh /usr/local/bin/memos-entrypoint

RUN groupadd --gid 10001 memos \
    && useradd --uid 10001 --gid memos --create-home --home-dir /var/lib/memos memos \
    && mkdir -p /var/lib/memos/files \
    && chown -R memos:memos /var/lib/memos /opt/memos \
    && chmod 0755 /usr/local/bin/memos-entrypoint

USER memos
WORKDIR /var/lib/memos
EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/memos-entrypoint"]
CMD ["python", "-m", "uvicorn", "memos.api.server_api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
