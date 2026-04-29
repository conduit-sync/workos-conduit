# Local Development Guide

This guide covers setting up a local development environment, running the application, executing tests, and validating changes before pushing.

---

## Prerequisites

| Tool | Minimum version | Install |
|---|---|---|
| Python | 3.13 | [python.org](https://www.python.org/downloads/) or `brew install python@3.13` |
| make | Any | Pre-installed on macOS/Linux |
| git | Any | Pre-installed or `brew install git` |
| Docker + Docker Compose | Optional (for container-based dev) | [docker.com](https://www.docker.com/) |
| AWS CLI | Optional (for real AWS testing) | `brew install awscli` |

Verify Python version:

```bash
python3.13 --version
# Python 3.13.x
```

---

## First-Time Setup

```bash
# 1. Clone the repository
git clone https://github.com/your-org/workos-conduit.git
cd workos-conduit

# 2. Create a virtual environment using Python 3.13
python3.13 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install all dependencies (app + dev tools)
make install
# Equivalent to: pip install -e ".[dev]"
```

---

## Configuration for Local Development

Copy the example file and fill in the minimum required values:

```bash
cp .env.example .env
```

### Minimum required fields

These must be set to real values for the app to start:

| Variable | Where to get it |
|---|---|
| `WORKOS_API_KEY` | WorkOS dashboard → API Keys |
| `WORKOS_DIRECTORY_ID` | WorkOS dashboard → Directory Sync → your directory |
| `NINJAONE_CLIENT_ID` | NinjaOne → Administration → Apps & API → API |
| `NINJAONE_CLIENT_SECRET` | Same as above |
| `NINJAONE_ORG_ID` | NinjaOne organisation ID (visible in the URL) |

### Running the dev server without AWS (recommended for local dev)

Set `CURSOR_BACKEND=local` and `STATE_BACKEND=local` in your `.env`. This uses an in-memory cursor and a local filesystem state store — no AWS credentials needed.

Minimum `.env` for `make dev`:

```bash
WORKOS_API_KEY=sk_test_placeholder
WORKOS_DIRECTORY_ID=directory_test
NINJAONE_CLIENT_ID=test_client_id
NINJAONE_CLIENT_SECRET=test_client_secret
CURSOR_BACKEND=local
STATE_BACKEND=local
API_SECRET_KEY=local-dev-key
LOG_FORMAT=console
LOG_LEVEL=DEBUG
```

Run records are written to `.local-state/runs/` (gitignored). The cursor resets to zero on every server restart.

### Running the dev server with real AWS

If you want to test against real AWS resources, keep `CURSOR_BACKEND=aws` and `STATE_BACKEND=aws` and supply credentials:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1
# or: aws configure
```

Also set `S3_STATE_BUCKET` to an existing bucket you have write access to.

### Safe placeholder values for unit testing only

If you only want to run the test suite, the `.env` values below are sufficient. Tests override all settings via pytest fixtures and never make real AWS or NinjaOne calls.

```bash
WORKOS_API_KEY=sk_test_placeholder
WORKOS_DIRECTORY_ID=directory_test
NINJAONE_CLIENT_ID=test_client_id
NINJAONE_CLIENT_SECRET=test_client_secret
CURSOR_BACKEND=local
STATE_BACKEND=local
API_SECRET_KEY=local-dev-key
LOG_FORMAT=console
LOG_LEVEL=DEBUG
```

> The test suite uses [moto](https://docs.getmoto.org/) to mock all AWS calls — no real credentials or buckets required regardless of `CURSOR_BACKEND`/`STATE_BACKEND` settings.

---

## Running the Development Server

### Option 1: make dev (recommended)

```bash
make dev
```

This runs:
```bash
LOG_FORMAT=console LOG_LEVEL=DEBUG \
uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload --reload-dir src
```

- `--reload` watches `src/` and restarts the server on any `.py` change
- `LOG_FORMAT=console` produces human-readable colourised logs instead of JSON
- `LOG_LEVEL=DEBUG` shows all log lines including adapter API calls

### Option 2: scripts/dev.sh

```bash
bash scripts/dev.sh
```

Equivalent to `make dev` — useful when you want to customise the script directly.

### Option 3: Docker Compose

```bash
docker-compose up --build
```

Mounts `src/` as a volume so code changes reload without rebuilding the image. Requires a `.env` file at the repo root. Useful for testing the containerised environment before deploying.

---

## Validating the Running Server

Once the server is running on port 8080, use these curl commands to confirm it is healthy and functional.

### Liveness check

```bash
curl -s http://localhost:8080/health/ | jq
```

Expected response:
```json
{"status": "ok"}
```

This always returns 200 regardless of downstream connectivity.

### Readiness check

```bash
curl -s http://localhost:8080/health/ready | jq
```

Expected response when all components are healthy:
```json
{
  "status": "ready",
  "components": {
    "adapter": true,
    "cursor_backend": true,
    "state_backend": true
  }
}
```

Returns HTTP 503 if any component fails its `health_check()`.

### Trigger a sync manually

```bash
curl -s -X POST http://localhost:8080/api/v1/sync/trigger \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-key" \
  -d '{"trigger_source": "api"}' | jq
```

Expected response:
```json
{
  "run_id": "abc123...",
  "status": "success",
  "events_processed": 3,
  "duration_seconds": 1.24,
  "adapter": "ninjaone",
  "message": "Sync completed with status: success"
}
```

### Check sync status

```bash
curl -s http://localhost:8080/api/v1/sync/status | jq
```

### List recent runs

```bash
curl -s "http://localhost:8080/api/v1/runs/?limit=5" | jq
```

### View the dashboard

Open [http://localhost:8080/](http://localhost:8080/) in a browser. The dashboard shows run history, action breakdown, and a "Trigger Sync Now" button that prompts for the API key.

---

## Running the Test Suite

```bash
make test
```

This runs:
```bash
pytest --cov=src --cov-report=xml --cov-report=term-missing -v
```

### What each test layer covers

**Unit tests** (`tests/unit/`):
- All AWS calls are mocked via [moto](https://docs.getmoto.org/) — no real credentials needed
- Handler tests use `MagicMock(spec=BaseTargetAdapter)` to isolate handler logic
- No network calls of any kind

**Integration tests** (`tests/integration/`):
- Uses `fastapi.testclient.TestClient` to exercise the full FastAPI request/response cycle
- Dependencies (engine, backends) are overridden via `app.dependency_overrides`
- Still no real AWS or NinjaOne calls

### Running a single test

```bash
# Run a specific file
.venv/bin/pytest tests/unit/test_allowed_groups.py -v

# Run a specific test function
.venv/bin/pytest tests/unit/test_allowed_groups.py::test_load_from_env_returns_parsed_list -v

# Run tests matching a keyword
.venv/bin/pytest -k "allowed_groups" -v
```

### Coverage report

After `make test`, open `coverage.xml` for machine-readable coverage, or read the terminal output for a per-file breakdown. The target is ≥ 80% line coverage. The CI pipeline fails below this threshold.

---

## Linting and Formatting

```bash
# Check for linting errors (ruff) and formatting issues (black)
make lint

# Auto-fix formatting
make fmt

# Check formatting without modifying files (used in CI)
make fmt-check
```

### What ruff enforces

The project uses ruff with rules `E, F, I, UP, B` (minus `B008` which conflicts with FastAPI's `Depends` pattern):

- **E/F**: Standard pyflakes / pycodestyle errors (unused imports, undefined names, etc.)
- **I**: Import sorting (isort-compatible)
- **UP**: Pyupgrade — use modern Python 3.10+ syntax (`str | None`, `StrEnum`, etc.)
- **B**: Bugbear — common Python mistakes and anti-patterns

### Common ruff issues and fixes

| Error | Fix |
|---|---|
| `F401 imported but unused` | Remove the import |
| `I001 import block unsorted` | Run `make fmt` to auto-sort |
| `UP035 deprecated typing import` | Replace `from typing import List` with `list` |
| `F841 local variable assigned but never used` | Remove the assignment or use `_` |

---

## Testing Group Filtering Locally

To verify the allow-list feature without a live NinjaOne instance:

**1. Set the allow-list in `.env`:**

```bash
SYNC_ALLOWED_GROUPS=["IT Admins"]
```

**2. Trigger a sync:**

```bash
curl -s -X POST http://localhost:8080/api/v1/sync/trigger \
  -H "X-API-Key: local-dev-key" \
  -H "Content-Type: application/json" \
  -d '{}' | jq .run_id
```

**3. Check the run detail for SKIPPED results:**

```bash
curl -s http://localhost:8080/api/v1/runs/RUN_ID_HERE | jq '.results[] | select(.action == "skipped")'
```

Group events where the group name is not "IT Admins" will appear with `action: "skipped"` and will not have called the NinjaOne API.

**4. Verify empty list allows all:**

```bash
SYNC_ALLOWED_GROUPS=[]  # in .env — all groups pass through
```

---

## Bootstrap Script

The bootstrap script (`scripts/bootstrap.py`) is a one-time tool for importing all existing Google Workspace users from WorkOS into NinjaOne before you deploy the event-driven sync. Run it once before enabling the ECS service.

```bash
# Dry run — shows what would be created without making any API calls
python scripts/bootstrap.py --dry-run

# Live run — creates users in NinjaOne
python scripts/bootstrap.py

# Target a specific adapter
python scripts/bootstrap.py --adapter ninjaone
```

Expected output:
```
DRY RUN — no changes will be made
Processing users from WorkOS directory: directory_01...
  WOULD CREATE alice@example.com
  WOULD CREATE bob@example.com
  WOULD SKIP   carol@example.com (already exists)

Summary: 2 would-create, 1 would-skip, 0 errors
```

The script paginates through all WorkOS directory users and calls `adapter.provision_user_created()` for each one. Since `provision_user_created` is idempotent (returns `SKIPPED` if the user already exists), it is safe to run multiple times.
