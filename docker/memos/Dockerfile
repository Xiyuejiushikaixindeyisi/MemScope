ARG PYTHON_IMAGE=python:3.11.16-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84
ARG SOURCE_DATE_EPOCH=1787929140

FROM ${PYTHON_IMAGE} AS builder

ARG MEMOS_ARCHIVE=MemoryOS-v2.0.32-185ebdb.tar.gz
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG SOURCE_DATE_EPOCH

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /opt/vendor
COPY third_party/memos/${MEMOS_ARCHIVE} ./
COPY third_party/memos/SHA256SUMS ./
COPY docker/memos/constraints.txt ./constraints.txt
COPY docker/memos/entrypoint.sh ./memos-entrypoint.sh

RUN sha256sum --check SHA256SUMS \
    && mkdir -p /opt/memos \
    && tar --extract --gzip --file "${MEMOS_ARCHIVE}" \
        --strip-components=1 --directory /opt/memos \
    && test "$(grep -F -c '"tokenizer_or_token_counter": "gpt2"' \
        /opt/memos/src/memos/api/config.py)" -eq 3 \
    && sed -i \
        's|"tokenizer_or_token_counter": "gpt2"|"tokenizer_or_token_counter": os.getenv("MEM_READER_TOKENIZER", "word")|g' \
        /opt/memos/src/memos/api/config.py \
    && test "$(grep -F -c 'if self._io_loop_thread and self._io_loop_thread.is_alive():' \
        /opt/memos/src/memos/mem_scheduler/webservice_modules/rabbitmq_service.py)" -eq 1 \
    && sed -i \
        's|if self._io_loop_thread and self._io_loop_thread.is_alive():|if getattr(self, "_io_loop_thread", None) and self._io_loop_thread.is_alive():|' \
        /opt/memos/src/memos/mem_scheduler/webservice_modules/rabbitmq_service.py \
    && install --mode=0755 memos-entrypoint.sh /opt/memos/memos-entrypoint.sh \
    && python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install \
        --no-cache-dir \
        --no-compile \
        --index-url "${PIP_INDEX_URL}" \
        --constraint /opt/vendor/constraints.txt \
        --requirement /opt/memos/docker/requirements.txt \
    && find /opt/venv -type d -name __pycache__ -prune -exec rm -rf '{}' + \
    && find /opt/venv /opt/memos -exec touch -h \
        --date="@${SOURCE_DATE_EPOCH}" '{}' + \
    && rm -rf /opt/vendor

FROM ${PYTHON_IMAGE} AS runtime

ARG SOURCE_DATE_EPOCH

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/memos/src

RUN groupadd --gid 10001 memos \
    && useradd --uid 10001 --gid memos --create-home --no-log-init \
        --home-dir /var/lib/memos memos \
    && mkdir -p /var/lib/memos/files /opt/venv /opt/memos \
    && chown memos:memos /var/lib/memos /var/lib/memos/files \
    && touch -h --date="@${SOURCE_DATE_EPOCH}" \
        /etc /etc/passwd /etc/passwd- /etc/group /etc/group- /etc/shadow \
        /etc/shadow- /etc/gshadow /etc/gshadow- /etc/subgid /etc/subuid \
        /opt /opt/venv /opt/memos /usr/local/bin /var /var/lib \
    && find /var/lib/memos \
        -exec touch -h --date="@${SOURCE_DATE_EPOCH}" '{}' +

COPY --from=builder --chown=10001:10001 /opt/venv /opt/venv
COPY --from=builder --chown=10001:10001 /opt/memos /opt/memos

USER 10001:10001
WORKDIR /var/lib/memos
EXPOSE 8000

ENTRYPOINT ["/opt/memos/memos-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "memos.api.server_api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
