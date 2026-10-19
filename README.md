# LLM_Agents_Project
Репозиторий для проекта по курсу Мультиагентные системы

FastAPI backend for study-document uploads, processing results, deadlines, and
iCalendar export. The HTTP contract is defined in [`openapi.yaml`](openapi.yaml).

## Stack

- Python 3.12, FastAPI, Pydantic v2
- PostgreSQL 17, asyncpg, and asynchronous SQLAlchemy 2.x sessions
- Alembic migrations
- Poetry dependency management
- Ruff linting/formatting and Mypy strict type checking
- Pytest API and service tests

## Local development

Install Poetry, then install all dependencies:

```bash
poetry install
cp .env.example .env
```

Start PostgreSQL, run migrations, and start the API:

```bash
docker compose up -d db
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload
```

The API is available at <http://localhost:8000>, Swagger UI at
<http://localhost:8000/docs>, and ReDoc at <http://localhost:8000/redoc>.

Run quality checks:

```bash
poetry run ruff format --check .
poetry run ruff check .
poetry run mypy app tests
poetry run pytest
```

Apply formatting with `poetry run ruff format .`.

## Docker

Start the complete API and PostgreSQL stack:

```bash
docker compose up --build
```

The API container waits for PostgreSQL, applies all Alembic migrations, and then
starts Uvicorn. Uploaded PDFs and database data are stored in named volumes.

## Migrations

After changing SQLAlchemy models, create and review a migration:

```bash
poetry run alembic revision --autogenerate -m "describe change"
poetry run alembic upgrade head
```
