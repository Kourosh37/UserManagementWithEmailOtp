# syntax=docker/dockerfile:1.7
#
# Multi-stage image to keep the runtime layer slim while compiling wheels
# that need system headers (asyncpg, bcrypt).

FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=on \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

WORKDIR /app

# System deps for compiling and linking asyncpg/bcrypt wheels
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && python -m venv "${VIRTUAL_ENV}" \
    && pip install --upgrade pip \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN pip install .

# Runtime image (no build toolchain)
FROM python:3.12-slim AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=on \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

WORKDIR /app

# Only runtime libs required by asyncpg/postgres client
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

COPY --from=builder "${VIRTUAL_ENV}" "${VIRTUAL_ENV}"

# Copy application source (keep secrets out of the image)
COPY app ./app
COPY index.html README.md .env.example ./

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
