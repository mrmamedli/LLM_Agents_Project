FROM python:3.12-slim AS builder

ENV POETRY_VERSION=2.1.1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

WORKDIR /app
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"
COPY pyproject.toml poetry.lock* ./
RUN poetry install --only main --no-root

FROM python:3.12-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN mkdir -p /app/data/uploads

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
