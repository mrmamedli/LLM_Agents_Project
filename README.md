# LLM_Agents_Project
FastAPI backend for study-document uploads, processing results, deadlines, and
iCalendar export. The HTTP contract is defined in [`openapi.yaml`](openapi.yaml).

## Stack

- Python 3.12, FastAPI, Pydantic v2
- PostgreSQL 17, asyncpg, and asynchronous SQLAlchemy 2.x sessions
- Nginx frontend with same-origin proxying to the FastAPI backend
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

Start PostgreSQL, run migrations, and start the API during backend development:

```bash
docker compose up -d database
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

Copy the environment template and start the complete frontend, backend, and
PostgreSQL stack:

```bash
cp .env.example .env
docker compose up --build
```

Open StudyHub at <http://localhost:8080>. Swagger UI is available at
<http://localhost:8080/docs>, ReDoc at <http://localhost:8080/redoc>, and the
backend health endpoint at <http://localhost:8080/health>.

The stack contains three services:

- `frontend` serves the static application through Nginx and proxies `/api`,
  documentation, and health requests to the backend;
- `backend` waits for PostgreSQL, applies all Alembic migrations, and starts
  Uvicorn;
- `database` runs PostgreSQL 17.

Uploaded PDFs and database data are stored in the `uploads` and `postgres_data`
named volumes. The backend and database are not published to the host. Change
`APP_PORT` in `.env` to publish the frontend on a different port.

### Email behavior

`EMAILS_ENABLED=false` is the default Compose debugging mode. Verification
emails are not sent and newly registered accounts are immediately verified, so
the frontend logs in directly after registration.

For a real deployment, configure SMTP and enable email delivery:

```dotenv
EMAILS_ENABLED=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=studyhub
SMTP_PASSWORD=replace-me
SMTP_FROM_EMAIL=noreply@example.com
SMTP_START_TLS=true
SMTP_USE_TLS=false
COOKIE_SECURE=true
```

`SMTP_START_TLS` and `SMTP_USE_TLS` cannot both be enabled. Set
`COOKIE_SECURE=true` only when StudyHub is served through HTTPS.

Stop the stack while preserving data with `docker compose down`. To also delete
uploaded files and database data, run `docker compose down --volumes`.

## Migrations

After changing SQLAlchemy models, create and review a migration:

```bash
poetry run alembic revision --autogenerate -m "describe change"
poetry run alembic upgrade head
```
