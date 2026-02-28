# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Copy only the files needed to install the package.
# This maximises layer caching — source changes don't invalidate the pip layer.
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir --prefix=/install -e .

# ── Stage 2: production ───────────────────────────────────────────────────────
FROM python:3.12-slim AS production

WORKDIR /app

# Copy installed package from builder stage
COPY --from=builder /install /usr/local
COPY --from=builder /build/src /app/src
COPY --from=builder /build/pyproject.toml /app/pyproject.toml

# Alembic needs the alembic.ini and migrations at runtime
COPY alembic.ini ./
COPY alembic/ ./alembic/

ENV PYTHONUNBUFFERED=1

# No CMD — overridden per service in docker-compose.yml
