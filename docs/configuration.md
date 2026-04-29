# Configuration Reference

All configuration is provided via environment variables. The application reads them at startup via `pydantic-settings` from the process environment and (optionally) a `.env` file at the repo root.

Variable names are **case-insensitive** — `WORKOS_API_KEY`, `workos_api_key`, and `Workos_Api_Key` are all equivalent.

---

## Secrets vs Plain Config

These variables contain credentials and **must** be stored in AWS Secrets Manager (not as plain ECS environment variables) when deployed to production:

| Variable | Reason |
|---|---|
| `WORKOS_API_KEY` | WorkOS API credential |
| `NINJAONE_CLIENT_ID` | NinjaOne OAuth client ID |
| `NINJAONE_CLIENT_SECRET` | NinjaOne OAuth client secret |
| `API_SECRET_KEY` | Protects the `/api/v1/sync/trigger` endpoint |

All other variables are safe as plain ECS environment variables or SSM parameters.

---

## WorkOS

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `WORKOS_API_KEY` | `str` | — | **Yes** | WorkOS API key (`sk_live_...` or `sk_test_...`) |
| `WORKOS_DIRECTORY_ID` | `str` | — | **Yes** | WorkOS Directory Sync directory ID (`directory_...`) |
| `WORKOS_EVENT_TYPES` | `list[str]` | All 5 dsync types | No | Comma-separated event types to subscribe to. Default: `dsync.user.created,dsync.user.updated,dsync.user.deleted,dsync.group.user_added,dsync.group.user_removed` |
| `WORKOS_EVENTS_PAGE_SIZE` | `int` | `100` | No | Maximum events per API call. WorkOS maximum is 100. |

**Note**: `WORKOS_EVENT_TYPES` accepts a JSON array string or a comma-separated list depending on the pydantic-settings list coercion. Use JSON format in `.env`: `WORKOS_EVENT_TYPES=["dsync.user.created","dsync.user.updated"]`.

---

## Adapter Selection

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `SYNC_TARGET_ADAPTER` | `str` | `ninjaone` | No | Registered adapter key. Currently `ninjaone` is the only built-in option. |
| `SYNC_STOP_ON_ERROR` | `bool` | `true` | No | When `true`, stop processing events as soon as any event errors and retry the same event on the next cycle. When `false`, log the error and continue — the failing event is eventually skipped permanently once the cursor advances past it. See [architecture.md](architecture.md) for the full cursor semantics. |

---

## Group Allow-List

Controls which WorkOS directory groups are processed. An empty list (the default) allows all groups through — no behaviour change from before this feature was added.

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `SYNC_ALLOWED_GROUPS` | `str` (JSON array) | `[]` | No | JSON array of exact WorkOS group names to process. Groups not in this list return `SyncAction.SKIPPED` before reaching the adapter. Example: `'["IT Admins","Support Team"]'` |
| `SYNC_ALLOWED_GROUPS_SOURCE` | `str` | `env` | No | Where to load the allow-list from. `env` reads `SYNC_ALLOWED_GROUPS`; `ssm` reads from SSM Parameter Store. |
| `SYNC_ALLOWED_GROUPS_SSM_PARAM` | `str` | `/workos-conduit/allowed-groups` | When source=ssm | SSM parameter path containing the JSON array. Required when `SYNC_ALLOWED_GROUPS_SOURCE=ssm`. |

**Interaction**: `SYNC_ALLOWED_GROUPS_SOURCE=ssm` requires `SYNC_ALLOWED_GROUPS_SSM_PARAM` to be non-empty. The validator raises at startup if it is empty.

**Updating without redeploy**: When `SYNC_ALLOWED_GROUPS_SOURCE=ssm`, you can update the allowed groups by writing a new JSON array to the SSM parameter. The new value is read on the next `run_cycle()` call (no restart required) because `load_allowed_groups()` is called fresh each cycle.

---

## NinjaOne

