#!/bin/sh
set -eu

alembic upgrade head

if [ "${TRUST_PROXY_HEADERS:-false}" = "true" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log --proxy-headers --forwarded-allow-ips "${TRUSTED_PROXY_IPS}"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log --no-proxy-headers
