# syntax=docker/dockerfile:1.7
# ------------------------------------------------------------------------------
# Stage 1: build wheels (compilers stay out of the runtime image)
# ------------------------------------------------------------------------------
FROM python:3.14-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --upgrade pip \
    && pip wheel --wheel-dir /wheels ".[postgres,mcp]"

# ------------------------------------------------------------------------------
# Stage 2: runtime
# ------------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

ARG APP_USER=tower
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENV=production \
    API_HOST=0.0.0.0 \
    API_PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 ${APP_USER}

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# Sample data is only needed for the SQLite fallback; PostgreSQL deployments seed from code.
COPY --chown=${APP_USER}:${APP_USER} data/samples/ data/samples/
RUN mkdir -p /app/data && chown -R ${APP_USER}:${APP_USER} /app/data

USER ${APP_USER}

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "logistics_tower.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
