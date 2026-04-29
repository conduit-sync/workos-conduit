# WorkOS → Target Provisioning Conduit
## Claude Code Implementation Brief — v3

> **License**: GNU General Public License v3.0 (GPL-3.0)
> **Language**: Python 3.13+
> **Framework**: FastAPI
> **Formatter**: Black
> **Open Source**: Yes — designed for community contribution

---

## Project Overview

A **generic, extensible, open-source** user provisioning bridge that:

1. Polls the **WorkOS Events API** for Directory Sync events (Google Workspace → WorkOS)
2. Dispatches provisioning actions to **pluggable target adapters** (NinjaOne today, others tomorrow)
3. Persists sync execution state via a **pluggable state backend** (AWS S3 today, Azure Blob / GCS / local tomorrow)
4. Persists cursor state via a **pluggable cursor backend** (AWS SSM Parameter Store today)
5. Exposes a **FastAPI application** that:
   - Serves REST endpoints for triggering sync, checking health, and reading run history
   - Serves a **built-in HTML dashboard** (Jinja2 templates served by FastAPI directly) for visualising sync state and manually triggering polls
6. Runs as a long-lived **AWS ECS Fargate container** (single instance, minimal footprint)

### Design Philosophy

- **Adapter pattern (targets)**: All provisioning targets implement a common `BaseTargetAdapter` interface. Adding a new target (Zendesk, Freshservice, Jira SM) means implementing one class — no changes to core logic.
- **Backend pattern (cloud resources)**: Cursor and state persistence are behind `CursorBackend` / `StateBackend` ABCs. AWS is the only concrete implementation today; Azure/GCS/local slot in via the same registry pattern.
- **API-driven**: Polling is triggered via a `POST /api/v1/sync/trigger` endpoint, not an internal timer. The caller (EventBridge Scheduler, external cron, or the dashboard UI) decides when to poll.
- **Audit-first**: Every sync run is immutably written to the state backend as JSON. The dashboard reads directly from the backend — no database needed.
- **Configurable everywhere**: Page sizes, retry counts, timeouts, dashboard limits, logging outputs, and stop-on-error behaviour are all environment-driven. Sensible defaults; zero hardcoded tuning constants in code.
- **Stdout-first logging**: Logs default to structured JSON on stdout so CloudWatch (`awslogs` driver), Datadog, Splunk, or any log shipper can consume them unchanged.
- **GPL-3.0**: All contributions must remain open source.

---

## Repository Structure to Create

```
workos-conduit/
├── LICENSE                              ← GPL-3.0 full text
├── README.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── Makefile                             ← dev / test / lint / fmt / run targets
├── .github/
│   └── workflows/
│       ├── ci.yml                       ← lint + test on PR
│       └── release.yml                  ← build + push to GHCR on tag
├── sonar-project.properties             ← SonarQube config
├── pyproject.toml                       ← deps + black + ruff + pytest config
├── requirements.txt                     ← pinned runtime deps
├── requirements-dev.txt                 ← pinned dev/test deps
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── src/
│   ├── __init__.py
│   ├── main.py                          ← FastAPI app factory + lifespan
│   ├── config.py                        ← pydantic-settings Settings
│   ├── deps.py                          ← FastAPI dependency injection
│   ├── logging_config.py                ← structlog configuration
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py                    ← mounts all sub-routers
│   │   ├── sync.py                      ← POST /sync/trigger, GET /sync/status
│   │   ├── runs.py                      ← GET /runs, GET /runs/{run_id}
│   │   └── health.py                    ← GET /health, GET /health/ready
│   │
│   ├── dashboard/
│   │   ├── __init__.py
│   │   ├── router.py                    ← GET / (serves dashboard HTML)
│   │   └── templates/
│   │       ├── base.html
│   │       ├── index.html               ← main dashboard
│   │       └── run_detail.html          ← single run detail page
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── sync_engine.py               ← orchestrates one full sync cycle
│   │   ├── sync_run.py                  ← SyncRunContext (Unit of Work)
│   │   ├── event_router.py              ← routes WorkOS events to handlers
│   │   └── models.py                    ← shared Pydantic models
│   │
│   ├── backends/                        ← ★ pluggable cloud backends
│   │   ├── __init__.py
│   │   ├── base.py                      ← CursorBackend + StateBackend ABCs
│   │   ├── registry.py                  ← backend registry/factory
│   │   └── aws/
│   │       ├── __init__.py
│   │       ├── cursor_ssm.py            ← SsmCursorBackend
│   │       └── state_s3.py              ← S3StateBackend
│   │
│   ├── workos/
│   │   ├── __init__.py
│   │   └── client.py                    ← WorkOS Events API wrapper
│   │
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py                      ← BaseTargetAdapter ABC
│   │   ├── registry.py                  ← adapter registry/factory
│   │   └── ninjaone/
│   │       ├── __init__.py
│   │       ├── adapter.py               ← NinjaOneAdapter(BaseTargetAdapter)
│   │       ├── client.py                ← NinjaOne REST API client
│   │       └── mapper.py                ← WorkOS user → NinjaOne payload
│   │
│   └── handlers/
│       ├── __init__.py
│       ├── base.py                      ← BaseEventHandler ABC
│       ├── user_created.py
│       ├── user_updated.py
│       ├── user_deleted.py
│       └── group_membership.py
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_mapper_ninjaone.py
│   │   ├── test_event_router.py
│   │   ├── test_sync_engine.py
│   │   ├── test_sync_run.py
│   │   ├── test_cursor_ssm.py
│   │   ├── test_state_s3.py
│   │   ├── test_backend_registry.py
│   │   └── handlers/
│   │       ├── test_user_created.py
│   │       ├── test_user_updated.py
│   │       ├── test_user_deleted.py
│   │       └── test_group_membership.py
│   ├── integration/
│   │   ├── test_api_sync.py
│   │   ├── test_api_runs.py
│   │   └── test_api_health.py
│   └── fixtures/
│       ├── workos_user_created.json
│       ├── workos_user_updated.json
│       ├── workos_user_deleted.json
│       ├── workos_group_user_added.json
│       └── workos_group_user_removed.json
│
├── scripts/
│   ├── bootstrap.py                     ← one-time full user import
│   ├── dev.sh                           ← local uvicorn --reload runner
│   └── deploy.sh
│
└── infra/
    └── aws/                             ← AWS-specific deployment assets
        ├── task-definition.json
        ├── iam-task-role-policy.json
        └── eventbridge-schedule.json
```

> **Future**: new cloud implementations live under `src/backends/<cloud>/` and `infra/<cloud>/`. No other directories are cloud-coupled.

---

## License File

### Create `LICENSE`

Fetch the full GPL-3.0 license text from https://www.gnu.org/licenses/gpl-3.0.txt and write it verbatim to `LICENSE`.

Add the SPDX header to every `.py` source file:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors
```

---

## SonarQube Configuration

### Create `sonar-project.properties`

```properties
sonar.projectKey=workos-conduit
sonar.projectName=WorkOS Conduit
sonar.projectVersion=1.0.0
sonar.sources=src
sonar.tests=tests
sonar.language=py
sonar.sourceEncoding=UTF-8

# Python-specific
sonar.python.version=3.13
sonar.python.coverage.reportPaths=coverage.xml
sonar.python.xunit.reportPath=test-results.xml

