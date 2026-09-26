FROM ghcr.io/astral-sh/uv:0.8.11 AS uv
FROM python:3.13-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY --from=uv /uv /uvx /bin/

WORKDIR /app
RUN apk upgrade --no-cache libcrypto3 libssl3 libuuid
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

# Runtime images do not need the system pip installation copied by the base
# image. Removing it also removes unused vendored build-tool dependencies.
RUN rm -rf /usr/local/lib/python3.13/site-packages/pip \
        /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
    && rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.13

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY docker-entrypoint.sh ./

RUN addgroup -S regbridge \
    && adduser -S -D -H -G regbridge regbridge \
    && chown -R regbridge:regbridge /app \
    && chmod 0555 /app/docker-entrypoint.sh

USER regbridge
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/ready', timeout=2)"]

ENTRYPOINT ["/app/docker-entrypoint.sh"]
