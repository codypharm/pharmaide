FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic ./alembic
COPY alembic.ini ./
COPY app ./app
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.13-slim

ENV PATH="/app/.venv/bin:$PATH"
ENV PORT=8080
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system pharmaide && adduser --system --ingroup pharmaide pharmaide

COPY --from=builder --chown=pharmaide:pharmaide /app /app

USER pharmaide

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