Required when `SYNC_TARGET_ADAPTER=ninjaone`.

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `NINJAONE_BASE_URL` | `str` | `https://app.ninjarmm.com` | No | NinjaOne API base URL. Override for EU or other regions. |
| `NINJAONE_CLIENT_ID` | `str` | `""` | **Yes** (when adapter=ninjaone) | OAuth 2.0 client ID from NinjaOne API settings |
| `NINJAONE_CLIENT_SECRET` | `str` | `""` | **Yes** (when adapter=ninjaone) | OAuth 2.0 client secret |
| `NINJAONE_ORG_ID` | `str` | `""` | No | NinjaOne organisation ID. Passed as `organizationId` when creating technicians. |
| `NINJAONE_GROUP_ROLE_MAP` | `str` (JSON object) | `{}` | No | JSON object mapping WorkOS group names to NinjaOne role names. Example: `'{"IT Admins": "administrator", "Support": "technician"}'`. Empty object means all group events are SKIPPED at the adapter level. |
| `NINJAONE_GROUP_ROLE_MAP_SOURCE` | `str` | `env` | No | Where to load the role map from. `env` reads `NINJAONE_GROUP_ROLE_MAP`; `ssm` reads from SSM Parameter Store. |
| `NINJAONE_GROUP_ROLE_MAP_SSM_PARAM` | `str` | `/workos-conduit/ninjaone/group-role-map` | When source=ssm | SSM parameter path containing the JSON object. |

**Interaction**: `NINJAONE_GROUP_ROLE_MAP_SOURCE=ssm` requires `NINJAONE_GROUP_ROLE_MAP_SSM_PARAM` to be non-empty. Startup validation raises if it is empty.

**Role names**: NinjaOne role names must match exactly what NinjaOne expects in the `role` field of the technician update API. Common values: `administrator`, `technician`, `custom_role_name`. Check your NinjaOne tenant for valid role names.

**Group name matching**: Both `SYNC_ALLOWED_GROUPS` and `NINJAONE_GROUP_ROLE_MAP` use **exact, case-sensitive** string matching against the WorkOS group name. `"IT Admins"` and `"it admins"` are different groups.

---

## HTTP Tuning

Controls outbound HTTP calls to the NinjaOne API.

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `HTTP_TIMEOUT_SECONDS` | `int` | `30` | No | Request timeout in seconds for all outbound HTTP calls |
| `HTTP_RETRY_MAX_ATTEMPTS` | `int` | `3` | No | Maximum number of retry attempts for transient failures (5xx, 429) |
| `HTTP_RETRY_BACKOFF_BASE_SECONDS` | `float` | `1.0` | No | Base delay in seconds for exponential backoff. Attempt N waits `base * 2^(N-1)` seconds. With default 1.0: 1s, 2s, 4s. |

**429 handling**: On a NinjaOne 429 response, the client reads the `Retry-After` header and sleeps for that duration before retrying (bypassing the exponential backoff calculation).

---

## Backends

### Backend Selection

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `CURSOR_BACKEND` | `str` | `aws` | No | Backend for cursor storage. `aws` (SSM Parameter Store) or `local` (in-memory, resets on restart). |
| `STATE_BACKEND` | `str` | `aws` | No | Backend for run record storage. `aws` (S3) or `local` (filesystem under `LOCAL_STATE_DIR`). |
| `LOCAL_STATE_DIR` | `str` | `.local-state` | No | Root directory for the `local` state backend. Run records are written to `{dir}/runs/{run_id}.json`. Not used when `STATE_BACKEND=aws`. |

**`local` backend**: intended for local development only — no AWS credentials required. The cursor lives in memory and resets on every server restart. Run records are persisted to the local filesystem and are gitignored.

**`aws` backend**: required for production. Uses SSM Parameter Store for the cursor and S3 for run records.

### AWS

Required when `CURSOR_BACKEND=aws` (default) or `STATE_BACKEND=aws` (default).

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `AWS_REGION` | `str` | `us-east-1` | No | AWS region for all service calls (SSM, S3) |
| `SSM_CURSOR_PARAM` | `str` | `/workos-conduit/cursor` | No | SSM Parameter Store path for the cursor value |
| `S3_STATE_BUCKET` | `str` | `""` | **Yes** (when state_backend=aws) | S3 bucket name for storing run records |
| `S3_STATE_PREFIX` | `str` | `runs/` | No | Key prefix inside the bucket. All run records are stored under `{prefix}YYYY/MM/DD/{run_id}.json` |

**IAM requirements**: The ECS task role needs:
- `ssm:GetParameter` and `ssm:PutParameter` on `arn:aws:ssm:*:*:parameter/workos-conduit/*`
- `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` on the state bucket

