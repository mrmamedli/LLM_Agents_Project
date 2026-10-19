# StudyHub development guide

## Project overview

StudyHub helps students organize course materials and deadlines. Users can
manage subjects, upload PDF documents, inspect extracted information, update
deadlines, and export deadlines as an iCalendar file.

### Backend

The backend is an asynchronous Python 3.12 application built with FastAPI and
Pydantic v2. It uses asynchronous SQLAlchemy with asyncpg and PostgreSQL,
Alembic for database migrations, and Poetry for dependency management. The API
contract is defined in `openapi.yaml`.

Backend code is organized as follows:

- `app/routers/` contains HTTP endpoints.
- `app/services/` contains application services and external integrations.
- `app/agent/` contains document-processing and extraction logic.
- `app/models.py` contains SQLAlchemy models.
- `app/schemas.py` contains API request and response schemas.
- `tests/` contains asynchronous API and service tests.

### Frontend

The frontend is a lightweight Russian-language single-page interface written
in vanilla HTML, CSS, and JavaScript. It has no separate package manager or
build step. Its source files are in `app/static/`:

- `app/static/index.html` defines the application shell.
- `app/static/app.js` manages subjects, PDF uploads, document cards,
  deadlines, calendar views, and API requests to `/api`.
- `app/static/style.css` provides responsive styling and light/dark themes.

When changing the frontend, keep it dependency-free unless the task explicitly
requires introducing frontend tooling. Verify UI behavior manually in a
browser and preserve compatibility with the OpenAPI contract.

## Development commands

Install dependencies:

```bash
poetry install
```

Apply formatting:

```bash
poetry run ruff format .
```

Check formatting without modifying files:

```bash
poetry run ruff format --check .
```

Run linting:

```bash
poetry run ruff check .
```

Run strict type checking:

```bash
poetry run mypy app tests
```

Run all tests:

```bash
poetry run pytest
```

Run all quality checks before handing work back:

```bash
poetry run ruff format --check .
poetry run ruff check .
poetry run mypy app tests
poetry run pytest
```

## Repository rules

1. **Never commit or push.** The agent may edit and stage files only when the
   user requests it. The user is responsible for every commit and push.
2. **Never develop on `main`.** Before changing files, verify that the current
   branch is not `main`. If it is `main`, stop and ask the user to switch to or
   create a feature branch.
3. **Keep one feature per branch.** Every branch must contain one feature or
   one focused change only. Do not mix unrelated changes in the same branch,
   staged diff, or pull request.
