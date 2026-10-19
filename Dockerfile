# syntax=docker/dockerfile:1

# --------------------------------------------------------------------------- #
# Stage 1 — builder: compile/install Python dependencies into a virtualenv
# --------------------------------------------------------------------------- #
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# build-essential + libpq-dev are needed to compile psycopg2 if no wheel exists.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# --------------------------------------------------------------------------- #
# Stage 2 — runtime: slim image, non-root user, only what is needed
# --------------------------------------------------------------------------- #
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# libpq5 = runtime library for psycopg2.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home appuser

COPY --from=builder /opt/venv /opt/venv
COPY . .

RUN chmod +x entrypoint.sh \
    && mkdir -p /app/staticfiles \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