See `infra/aws/iam-task-role-policy.json` for the reference policy.

### SSM Parameter Layout

```
/workos-conduit/
├── cursor                          ← last processed WorkOS event ID
├── allowed-groups                  ← JSON array (when SYNC_ALLOWED_GROUPS_SOURCE=ssm)
└── ninjaone/
    └── group-role-map              ← JSON object (when NINJAONE_GROUP_ROLE_MAP_SOURCE=ssm)
```

---

## Server

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `SERVER_HOST` | `str` | `0.0.0.0` | No | Host to bind the uvicorn server to |
| `SERVER_PORT` | `int` | `8080` | No | Port to listen on |
| `API_SECRET_KEY` | `str` | `change-me-in-production` | **Yes** (in production) | Secret token for `X-API-Key` header authentication on `POST /api/v1/sync/trigger`. The default value is intentionally insecure — always override in production. |

---

## Dashboard

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `DASHBOARD_ENABLED` | `bool` | `true` | No | Enable or disable the Jinja2 HTML dashboard at `GET /`. When `false`, the route returns 404. |
| `DASHBOARD_RUN_HISTORY_LIMIT` | `int` | `50` | No | Maximum number of run records shown in the dashboard run history table |
| `DASHBOARD_AUTO_REFRESH_SECONDS` | `int` | `60` | No | Interval in seconds for the dashboard `<meta http-equiv="refresh">` tag. Set to `0` to disable auto-refresh. |

---

## Logging

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `LOG_LEVEL` | `str` | `INFO` | No | Minimum log level. One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `LOG_OUTPUT` | `str` | `stdout` | No | Where to write logs. `stdout` (default, recommended for containers), `file`, or `both` |
| `LOG_FORMAT` | `str` | `json` | No | Log format. `json` produces one JSON object per line (for CloudWatch, Datadog, Splunk). `console` produces human-readable colourised output (for local dev). |
| `LOG_FILE_PATH` | `str` | `/var/log/workos-conduit/app.log` | When output=file | Absolute path for the rotating log file. The file rotates at 10 MB, keeping 5 backups. Falls back to stdout if the path is not writable. |

**Recommended production settings**: `LOG_OUTPUT=stdout LOG_FORMAT=json`. The ECS `awslogs` driver captures stdout and sends it to CloudWatch Logs automatically.

**Recommended local dev settings**: `LOG_OUTPUT=stdout LOG_FORMAT=console LOG_LEVEL=DEBUG`.

### JSON log fields

Every structured log line includes:
- `timestamp` — ISO 8601 UTC
- `level` — log level string
- `logger` — module name (e.g. `src.core.sync_engine`)
- `event` — event name (e.g. `sync_triggered`, `event_processed`, `cycle_complete`)
- All bound context fields (e.g. `run_id`, `event_id`, `adapter`, `email`, `action`)

Example:
```json
{
  "timestamp": "2024-04-01T12:00:01.234Z",
  "level": "info",
  "logger": "src.core.sync_engine",
  "event": "cycle_complete",
  "run_id": "abc123",
  "status": "success",
  "events_processed": 5,
  "duration_seconds": 1.24
}
```

---

## Validation Rules

The `Settings.validate_config` model validator enforces these rules at startup. Any violation raises a `ValueError` and prevents the application from starting.

| Condition | Error |
|---|---|
| `SYNC_TARGET_ADAPTER=ninjaone` and `NINJAONE_CLIENT_ID` is empty | `ninjaone_client_id and ninjaone_client_secret required` |
| `STATE_BACKEND=aws` and `S3_STATE_BUCKET` is empty | `s3_state_bucket required when state_backend=aws` |
| `CURSOR_BACKEND=local` or `STATE_BACKEND=local` | No validation error — `local` backends have no required fields |
| `NINJAONE_GROUP_ROLE_MAP_SOURCE=ssm` and `NINJAONE_GROUP_ROLE_MAP_SSM_PARAM` is empty | `ninjaone_group_role_map_ssm_param required` |
| `SYNC_ALLOWED_GROUPS_SOURCE=ssm` and `SYNC_ALLOWED_GROUPS_SSM_PARAM` is empty | `sync_allowed_groups_ssm_param required` |