# Exclusions
sonar.exclusions=**/__pycache__/**,**/*.pyc,infra/**,scripts/**

# Quality gate
sonar.qualitygate.wait=true

# Coverage thresholds (enforced by quality gate in SonarQube UI)
# Recommended minimums: line coverage 80%, branch coverage 70%
```

---

## Environment Variables

### Create `.env.example`

```bash
# ── WorkOS ────────────────────────────────────────────
WORKOS_API_KEY=sk_example_...
WORKOS_DIRECTORY_ID=directory_...
# Comma-separated list; default covers all dsync event types
WORKOS_EVENT_TYPES=dsync.user.created,dsync.user.updated,dsync.user.deleted,dsync.group.user_added,dsync.group.user_removed
WORKOS_EVENTS_PAGE_SIZE=100

# ── Active target adapter ─────────────────────────────
# Must match a registered adapter key in adapters/registry.py
# Current options: ninjaone
# Future options: zendesk, freshservice, jira_sm
SYNC_TARGET_ADAPTER=ninjaone

# Sync behaviour
SYNC_STOP_ON_ERROR=true          # if false, log error and continue (skips failed event)

# ── Backend selection (cloud resources) ───────────────
# Current options: aws
# Future options: azure, gcp, local
CURSOR_BACKEND=aws
STATE_BACKEND=aws

# ── NinjaOne (used when SYNC_TARGET_ADAPTER=ninjaone) ─
NINJAONE_BASE_URL=https://app.ninjarmm.com
NINJAONE_CLIENT_ID=...
NINJAONE_CLIENT_SECRET=...
NINJAONE_ORG_ID=...
# JSON string mapping Google group names → NinjaOne roles
NINJAONE_GROUP_ROLE_MAP={"IT Admins": "administrator", "Support": "technician"}

# ── HTTP client tuning (applies to outbound target calls) ──
HTTP_TIMEOUT_SECONDS=30
HTTP_RETRY_MAX_ATTEMPTS=3
HTTP_RETRY_BACKOFF_BASE_SECONDS=1.0

# ── AWS (used when CURSOR_BACKEND=aws or STATE_BACKEND=aws) ──
AWS_REGION=us-east-1
SSM_CURSOR_PARAM=/workos-conduit/cursor
S3_STATE_BUCKET=workos-conduit-state
S3_STATE_PREFIX=runs/

# ── FastAPI server ────────────────────────────────────
SERVER_HOST=0.0.0.0
SERVER_PORT=8080
API_SECRET_KEY=change-me-in-production

# ── Dashboard ─────────────────────────────────────────
DASHBOARD_ENABLED=true
DASHBOARD_RUN_HISTORY_LIMIT=50
DASHBOARD_AUTO_REFRESH_SECONDS=60

# ── Logging ───────────────────────────────────────────
LOG_LEVEL=INFO
LOG_OUTPUT=stdout                # stdout | file | both
LOG_FORMAT=json                  # json | console
LOG_FILE_PATH=/var/log/workos-conduit/app.log   # only used when LOG_OUTPUT != stdout
```

---

## Phase 1 — Project Scaffolding

### 1.1 — Create `pyproject.toml`

Define under `[project]`:
- `name = "workos-conduit"`
- `version = "1.0.0"`
- `license = {text = "GPL-3.0-or-later"}`
- `requires-python = ">=3.13"`

Runtime dependencies:
```
workos>=5.0.0
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
jinja2>=3.1.0
python-dotenv>=1.0.0
pydantic-settings>=2.5.0
structlog>=24.0.0
boto3>=1.35.0
httpx>=0.27.0
```

Dev dependencies (under `[project.optional-dependencies]` key `dev`):
```
pytest>=8.0.0
pytest-asyncio>=0.24.0
pytest-mock>=3.14.0
pytest-cov>=5.0.0
respx>=0.21.0
moto[s3,ssm]>=5.0.0
black>=24.0.0
ruff>=0.6.0
```

Under `[tool.black]`:
```toml
[tool.black]
line-length = 88
target-version = ["py313"]
```

Under `[tool.ruff]`:
```toml
[tool.ruff]
line-length = 88
target-version = "py313"
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501"]
```

Under `[tool.pytest.ini_options]`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "--cov=src --cov-report=xml --cov-report=term-missing -v"
```

### 1.2 — Create `src/config.py`

Use `pydantic-settings` `BaseSettings`. All fields map to environment variables.

```python
class Settings(BaseSettings):
    # WorkOS
    workos_api_key: str
    workos_directory_id: str
    workos_event_types: list[str] = [
        "dsync.user.created",
        "dsync.user.updated",
        "dsync.user.deleted",
        "dsync.group.user_added",
        "dsync.group.user_removed",
    ]
    workos_events_page_size: int = 100

    # Adapter selection
    sync_target_adapter: str = "ninjaone"
    sync_stop_on_error: bool = True

    # Backend selection
    cursor_backend: str = "aws"
    state_backend: str = "aws"

    # NinjaOne (only required when adapter=ninjaone)
    ninjaone_base_url: str = "https://app.ninjarmm.com"
    ninjaone_client_id: str = ""
    ninjaone_client_secret: str = ""
    ninjaone_org_id: str = ""
    ninjaone_group_role_map: str = "{}"

    # HTTP tuning
    http_timeout_seconds: int = 30
    http_retry_max_attempts: int = 3
    http_retry_backoff_base_seconds: float = 1.0

    # AWS
    aws_region: str = "us-east-1"
    ssm_cursor_param: str = "/workos-conduit/cursor"
    s3_state_bucket: str = ""
    s3_state_prefix: str = "runs/"

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8080
    api_secret_key: str

    # Dashboard
    dashboard_enabled: bool = True
    dashboard_run_history_limit: int = 50
    dashboard_auto_refresh_seconds: int = 60

    # Logging
    log_level: str = "INFO"
    log_output: str = "stdout"           # stdout | file | both
    log_format: str = "json"             # json | console
    log_file_path: str = "/var/log/workos-conduit/app.log"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    @model_validator(mode="after")
    def validate_adapter_config(self) -> "Settings":
        if self.sync_target_adapter == "ninjaone":
            if not self.ninjaone_client_id or not self.ninjaone_client_secret:
                raise ValueError(
                    "ninjaone_client_id and ninjaone_client_secret required "
                    "when sync_target_adapter=ninjaone"
                )
        if self.state_backend == "aws" and not self.s3_state_bucket:
            raise ValueError("s3_state_bucket required when state_backend=aws")
        return self
```

Expose a `get_settings()` function cached with `@lru_cache`.

### 1.3 — Create `src/logging_config.py`

```python
def configure_logging(settings: Settings) -> None:
    """
    Configure structlog + stdlib logging based on settings.

    Behaviour:
      - log_output=stdout (default): writes to sys.stdout only.
        Ideal for containerised deploys (ECS awslogs driver, Docker, k8s).
      - log_output=file: writes to log_file_path only (rotating file handler).
      - log_output=both: writes to both.
      - log_format=json: renders structured JSON (one event per line).
        Consume directly from CloudWatch Logs Insights, Datadog, Splunk.
      - log_format=console: renders human-readable colorised output.
        Use for local dev (LOG_FORMAT=console make dev).

    All log records include: timestamp, level, logger, event, plus any
    bound context (run_id, event_id, adapter, etc).
    """
```

---

## Phase 2 — Shared Pydantic Models

### 2.1 — Create `src/core/models.py`

These models are **adapter-agnostic and backend-agnostic**. Used across the entire application.

```python
class SyncAction(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    DEACTIVATED = "deactivated"
    SKIPPED = "skipped"
    NO_CHANGE = "no_change"
    ROLE_ASSIGNED = "role_assigned"
    NOT_FOUND_SKIPPED = "not_found_skipped"
    ALREADY_INACTIVE = "already_inactive"
    ERROR = "error"

class RunStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    ERROR = "error"
    NO_EVENTS = "no_events"

class HandlerResult(BaseModel):
    event_id: str
    event_type: str
    action: SyncAction
    target_adapter: str
    email: str | None = None
    target_user_id: str | None = None
    changed_fields: list[str] | None = None
    role: str | None = None
    error_message: str | None = None
    duration_ms: int = 0

class RunError(BaseModel):
    event_id: str
    event_type: str
    error_message: str
    traceback: str | None = None

class RunRecord(BaseModel):
    run_id: str
    adapter: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    status: RunStatus
    trigger_source: str           # "api" | "dashboard" | "scheduler"
    events_fetched: int
    events_processed: int
    cursor_before: str | None
    cursor_after: str | None
    results: list[HandlerResult]
    errors: list[RunError]

    @property
    def counts(self) -> dict[str, int]:
        """Returns count of each SyncAction across results."""
        ...
```

---

## Phase 3 — Backend Interfaces (Pluggable Cloud Resources)

### 3.1 — Create `src/backends/base.py`

```python
class CursorBackend(ABC):
    """
    Persists the last-seen WorkOS event ID.
    Implementations: AWS SSM today; Azure AppConfig / GCS / local file later.
    """

    @abstractmethod
    def get(self) -> str | None:
        """Return saved event ID or None if unset (first run). Never raise on missing."""

    @abstractmethod
    def save(self, event_id: str) -> None:
        """Overwrite saved event ID. Called once per successfully processed event."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the cursor store is reachable."""


class StateBackend(ABC):
    """
    Persists immutable RunRecord JSON documents.
    Implementations: AWS S3 today; Azure Blob / GCS / local filesystem later.
    """

    @abstractmethod
    def write_run(self, record: RunRecord) -> str:
        """Serialise and persist a RunRecord. Return backend-specific key/URI. APPEND-ONLY."""

    @abstractmethod
    def get_run(self, run_id: str) -> RunRecord | None:
        """Return single RunRecord by ID. None if not found."""

    @abstractmethod
    def list_recent_runs(self, limit: int) -> list[RunRecord]:
        """Return up to `limit` most recent runs, sorted newest-first."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the state store is reachable."""
```

### 3.2 — Create `src/backends/registry.py`

```python
"""
Registry for backend implementations.
One registry per backend type (cursor vs state) — cleaner than a single union map.

To register a new backend:
  from src.backends.azure.cursor_appconfig import AppConfigCursorBackend
  register_cursor_backend("azure", lambda s: AppConfigCursorBackend(s))
"""

_CURSOR_REGISTRY: dict[str, Callable[[Settings], CursorBackend]] = {}
_STATE_REGISTRY:  dict[str, Callable[[Settings], StateBackend]]  = {}

def register_cursor_backend(key: str, factory: Callable[[Settings], CursorBackend]) -> None: ...
def register_state_backend(key:  str, factory: Callable[[Settings], StateBackend])  -> None: ...

def get_cursor_backend(key: str, settings: Settings) -> CursorBackend: ...
def get_state_backend(key:  str, settings: Settings) -> StateBackend:  ...

# Register AWS backends (only implementation today):
from src.backends.aws.cursor_ssm import SsmCursorBackend    # noqa: E402
from src.backends.aws.state_s3   import S3StateBackend      # noqa: E402

register_cursor_backend("aws", lambda s: SsmCursorBackend(s))
register_state_backend("aws",  lambda s: S3StateBackend(s))
```

### 3.3 — Create `src/backends/aws/cursor_ssm.py`

```python
class SsmCursorBackend(CursorBackend):
    def __init__(self, settings: Settings):
        self._client = boto3.client("ssm", region_name=settings.aws_region)
        self._param  = settings.ssm_cursor_param

    def get(self) -> str | None:
        """GetParameter; return None on ParameterNotFound. Never raise on missing."""

    def save(self, event_id: str) -> None:
        """PutParameter Type=String Overwrite=True. Log at DEBUG."""

    def health_check(self) -> bool:
        """DescribeParameters with ParameterFilter for the param; return True on 200."""
```

### 3.4 — Create `src/backends/aws/state_s3.py`

```python
class S3StateBackend(StateBackend):
    def __init__(self, settings: Settings):
        self._client = boto3.client("s3", region_name=settings.aws_region)
        self._bucket = settings.s3_state_bucket
        self._prefix = settings.s3_state_prefix

    def write_run(self, record: RunRecord) -> str:
        """
        Serialise via record.model_dump_json().
        Key: {prefix}{YYYY}/{MM}/{DD}/{run_id}.json
        ContentType: application/json
        APPEND-ONLY — never overwrite existing keys.
        Return S3 key.
        """

    def get_run(self, run_id: str) -> RunRecord | None:
        """List under prefix, find key containing run_id, parse."""

    def list_recent_runs(self, limit: int) -> list[RunRecord]:
        """list_objects_v2; sort by LastModified desc; fetch up to `limit`."""

    def health_check(self) -> bool:
        """HeadBucket; True on 200/404-in-bucket; False on connection error."""
```

---

## Phase 4 — Adapter Interface (Target Plugin System)

### 4.1 — Create `src/adapters/base.py`

```python
class ProvisioningUser(BaseModel):
    """
    Canonical, adapter-agnostic user model.
    WorkOS events are always mapped to this before reaching any adapter.
    """
    email: str
    first_name: str
    last_name: str
    is_active: bool
    department: str | None = None
    job_title: str | None = None
    external_id: str           # WorkOS directory_user ID

class ProvisioningGroup(BaseModel):
    """Canonical group membership event."""
    user: ProvisioningUser
    group_name: str
    action: str                # "added" | "removed"

class BaseTargetAdapter(ABC):
    """
    Abstract base class for all provisioning targets.

    To add a new target (e.g. Zendesk):
      1. Create src/adapters/zendesk/adapter.py
      2. Implement ZendeskAdapter(BaseTargetAdapter)
      3. Register in src/adapters/registry.py with register_adapter("zendesk", ...)
      No other files need to change.
    """

    @property
    @abstractmethod
    def adapter_key(self) -> str:
        """Unique identifier string e.g. 'ninjaone', 'zendesk'."""

    @abstractmethod
    def provision_user_created(self, user: ProvisioningUser) -> HandlerResult: ...

    @abstractmethod
    def provision_user_updated(self, user: ProvisioningUser) -> HandlerResult: ...

    @abstractmethod
    def provision_user_deactivated(self, user: ProvisioningUser) -> HandlerResult: ...

    @abstractmethod
    def provision_group_membership(self, group: ProvisioningGroup) -> HandlerResult: ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if target system is reachable. Used by /health/ready."""
```

### 4.2 — Create `src/adapters/registry.py`

Same pattern as `backends/registry.py`:

```python
_REGISTRY: dict[str, Callable[[Settings], BaseTargetAdapter]] = {}

def register_adapter(key: str, factory: Callable[[Settings], BaseTargetAdapter]) -> None: ...
def get_adapter(key: str, settings: Settings) -> BaseTargetAdapter: ...

# Register built-in adapters:
from src.adapters.ninjaone.adapter import NinjaOneAdapter  # noqa: E402
register_adapter("ninjaone", lambda s: NinjaOneAdapter(s))
```

---

## Phase 5 — NinjaOne Adapter

### 5.1 — Create `src/adapters/ninjaone/client.py`

Implement `NinjaOneAPIClient`:

- `__init__(settings)` — stores credentials, reads `http_timeout_seconds`, `http_retry_max_attempts`, `http_retry_backoff_base_seconds` from settings.
- `_get_token() -> str` — POST `{base_url}/ws/oauth/token` with `grant_type=client_credentials&scope=monitoring management`. Cache token in `self._token`, refresh 60s before expiry. Use `threading.Lock` for thread safety.
- `_request(method, path, **kwargs) -> dict` — authenticated request with retry: 429 → sleep Retry-After + retry once; 5xx → exponential backoff `base * 2^n` up to `retry_max_attempts`; 4xx → raise `NinjaOneAPIError(status_code, response_body)` immediately.
- `get_technicians() -> list[dict]` — GET `/api/v2/users?userType=TECHNICIAN`
- `find_technician_by_email(email) -> dict | None`
- `create_technician(payload) -> dict` — POST `/api/v2/users`
- `update_technician(user_id, payload) -> dict` — PATCH `/api/v2/users/{user_id}`
- `deactivate_technician(user_id) -> None` — PATCH `/api/v2/users/{user_id}` body `{"enabled": false}`
- `health_check() -> bool` — GET `/api/v2/users?userType=TECHNICIAN&limit=1`, return True on 200

Define `class NinjaOneAPIError(Exception)` with `status_code: int` and `response_body: str`.

### 5.2 — Create `src/adapters/ninjaone/mapper.py`

```python
def workos_to_ninjaone(user: ProvisioningUser, org_id: str) -> dict:
    """Maps ProvisioningUser → NinjaOne technician create/update payload."""
    return {
        "firstName": user.first_name,
        "lastName": user.last_name,
        "email": user.email,
        "userType": "TECHNICIAN",
        "mustChangePassword": False,
        "enabled": user.is_active,
    }

def workos_group_to_ninjaone_role(group_name: str, role_map: dict[str, str]) -> str | None:
    """
    Looks up group_name in role_map.
    role_map loaded from NINJAONE_GROUP_ROLE_MAP env var (JSON string).
    Returns None if group_name not found — caller logs warning, does not fail.
    """
```

### 5.3 — Create `src/adapters/ninjaone/adapter.py`

Implement `NinjaOneAdapter(BaseTargetAdapter)`:

- `adapter_key = "ninjaone"`
- `__init__(settings)` — instantiates `NinjaOneAPIClient(settings)`, loads `_role_map` from `json.loads(settings.ninjaone_group_role_map)`

Each method follows the idempotency contract from `BaseTargetAdapter`:

`provision_user_created`:
1. `find_technician_by_email(user.email)` — if found, return `SKIPPED`
2. `workos_to_ninjaone(user, org_id)` → `create_technician(payload)`
3. Return `HandlerResult(action=CREATED, target_user_id=str(resp["id"]))`

`provision_user_updated`:
1. Find by email — if not found, delegate to `provision_user_created`
2. Compute diff between current NinjaOne fields and new `ProvisioningUser`
3. If no diff → `NO_CHANGE`. If diff → `update_technician(id, diff_only)` → `UPDATED`

`provision_user_deactivated`:
1. Find by email → if not found `NOT_FOUND_SKIPPED`
2. If `enabled == False` → `ALREADY_INACTIVE`
3. `deactivate_technician(id)` → `DEACTIVATED`

`provision_group_membership`:
1. `workos_group_to_ninjaone_role(group.group_name, self._role_map)` → if None → `SKIPPED`
2. Find user by email → `update_technician(id, {"role": role})` → `ROLE_ASSIGNED`

`health_check` → delegates to `self._client.health_check()`

---

## Phase 6 — WorkOS Events Client

### 6.1 — Create `src/workos/client.py`

```python
class WorkOSEventsClient:
    def __init__(self, settings: Settings):
        self._client     = workos.WorkOSClient(api_key=settings.workos_api_key)
        self._types      = settings.workos_event_types
        self._page_size  = settings.workos_events_page_size

    def list_events(self, after: str | None = None) -> tuple[list[dict], str | None]:
        """
        Calls workos SDK: workos_client.events.list_events(
            events=self._types, after=after, limit=self._page_size
        )
        Returns (events_list, last_event_id).
        last_event_id = events_list[-1]["id"] if non-empty, else None.
        """
```

---

## Phase 7 — Event Handlers, Router, Sync Run Context, and Sync Engine

### 7.1 — Create `src/handlers/base.py`

```python
class BaseEventHandler(ABC):
    @abstractmethod
    def can_handle(self, event_type: str) -> bool: ...

    @abstractmethod
    def handle(self, event: dict, adapter: BaseTargetAdapter) -> HandlerResult: ...

    def _workos_event_to_user(self, event_data: dict) -> ProvisioningUser:
        """
        Maps raw WorkOS dsync event data → ProvisioningUser canonical model.
        Extracts: email, first_name, last_name, state (→ is_active),
        custom_attributes.department, custom_attributes.job_title, id (→ external_id).
        Shared utility for all user event handlers.
        """
```

### 7.2 — Create handler implementations

`src/handlers/user_created.py`:
- `can_handle`: returns `event_type == "dsync.user.created"`
- `handle`: `_workos_event_to_user(event["data"])` → `adapter.provision_user_created(user)`

`src/handlers/user_updated.py`:
- `can_handle`: `event_type == "dsync.user.updated"`
- `handle`: same pattern → `adapter.provision_user_updated(user)`

`src/handlers/user_deleted.py`:
- `can_handle`: `event_type == "dsync.user.deleted"`
- `handle`: `_workos_event_to_user` with `is_active=False` → `adapter.provision_user_deactivated(user)`

`src/handlers/group_membership.py`:
- `can_handle`: `event_type in ("dsync.group.user_added", "dsync.group.user_removed")`
- `handle`: build `ProvisioningGroup(user=..., group_name=event["data"]["group"]["name"], action=...)` → `adapter.provision_group_membership(group)`

### 7.3 — Create `src/core/event_router.py`

```python
class EventRouter:
    def __init__(self, handlers: list[BaseEventHandler]): ...

    def route(self, event: dict, adapter: BaseTargetAdapter) -> HandlerResult:
        """
        Find first handler where can_handle(event["event"]) is True.
        If none: return HandlerResult(action=SKIPPED, event_type=..., event_id=...).
        Wrap handler.handle() in try/except:
          On exception: return HandlerResult(action=ERROR, error_message=str(e)).
          Never propagate exceptions from route().
        """
```

### 7.4 — Create `src/core/sync_run.py` (Unit of Work)

```python
class SyncRunContext:
    """
    Unit of Work object for a single run_cycle execution.

    Owns all mutable run state so SyncEngine stays a thin orchestrator.
    Responsibilities:
      - generate run_id
      - track started_at / finished_at / cursor_before / cursor_after
      - accumulate results + errors
      - derive final RunStatus from accumulated state
      - produce an immutable RunRecord via finalize()
    """

    @classmethod
    def start(
        cls,
        adapter_key: str,
        trigger_source: str,
        cursor_before: str | None,
    ) -> "SyncRunContext": ...

    def record_fetched(self, count: int) -> None: ...

    def record_result(self, result: HandlerResult) -> None: ...

    def record_error(self, event: dict, exc: Exception) -> None:
        """Appends RunError with traceback."""

    def advance_cursor(self, event_id: str) -> None:
        """Sets cursor_after; called only after successful processing."""

    def has_errors(self) -> bool: ...

    def finalize(self) -> RunRecord:
        """
        Computes RunStatus:
          - NO_EVENTS if events_fetched == 0
          - ERROR if last action was ERROR and loop terminated early
          - PARTIAL_FAILURE if any ERROR but loop completed
          - SUCCESS otherwise
        Returns immutable RunRecord.
        """
```

### 7.5 — Create `src/core/sync_engine.py`

```python
class SyncEngine:
    def __init__(
        self,
        workos_client: WorkOSEventsClient,
        adapter: BaseTargetAdapter,
        cursor_backend: CursorBackend,
        state_backend: StateBackend,
        event_router: EventRouter,
        settings: Settings,
    ): ...

    def run_cycle(self, trigger_source: str = "api") -> RunRecord:
        """
        Pipeline (all state lives in SyncRunContext):

        1. ctx = SyncRunContext.start(
               adapter_key=self._adapter.adapter_key,
               trigger_source=trigger_source,
               cursor_before=self._cursor.get(),
           )
        2. events, _ = self._workos.list_events(after=ctx.cursor_before)
           ctx.record_fetched(len(events))
        3. If not events → goto step 5 (NO_EVENTS)
        4. For each event (sequential — preserves WorkOS ordering):
             result = self._router.route(event, self._adapter)
             ctx.record_result(result)
             if result.action == SyncAction.ERROR:
                 ctx.record_error(event, ...)
                 if self._settings.sync_stop_on_error:
                     break                          ← stop early (default)
                 continue                           ← skip this event (cursor NOT advanced)
             self._cursor.save(event["id"])
             ctx.advance_cursor(event["id"])
        5. record = ctx.finalize()
        6. self._state.write_run(record)
        7. log cycle summary at INFO (run_id, status, events_processed, duration)
        8. return record
        """
```

> **Cursor-advance semantics**: cursor only moves past events that processed cleanly. If `sync_stop_on_error=True` (default), the failing event is retried on the next cycle. If `sync_stop_on_error=False`, the failing event is effectively skipped on the next cycle because subsequent successful events advance the cursor past it — document this tradeoff in `CONTRIBUTING.md`.

---

## Phase 8 — FastAPI Application

### 8.1 — Create `src/deps.py`

FastAPI dependencies using `Depends`. All clients are instantiated once per request (stateless) or cached via `@lru_cache` where safe (settings, boto3 clients, backends).

```python
def get_settings() -> Settings: ...                        # @lru_cache
def get_workos_client(...) -> WorkOSEventsClient: ...
def get_cursor_backend(settings) -> CursorBackend:
    """backends.registry.get_cursor_backend(settings.cursor_backend, settings)"""
def get_state_backend(settings) -> StateBackend:
    """backends.registry.get_state_backend(settings.state_backend, settings)"""
def get_adapter(settings) -> BaseTargetAdapter:
    """adapters.registry.get_adapter(settings.sync_target_adapter, settings)"""
def get_event_router() -> EventRouter:
    """Returns EventRouter with all built-in handlers registered."""
def get_sync_engine(...) -> SyncEngine: ...
```

### 8.2 — Create `src/api/health.py`

```python
@router.get("/")
async def liveness() -> dict:
    """Always 200. Used by ECS container health check."""
    return {"status": "ok"}

@router.get("/ready")
async def readiness(
    adapter:        BaseTargetAdapter = Depends(get_adapter),
    cursor_backend: CursorBackend     = Depends(get_cursor_backend),
    state_backend:  StateBackend      = Depends(get_state_backend),
) -> dict:
    """
    Checks adapter + both backends via their health_check().
    200 {"status": "ready", "adapter": key, "cursor_backend": ..., "state_backend": ...}
    503 {"status": "unavailable", ...failing components...}
    """
```

### 8.3 — Create `src/api/sync.py`

```python
class TriggerRequest(BaseModel):
    trigger_source: str = "api"

class TriggerResponse(BaseModel):
    run_id: str
    status: RunStatus
    events_processed: int
    duration_seconds: float
    adapter: str
    message: str

@router.post("/trigger", response_model=TriggerResponse)
async def trigger_sync(
    request:  TriggerRequest,
    engine:   SyncEngine = Depends(get_sync_engine),
    x_api_key: str       = Header(alias="X-API-Key"),
    settings: Settings   = Depends(get_settings),
) -> TriggerResponse:
    """
    Triggers a complete sync cycle synchronously.
    Requires X-API-Key header matching settings.api_secret_key.
    Returns 401 on missing/wrong key.
    Returns completed RunRecord summary.
    This is the ONLY way to trigger a sync — no internal timer exists.
    """

@router.get("/status")
async def sync_status(state_backend: StateBackend = Depends(get_state_backend)) -> dict:
    """Returns most recent run record summary."""
```

### 8.4 — Create `src/api/runs.py`

```python
@router.get("/", response_model=list[RunRecord])
async def list_runs(
    limit: int = Query(default=50, le=200),
    state_backend: StateBackend = Depends(get_state_backend),
) -> list[RunRecord]:
    """Returns `limit` most recent runs from state backend, most recent first."""

@router.get("/{run_id}", response_model=RunRecord)
async def get_run(
    run_id: str,
    state_backend: StateBackend = Depends(get_state_backend),
) -> RunRecord:
    """Returns single run by run_id. 404 if not found."""
```

### 8.5 — Create `src/dashboard/router.py`

```python
templates = Jinja2Templates(directory="src/dashboard/templates")

@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    state_backend: StateBackend = Depends(get_state_backend),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """
    If settings.dashboard_enabled is False → 404.
    Fetches up to settings.dashboard_run_history_limit runs from state backend.
    Computes server-side: total_runs, last_run, health status, events_last_24h,
    and action counts (created/updated/deactivated/skipped/errors).
    Renders index.html with full context.
    """

@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(
    run_id: str,
    request: Request,
    state_backend: StateBackend = Depends(get_state_backend),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Renders run_detail.html. 404 if run not found or dashboard disabled."""
```

Helper functions (private, in same file):
- `_compute_health(runs: list[RunRecord]) -> str` → `"healthy"` if last 5 all SUCCESS; `"degraded"` if any PARTIAL_FAILURE; `"down"` if last run ERROR
- `_count_events_last_24h(runs: list[RunRecord]) -> int`
- `_compute_action_totals(runs: list[RunRecord]) -> dict[str, int]`

### 8.6 — Create `src/main.py`

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    log.info(
        "workos_conduit_started",
        adapter=settings.sync_target_adapter,
        cursor_backend=settings.cursor_backend,
        state_backend=settings.state_backend,
        dashboard_enabled=settings.dashboard_enabled,
    )
    yield
    log.info("workos_conduit_stopped")

def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="WorkOS Conduit",
        description="Generic user provisioning bridge: WorkOS → third-party targets",
        version="1.0.0",
        license_info={"name": "GPL-3.0-or-later", "url": "https://www.gnu.org/licenses/gpl-3.0"},
        lifespan=lifespan,
    )
    app.include_router(health_router, prefix="/health")
    app.include_router(sync_router,   prefix="/api/v1/sync")
    app.include_router(runs_router,   prefix="/api/v1/runs")
    if settings.dashboard_enabled:
        app.include_router(dashboard_router)
    return app

app = create_app()
```

---

## Phase 9 — Dashboard Templates

### 9.1 — Create `src/dashboard/templates/base.html`

- `<meta http-equiv="refresh" content="{{ dashboard_auto_refresh_seconds }}">` — configurable auto-refresh
- Google Fonts: `Syne` (headings) + `IBM Plex Mono` (IDs/timestamps)
- CSS custom properties: `--bg: #0d1117`, `--surface: #161b22`, `--border: #30363d`
- Status colors: `--green: #3fb950`, `--amber: #d29922`, `--red: #f85149`, `--blue: #58a6ff`, `--muted: #8b949e`
- Sticky nav: app title `WorkOS → {{ adapter }} Conduit`, health pill (colored by health status), last-run timestamp chip
- `{% block content %}{% endblock %}`

### 9.2 — Create `src/dashboard/templates/index.html`

Extends `base.html`. Receives: `runs`, `total_runs`, `last_run`, `health`, `events_last_24h`, `adapter`, `action_totals`, `dashboard_auto_refresh_seconds`.

**Section 1 — Summary stat cards** (horizontal row of 4):
- Total Runs / Events 24h / Last Status (badge) / Last Duration

**Section 2 — Action bar**:
- `Trigger Sync Now` button — on click, shows modal to enter API key, then calls `POST /api/v1/sync/trigger` via `fetch()` with `X-API-Key` header
- On success: green toast "Sync triggered — refreshing in 5s", then `setTimeout(() => location.reload(), 5000)`
- On error: red toast with error detail from response JSON
- JS must be inline `<script>` in this template (no external JS files)

**Section 3 — Run history table**:
Columns: `Run ID` (first 8 chars, monospace, links to `/runs/{run_id}`), `Started`, `Duration`, `Fetched`, `Created`, `Updated`, `Deactivated`, `Errors`, `Status`
- Status: colored pill badge
- Rows with `errors > 0`: amber `border-left` highlight
- Empty state: centered "No sync runs yet — trigger the first sync above."

**Section 4 — Action breakdown bar** (CSS-only, no JS chart library):
- Horizontal stacked bar: created (green) / updated (blue) / deactivated (amber) / skipped (muted) / errors (red)
- Widths are percentages computed server-side in Jinja2 and applied as `style="width: X%"`
- Legend row below bar

### 9.3 — Create `src/dashboard/templates/run_detail.html`

Extends `base.html`. Receives: `run` (full `RunRecord`).

Sections in order:
1. Run header: `run_id` (monospace), adapter badge, `trigger_source` chip, `started_at`, `duration_seconds`, status badge
2. Stats row: events_fetched / events_processed / errors count
3. Cursor row: `cursor_before` → (arrow) → `cursor_after` (both monospace)
4. Results table: `event_type` | action badge | `email` | `target_user_id` | `changed_fields` | `duration_ms`
5. Errors section (only rendered if `run.errors` is non-empty): red-bordered table with `event_id`, `event_type`, `error_message`
6. Back link → `/`

---

## Phase 10 — Tests

### 10.1 — Create `tests/conftest.py`

```python
@pytest.fixture
def settings_override() -> Settings: ...

@pytest.fixture
def test_client(settings_override) -> TestClient: ...

@pytest.fixture
def aws_credentials(monkeypatch):
    """Sets fake AWS credentials so moto works without real creds."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

@pytest.fixture
def mock_s3(aws_credentials):
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        yield s3

@pytest.fixture
def mock_ssm(aws_credentials):
    with mock_aws():
        yield boto3.client("ssm", region_name="us-east-1")

@pytest.fixture
def workos_user_created_event() -> dict: ...
@pytest.fixture
def workos_user_updated_event() -> dict: ...
@pytest.fixture
def workos_user_deleted_event() -> dict: ...

@pytest.fixture
def sample_run_records(mock_s3) -> list[RunRecord]:
    """Seeds 5 RunRecord objects via S3StateBackend, returns sorted most-recent-first."""
```

### 10.2 — Create fixture JSON files in `tests/fixtures/`

Five complete, realistic WorkOS event payloads:
- `workos_user_created.json` — full `dsync.user.created` with `custom_attributes` populated
- `workos_user_updated.json` — full `dsync.user.updated` with `previous_attributes` showing changed `job_title`
- `workos_user_deleted.json` — `dsync.user.deleted` with `state: "inactive"`
- `workos_group_user_added.json` — `dsync.group.user_added` with nested `user` and `group` objects
- `workos_group_user_removed.json` — `dsync.group.user_removed`

### 10.3 — Unit: `tests/unit/test_mapper_ninjaone.py`

- Active user (`state: "active"`) → `enabled: True`
- Inactive user (`state: "inactive"`) → `enabled: False`
- Missing `custom_attributes` key → does not raise, returns valid payload
- All required NinjaOne fields present: `firstName`, `lastName`, `email`, `userType`
- `workos_group_to_ninjaone_role` with known group → returns mapped role
- `workos_group_to_ninjaone_role` with unknown group → returns `None`

### 10.4 — Unit: `tests/unit/test_event_router.py`

- `dsync.user.created` → `UserCreatedHandler`
- `dsync.user.updated` → `UserUpdatedHandler`
- `dsync.user.deleted` → `UserDeletedHandler`
- `dsync.group.user_added` → `GroupMembershipHandler`
- `dsync.group.user_removed` → `GroupMembershipHandler`
- Unknown event type → `HandlerResult(action=SKIPPED)`
- Handler raising `RuntimeError` → `HandlerResult(action=ERROR)`, does not propagate

### 10.5 — Unit: `tests/unit/test_sync_run.py`

- `SyncRunContext.start` populates run_id (UUID v4), started_at, cursor_before
- `record_result` accumulates; `has_errors()` flips only on ERROR action
- `finalize()` with 0 events → status=NO_EVENTS
- `finalize()` with all success → status=SUCCESS
- `finalize()` with 1 error mid-stream → status=PARTIAL_FAILURE
- `finalize()` with first-event error when stop_on_error=True → status=ERROR
- `finalize()` sets finished_at and duration_seconds correctly

### 10.6 — Unit: `tests/unit/test_sync_engine.py`

Use `pytest-mock` to mock all dependencies:

- 0 events from WorkOS → `RunRecord(status=NO_EVENTS, events_fetched=0, events_processed=0)`
- 3 events, all success → `status=SUCCESS`, cursor saved 3 times in order
- 3 events, event 2 ERROR with `stop_on_error=True` → loop breaks after event 2, `status=PARTIAL_FAILURE`, cursor saved once
- 3 events, event 2 ERROR with `stop_on_error=False` → loop continues, cursor saved twice (events 1 and 3), `status=PARTIAL_FAILURE`
- `state_backend.write_run` called exactly once per `run_cycle()` regardless of outcome
- `trigger_source` propagates to `RunRecord.trigger_source`

### 10.7 — Unit: `tests/unit/handlers/test_user_created.py`

Use a mock `BaseTargetAdapter`:
- User does not exist → calls `provision_user_created`, returns `CREATED`
- User already exists → `provision_user_created` returns `SKIPPED`, no duplicate creation

### 10.8 — Unit: `tests/unit/handlers/test_user_updated.py`

- User exists, fields changed → `UPDATED` with non-empty `changed_fields`
- User exists, no field changes → `NO_CHANGE`
- User not found → adapter falls through to creation path → `CREATED`

### 10.9 — Unit: `tests/unit/handlers/test_user_deleted.py`

- Active user → `DEACTIVATED`
- Already inactive user → `ALREADY_INACTIVE`
- User not found in target → `NOT_FOUND_SKIPPED`

### 10.10 — Unit: `tests/unit/handlers/test_group_membership.py`

- Group with role mapping, action=added → `ROLE_ASSIGNED`
- Group with no mapping → `SKIPPED`
- action=removed → resets to default role

### 10.11 — Unit: `tests/unit/test_cursor_ssm.py` (uses moto)

- `get()` before any save → `None`
- `save("evt_001")` then `get()` → `"evt_001"`
- `save("evt_001")` then `save("evt_002")` then `get()` → `"evt_002"` (Overwrite=True)
- `health_check()` returns True when SSM reachable

### 10.12 — Unit: `tests/unit/test_state_s3.py` (uses moto)

- `write_run(record)` → S3 object exists at `runs/YYYY/MM/DD/{run_id}.json`
- `write_run` twice with different run_ids → both exist (append-only, no overwrite)
- `list_recent_runs(limit=3)` with 10 records → returns 3 most recent, sorted desc
- `get_run(run_id)` → returns correct `RunRecord`
- `get_run("does-not-exist")` → `None`
- `health_check()` returns True when bucket exists

### 10.13 — Unit: `tests/unit/test_backend_registry.py`

- `get_cursor_backend("aws", settings)` → `SsmCursorBackend` instance
- `get_state_backend("aws", settings)` → `S3StateBackend` instance
- Unknown key → raises with helpful message listing available keys
- Custom registered backend resolvable after `register_*_backend` call

### 10.14 — Integration: `tests/integration/test_api_sync.py`

```python
def test_trigger_sync_success(test_client, mocker): ...
def test_trigger_sync_wrong_api_key(test_client): ...
def test_trigger_sync_missing_api_key(test_client): ...
def test_trigger_sync_dashboard_source(test_client, mocker): ...
def test_sync_status_empty(test_client, mocker): ...
```

### 10.15 — Integration: `tests/integration/test_api_runs.py`

```python
def test_list_runs_empty(test_client, mock_s3): ...
def test_list_runs_returns_most_recent_first(test_client, mock_s3, sample_run_records): ...
def test_list_runs_respects_limit(test_client, mock_s3, sample_run_records): ...
def test_get_run_found(test_client, mock_s3, sample_run_records): ...
def test_get_run_not_found(test_client, mock_s3): ...
```

### 10.16 — Integration: `tests/integration/test_api_health.py`

```python
def test_liveness(test_client): ...
def test_readiness_all_healthy(test_client, mocker): ...
def test_readiness_adapter_unhealthy(test_client, mocker): ...
def test_readiness_cursor_backend_unhealthy(test_client, mocker): ...
def test_readiness_state_backend_unhealthy(test_client, mocker): ...
```

---

## Phase 11 — GitHub Actions CI/CD

### 11.1 — Create `.github/workflows/ci.yml`

```yaml
name: CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Black format check
        run: black --check src tests
      - name: Ruff lint
        run: ruff check src tests
      - name: Run tests with coverage
        run: pytest --cov=src --cov-report=xml --junitxml=test-results.xml
      - name: SonarQube Scan
        uses: SonarSource/sonarqube-scan-action@master
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ secrets.SONAR_HOST_URL }}
```

### 11.2 — Create `.github/workflows/release.yml`

Trigger on tag push matching `v*.*.*`:
1. Build Docker image
2. Login to `ghcr.io` using `GITHUB_TOKEN`
3. Tag image with semver (`v1.0.0`) and `latest`
4. Push both tags to GitHub Container Registry

---

## Phase 12 — Dockerfile, Compose, Makefile

### 12.1 — Create `Dockerfile`

```dockerfile
# SPDX-License-Identifier: GPL-3.0-or-later
FROM python:3.13-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.13/site-packages \
                    /usr/local/lib/python3.13/site-packages
COPY src/ ./src/

RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser /app
USER appuser

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8080/health/ || exit 1

# Logs go to stdout by default (LOG_OUTPUT=stdout, LOG_FORMAT=json)
# ECS awslogs driver, Docker log driver, and k8s kubectl logs all consume stdout.
CMD ["python", "-m", "uvicorn", "src.main:app", \
     "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
```

### 12.2 — Create `docker-compose.yml`

```yaml
services:
  app:
    build: .
    ports: ["8080:8080"]
    env_file: .env
    volumes:
      - ~/.aws:/home/appuser/.aws:ro
      - ./src:/app/src
    environment:
      LOG_FORMAT: console           # human-readable output for local dev
    command: >
      python -m uvicorn src.main:app
      --host 0.0.0.0 --port 8080 --reload
```

### 12.3 — Create `Makefile`

```makefile
.PHONY: install dev test lint fmt fmt-check clean build run docker-build docker-run

PYTHON ?= python3.13
VENV   ?= .venv

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -e ".[dev]"

# Run with auto-reload, console logging, .env loaded
dev:
	LOG_FORMAT=console LOG_LEVEL=DEBUG \
	$(VENV)/bin/uvicorn src.main:app \
	  --host 0.0.0.0 --port 8080 --reload --reload-dir src

test:
	$(VENV)/bin/pytest

lint:
	$(VENV)/bin/ruff check src tests

fmt:
	$(VENV)/bin/black src tests
	$(VENV)/bin/ruff check --fix src tests

fmt-check:
	$(VENV)/bin/black --check src tests
	$(VENV)/bin/ruff check src tests

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache coverage.xml test-results.xml

docker-build:
	docker build -t workos-conduit:dev .

docker-run:
	docker-compose up --build
```

### 12.4 — Create `scripts/dev.sh`

```bash
#!/usr/bin/env bash
# Local dev runner — equivalent to `make dev`, for users who prefer scripts.
# Uses console log format + DEBUG level + auto-reload on src/ changes.
set -euo pipefail

cd "$(dirname "$0")/.."

export LOG_FORMAT="${LOG_FORMAT:-console}"
export LOG_LEVEL="${LOG_LEVEL:-DEBUG}"

exec .venv/bin/uvicorn src.main:app \
  --host 0.0.0.0 \
  --port "${SERVER_PORT:-8080}" \
  --reload \
  --reload-dir src
```

---

## Phase 13 — Infrastructure (AWS)

### 13.1 — Create `infra/aws/task-definition.json`

ECS Fargate task definition:
- Family: `workos-conduit`, CPU: `256`, Memory: `512`
- Container port: `8080`
- Health check: `curl -f http://localhost:8080/health/`
- Secrets from Secrets Manager: `WORKOS_API_KEY`, `NINJAONE_CLIENT_ID`, `NINJAONE_CLIENT_SECRET`, `API_SECRET_KEY`
- Environment (non-secret): `AWS_REGION`, `S3_STATE_BUCKET`, `S3_STATE_PREFIX`, `SSM_CURSOR_PARAM`, `SYNC_TARGET_ADAPTER`, `CURSOR_BACKEND=aws`, `STATE_BACKEND=aws`, `NINJAONE_BASE_URL`, `NINJAONE_ORG_ID`, `WORKOS_DIRECTORY_ID`, `LOG_LEVEL`, `LOG_OUTPUT=stdout`, `LOG_FORMAT=json`
- Log driver: `awslogs`, log group: `/ecs/workos-conduit` (picks up stdout JSON directly)

### 13.2 — Create `infra/aws/iam-task-role-policy.json`

Minimal IAM policy for the ECS **task role**:
- `ssm:GetParameter` + `ssm:PutParameter` on `arn:aws:ssm:REGION:ACCOUNT:parameter/workos-conduit/*`
- `s3:PutObject` + `s3:GetObject` + `s3:ListBucket` on the state bucket and its objects

### 13.3 — Create `infra/aws/eventbridge-schedule.json`

EventBridge Scheduler target definition for `rate(5 minutes)` that calls `POST /api/v1/sync/trigger` on the ECS service's internal URL. Include the `X-API-Key` header as a constant in the target input transformer. Include comments explaining how to adjust the schedule rate.

> **Future clouds**: to add Azure, create `infra/azure/` with an equivalent set of deployment manifests (Container Apps / Function / Logic App schedule) and a corresponding `src/backends/azure/` module. No files outside these two directories should need to change.

---

## Phase 14 — Bootstrap and Deploy

### 14.1 — Create `scripts/bootstrap.py`

```
Usage: python scripts/bootstrap.py [--dry-run] [--adapter ninjaone]

One-time import of all existing Google Workspace users.
Run BEFORE deploying the ECS task.

1. Load Settings from .env
2. Instantiate adapter via adapters.registry.get_adapter()
3. Paginate ALL users from WorkOS Directory API
   (workos_client.directory_sync.list_directory_users, NOT Events API)
4. For each user:
   a. Convert raw WorkOS user → ProvisioningUser
   b. --dry-run: print "WOULD CREATE {email}" only
   c. Live: call adapter.provision_user_created(user), print result.action
5. Print summary table: total / created / skipped / errors
```

### 14.2 — Create `scripts/deploy.sh`

```bash
#!/bin/bash
set -euo pipefail
# Args: <aws-region> <ecr-uri> <ecs-cluster> <ecs-service>
# 1. docker build, tag with git SHA and latest
# 2. aws ecr get-login-password | docker login
# 3. docker push both tags
# 4. aws ecs register-task-definition from infra/aws/task-definition.json
# 5. aws ecs update-service --force-new-deployment
# 6. Print monitoring command
```

---

## Phase 15 — Open Source Docs

### 15.1 — Create `CONTRIBUTING.md`

Include:
- **Local dev**: `make install && make dev` → dashboard at `http://localhost:8080`
- **Tests**: `make test`
- **Formatting**: `make fmt` before PR
- **Adding a new target adapter** (step-by-step):
  1. Create `src/adapters/yourname/` directory
  2. Create `client.py` for your target system's API
  3. Create `mapper.py` mapping `ProvisioningUser` → your target's payload
  4. Create `adapter.py` implementing all `BaseTargetAdapter` abstract methods
  5. Register in `src/adapters/registry.py` with `register_adapter("yourname", ...)`
  6. Add `YOURNAME_*` env vars to `config.py` and `.env.example`
  7. Write tests in `tests/unit/` and `tests/integration/`
  8. No other files need to change
- **Adding a new cloud backend** (step-by-step):
  1. Create `src/backends/<cloud>/` directory
  2. Implement `CursorBackend` and/or `StateBackend` subclasses
  3. Register in `src/backends/registry.py` with `register_cursor_backend("<cloud>", ...)` / `register_state_backend(...)`
  4. Add `<CLOUD>_*` env vars to `config.py` and `.env.example`
  5. Add deployment manifests under `infra/<cloud>/`
  6. Write tests in `tests/unit/` using the cloud's moto-equivalent mocking library
- **Cursor-advance semantics**: cursor only advances past events processed successfully. `SYNC_STOP_ON_ERROR=true` (default) retries the failing event on next cycle; `false` skips it forever — pick based on whether your target adapter is robust to replay.
- Code style: Black + ruff enforced in CI. Run `make fmt-check` before PR.
- Coverage requirement: maintain ≥80% line coverage; PRs that reduce coverage are rejected
- PR checklist template
- GPL-3.0 note: by contributing you agree code is GPL-3.0-or-later

### 15.2 — Create `CHANGELOG.md`

```markdown
# Changelog
All notable changes to this project follow [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]
### Added
- Initial implementation: WorkOS Directory Sync → NinjaOne provisioning
- Generic `BaseTargetAdapter` interface and registry for multi-target extensibility
- Generic `CursorBackend` / `StateBackend` interfaces for multi-cloud extensibility
- AWS backend implementations (SSM cursor, S3 state)
- FastAPI server: /api/v1/sync/trigger, /api/v1/runs, /health endpoints
- Built-in HTML dashboard (toggleable via DASHBOARD_ENABLED)
- SyncRunContext (Unit of Work) for clean run-cycle state management
- Configurable HTTP retries, page sizes, logging output (stdout/file/both) and format (json/console)
- Black code formatting + ruff linting enforced in CI
- SonarQube project configuration
- GPL-3.0-or-later license
- GitHub Actions CI (lint + test + SonarQube) and release (GHCR push) workflows
- Python 3.13 target, Makefile for local dev workflow
```

---

## Logging Standards (Apply to Every `.py` File)

```python
import structlog
log = structlog.get_logger()
```

Configured in `src/logging_config.py`, invoked once in `src/main.py` lifespan.

**Defaults** (production): `LOG_OUTPUT=stdout`, `LOG_FORMAT=json`. This produces one JSON object per line on stdout, consumed directly by:
- AWS CloudWatch (via ECS `awslogs` driver)
- Datadog / Splunk / Sumo (via agent tailing container stdout)
- Any future log shipper — no code change required

**Local dev**: set `LOG_FORMAT=console` for human-readable coloured output.

| Event | Level | Required Fields |
|---|---|---|
| App started | INFO | `adapter`, `cursor_backend`, `state_backend`, `version` |
| Sync triggered | INFO | `run_id`, `trigger_source` |
| Event processed | DEBUG | `event_id`, `event_type`, `action`, `email`, `duration_ms` |
| User created | INFO | `adapter`, `email`, `target_user_id`, `run_id` |
| User updated | INFO | `adapter`, `email`, `changed_fields`, `run_id` |
| User deactivated | INFO | `adapter`, `email`, `run_id` |
| Skipped | DEBUG | `reason`, `email` |
| Target API error | ERROR | `adapter`, `status_code`, `event_id` |
| Cursor saved | DEBUG | `event_id`, `cursor_backend` |
| Run written to backend | DEBUG | `backend_key`, `run_id`, `state_backend` |
| Cycle complete | INFO | `run_id`, `events_processed`, `status`, `duration_seconds` |
| Unhandled exception | CRITICAL | `error`, `traceback` |

---

## Implementation Sequence

Execute phases **in this exact order**:

```
Phase  1  →  Scaffolding (pyproject.toml, config.py, logging_config.py, LICENSE, Makefile)
Phase  2  →  Core models (models.py — RunRecord, HandlerResult, ProvisioningUser, etc.)
Phase  3  →  Backend interfaces + AWS implementations (backends/base.py, registry.py, aws/*)
Phase  4  →  Adapter interface (adapters/base.py, registry.py)
Phase  5  →  NinjaOne adapter (client.py, mapper.py, adapter.py)
Phase  6  →  WorkOS client (workos/client.py)
Phase  7  →  Handlers + EventRouter + SyncRunContext + SyncEngine
Phase  8  →  FastAPI app (deps.py, api/*, dashboard/router.py, main.py)
Phase  9  →  Dashboard templates (base.html, index.html, run_detail.html)
Phase 10  →  All tests (conftest, fixtures, unit, integration)
Phase 11  →  GitHub Actions CI + release workflows
Phase 12  →  Dockerfile + docker-compose.yml + Makefile + scripts/dev.sh
Phase 13  →  infra/aws/ (task-definition, IAM policy, EventBridge schedule)
Phase 14  →  scripts/ (bootstrap.py, deploy.sh)
Phase 15  →  Open source docs (CONTRIBUTING.md, CHANGELOG.md, sonar-project.properties)
```

---

## Key Architectural Decisions (Do Not Change)

| Decision | Rationale |
|---|---|
| Sync triggered only via `POST /api/v1/sync/trigger` | Decouples scheduling; EventBridge, cron, or dashboard all use same endpoint |
| `BaseTargetAdapter` ABC + registry | Adding Zendesk/Freshservice = 1 new module + 1 registry call |
| `CursorBackend` / `StateBackend` ABCs + registry | Adding Azure/GCS/local = 1 new module + 1 registry call; no core changes |
| AWS-only concrete backend today | Keeps v1 surface area small; abstraction ready for future clouds |
| Canonical `ProvisioningUser` between WorkOS and adapters | Handlers are 100% adapter-agnostic |
| Cursor saved only after successful adapter write | Zero skipped events on crash/restart when `sync_stop_on_error=True` |
| State records are append-only | Immutable audit log; no database needed |
| SyncRunContext owns all run state (Unit of Work) | SyncEngine becomes a thin orchestrator; testable run lifecycle |
| Dashboard served by FastAPI via Jinja2, toggleable | One container, no S3 static hosting, no separate web server; disable for API-only deploys |
| Single-threaded event processing per cycle | Preserves WorkOS ordering guarantees |
| `moto` for all AWS tests | No real AWS creds in CI |
| Black + ruff enforced in CI | Zero style debates in PR reviews |
| Stdout-first JSON logs | CloudWatch / Datadog / Splunk all work unchanged |

---

## Pre-Deployment Checklist

- [ ] WorkOS Directory Sync connected to Google Workspace
- [ ] NinjaOne API credentials created (Administration → Apps → API)
- [ ] All secrets stored in AWS Secrets Manager under prefix `workos-conduit/`
- [ ] S3 bucket created — versioning enabled, **fully private** (no public access)
- [ ] IAM task role created with `infra/aws/iam-task-role-policy.json` attached
- [ ] ECS cluster + service exist; task definition registered
- [ ] `python scripts/bootstrap.py --dry-run` output reviewed
- [ ] `python scripts/bootstrap.py` run live — existing users imported to NinjaOne
- [ ] Container deployed, `GET /health/ready` returns 200 for all components (adapter, cursor_backend, state_backend)
- [ ] Dashboard accessible at `http://your-ecs-host:8080/` (if `DASHBOARD_ENABLED=true`)
- [ ] First sync triggered from dashboard, run record visible at `GET /api/v1/runs/`
- [ ] CloudWatch log group `/ecs/workos-conduit` showing structured JSON events
