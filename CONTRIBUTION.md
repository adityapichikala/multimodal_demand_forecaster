# Contributing to the Enterprise Multimodal Demand Forecaster

Thank you for your interest in contributing! This guide will get you from zero to a working local environment and through your first pull request.

---

## Table of Contents

- [Getting Started](#getting-started)
- [Local Development Setup](#local-development-setup)
- [Running Without Docker](#running-without-docker)
- [Alembic Migration Workflow](#alembic-migration-workflow)
- [Running Tests](#running-tests)
- [Branch Naming Convention](#branch-naming-convention)
- [Pull Request Process](#pull-request-process)
- [Issue Reporting](#issue-reporting)
- [Code Style](#code-style)

---

## Getting Started

1. **Fork** this repository to your GitHub account.
2. **Clone** your fork:

```bash
   git clone https://github.com/YOUR_USERNAME/multimodal_demand_forecaster.git
   cd multimodal_demand_forecaster
```

3. **Add the upstream remote** so you can pull future changes:

```bash
   git remote add upstream https://github.com/adityapichikala/multimodal_demand_forecaster.git
```

---

## Local Development Setup

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- API keys for: [Google AI Studio](https://aistudio.google.com/apikey), [WeatherAPI.com](https://www.weatherapi.com/), [TheNewsAPI](https://www.thenewsapi.com/)

### Step 1 — Configure your environment

Copy the example env file and fill in your keys:

```bash
cp .env.example .env
```

Open `.env` and replace all placeholder values with your real API keys.

### Step 2 — Start the full stack

```bash
docker-compose up --build
```

This starts **5 containers**: PostgreSQL, Redis, FastAPI, Celery Worker, and Next.js Frontend.

| Service    | URL                          |
|------------|------------------------------|
| Frontend   | http://localhost:3000        |
| API Docs   | http://localhost:8000/docs   |
| PostgreSQL | localhost:5432               |
| Redis      | localhost:6379               |

### Troubleshooting individual container failures

If one container crashes, you don't need to rebuild everything. Target just that service:

```bash
# Restart only the FastAPI backend
docker-compose restart api

# View logs for a specific container
docker-compose logs -f api
docker-compose logs -f celery_worker
docker-compose logs -f frontend

# Rebuild only one container after a code change
docker-compose up --build api
```

Common failure causes:
- **`db` container fails**: PostgreSQL password in `.env` doesn't match `DATABASE_URL`. Check both variables match.
- **`celery_worker` fails**: Redis isn't up yet. Run `docker-compose up redis` first, then `docker-compose up celery_worker`.
- **`frontend` fails**: Node modules not installed inside container. Run `docker-compose build frontend` then `docker-compose up frontend`.

---

## Running Without Docker

For faster backend iteration, you can run the FastAPI server directly (requires Python 3.11+):

```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# You still need PostgreSQL and Redis running.
# Start only those two containers:
docker-compose up db redis -d

# Run database migrations
alembic upgrade head

# Start the FastAPI server
uvicorn api:app --reload --port 8000
```

---

## Alembic Migration Workflow

The `alembic/` directory manages all database schema changes. **Every time you add or modify a SQLAlchemy model in `models.py`, you must generate a migration.**

### Generate a new migration

```bash
alembic revision --autogenerate -m "describe your change here"
```

Example:

```bash
alembic revision --autogenerate -m "add forecast_confidence column to forecasts table"
```

This creates a new file in `alembic/versions/`. Review it before applying.

### Apply pending migrations

```bash
alembic upgrade head
```

### Roll back one migration

```bash
alembic downgrade -1
```

> **Important:** Always commit your migration files alongside the model changes in the same PR. A PR that changes `models.py` without a migration file will be asked to add one before merge.

---

## Running Tests

The project uses `pytest` with an end-to-end test file:

```bash
# Make sure the full stack is running first (or at minimum db + redis)
docker-compose up -d

# Run all tests
pytest test_e2e.py -v

# Run a specific test by name
pytest test_e2e.py -v -k "test_upload"
```

All tests must pass before submitting a PR.

---

## Branch Naming Convention

Use one of these prefixes depending on what your change does:

| Prefix    | When to use                                      | Example                              |
|-----------|--------------------------------------------------|--------------------------------------|
| `feat/`   | Adding a new feature                             | `feat/add-export-to-csv`             |
| `fix/`    | Fixing a bug                                     | `fix/prophet-date-parsing-error`     |
| `docs/`   | Documentation only                               | `docs/add-alembic-migration-guide`   |
| `test/`   | Adding or fixing tests                           | `test/add-celery-worker-unit-tests`  |
| `refactor/` | Code cleanup with no functional change         | `refactor/optimise-agent-prompts`    |
| `chore/`  | Dependency updates, config changes               | `chore/bump-langchain-version`       |

---

## Pull Request Process

1. Make sure your branch is up to date with `main`:

```bash
   git fetch upstream
   git rebase upstream/main
```

2. Push your branch:

```bash
   git push origin docs/your-branch-name
```

3. Open a PR against `main` on the upstream repository.
4. Fill in the PR template that will appear automatically.
5. Reference the issue your PR closes: `Closes #26`

---

## Issue Reporting

Use the issue templates provided in `.github/ISSUE_TEMPLATE/`:

- **Bug Report** — for crashes, wrong outputs, or container failures
- **Feature Request** — for new capabilities or improvements

---

## Code Style

- Python: follows `.flake8` config at the repo root. Run `flake8 .` before pushing.
- TypeScript/Next.js: follow existing conventions in `frontend/src/`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `refactor:`.