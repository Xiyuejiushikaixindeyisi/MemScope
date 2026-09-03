ARG PYTHON_IMAGE=python:3.11.16-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84
ARG SOURCE_DATE_EPOCH=1787929140

FROM ${PYTHON_IMAGE} AS builder

ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /opt/build
COPY docker/memory-api/requirements.txt ./requirements.txt
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install \
        --no-cache-dir --no-compile --index-url "${PIP_INDEX_URL}" \
        --requirement requirements.txt \
    && /opt/venv/bin/python -m pip install --no-cache-dir --no-compile --no-deps . \
    && find /opt/venv -type d -name __pycache__ -prune -exec rm -rf '{}' +

FROM ${PYTHON_IMAGE} AS runtime

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10002 memscope \
    && useradd --uid 10002 --gid memscope --create-home --no-log-init \
        --home-dir /var/lib/memscope memscope \
    && mkdir -p /var/lib/memscope /opt/venv /opt/memscope \
    && chown memscope:memscope /var/lib/memscope

COPY --from=builder --chown=10002:10002 /opt/venv /opt/venv
COPY --chown=10002:10002 docker/memory-api/entrypoint.sh /opt/memscope/entrypoint.sh

USER 10002:10002
WORKDIR /var/lib/memscope
EXPOSE 8080

ENTRYPOINT ["/opt/memscope/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "memscope.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
