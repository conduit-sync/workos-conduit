# Configuration Reference

All configuration is provided via environment variables. The application reads them at startup via `pydantic-settings` from the process environment and (optionally) a `.env` file at the repo root.

Variable names are **case-insensitive** — `WORKOS_API_KEY`, `workos_api_key`, and `Workos_Api_Key` are all equivalent.

---

## Secrets vs Plain Config

These variables contain credentials and **must** be stored in AWS Secrets Manager (not as plain ECS environment variables) when deployed to production:

| Variable | Reason |
|---|---|
| `WORKOS_API_KEY` | WorkOS API credential |
| `NINJAONE_OAUTH_CLIENT_SECRET` | NinjaOne OAuth client secret |
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

## NinjaOne

Required when `SYNC_TARGET_ADAPTER=ninjaone`.

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `NINJAONE_BASE_URL` | `str` | `https://app.ninjarmm.com` | No | NinjaOne API base URL. Override for EU or other regions. |
| `NINJAONE_OAUTH_CLIENT_ID` | `str` | `""` | **Yes** (when adapter=ninjaone) | NinjaOne OAuth app client ID. |
| `NINJAONE_OAUTH_CLIENT_SECRET` | `str` | `""` | **Yes** (when adapter=ninjaone) | NinjaOne OAuth app client secret. |
| `NINJAONE_OAUTH_SCOPE` | `str` | `control offline_access monitoring management` | No | OAuth scopes sent in authorization and refresh-token flows. |
| `NINJAONE_OAUTH_AUTHORIZE_PATH` | `str` | `/oauth/authorize` | No | NinjaOne OAuth authorize endpoint path. |
| `NINJAONE_OAUTH_TOKEN_PATH` | `str` | `/oauth/token` | No | NinjaOne OAuth token endpoint path. |
| `NINJAONE_OAUTH_REDIRECT_PATH` | `str` | `/dashboard/oauth/ninjaone/callback` | No | Callback path mounted by this app. Usually keep default unless routes are proxied/rebased. |
| `NINJAONE_OAUTH_REFRESH_TOKEN_SSM_PARAM` | `str` | `/workos-conduit/ninjaone/oauth-refresh-token` | No | SSM SecureString path storing the refresh-token JSON blob. |
| `NINJAONE_OAUTH_REFRESH_TOKEN_LIFETIME_DAYS` | `int` | `30` | No | Used to compute estimated refresh-token expiration shown in dashboard. |
| `NINJAONE_GROUP_ROLE_MAP` | `str` (JSON object) | `{"organizations_groups_mapping": []}` | No | JSON object containing an `organizations_groups_mapping` array. Each entry maps a Google Workspace group to a NinjaOne organization and role. See format below. An empty array means all group events are SKIPPED at the adapter level. |
| `NINJAONE_GROUP_ROLE_MAP_SOURCE` | `str` | `env` | No | Where to load the role map from. `env` reads `NINJAONE_GROUP_ROLE_MAP`; `ssm` reads from SSM Parameter Store. |
| `NINJAONE_GROUP_ROLE_MAP_SSM_PARAM` | `str` | `/workos-conduit/ninjaone/group-role-map` | When source=ssm | SSM parameter path containing the JSON object. |
| `NINJAONE_GROUP_ADMINS` | `str` | `""` | No | WorkOS group name whose members are skipped for `dsync.user.created` and `dsync.user.updated` events. Delete events (`dsync.user.deleted`) still process normally. Example: `ninjaone-admins`. |

**JSON format for `NINJAONE_GROUP_ROLE_MAP`**:

```json
{
  "organizations_groups_mapping": [
    {
      "ninjaone_organization_name": "Stakes Manufacturing",
      "ninjaone_organization_id": "9e77507d-d092-4a37-bf99-c987fc27a327",
      "google_workspace_group_name": "ninjaone-users",
      "ninjaone_role": "END_USER"
    },
    {
      "ninjaone_organization_name": "Warehouse Operations",
      "ninjaone_organization_id": "34e9abb2-a0c3-423d-8858-bbc3bbd2048b",
      "google_workspace_group_name": "warehouse-operations-users",
      "ninjaone_role": "END_USER"
    }
  ]
}
```

Each entry fields:

| Field | Type | Description |
|---|---|---|
| `ninjaone_organization_name` | `str` | Human-readable label (for documentation only; not sent to the API) |
| `ninjaone_organization_id` | `str` | NinjaOne organization UUID. Passed as `organizationId` when creating an end-user. |
| `google_workspace_group_name` | `str` | Exact WorkOS group name to match (case-sensitive) |
| `ninjaone_role` | `str` | Must be `END_USER`. Other values log a warning and skip the event. |

**Org assignment behaviour**: When a `dsync.group.user_added` event arrives, the adapter looks up the group mapping, then:
- If the user does not exist in NinjaOne → creates them with the mapped `organizationId`
- If the user exists but belongs to a different organization → patches `organizationId` to the expected one (returns `UPDATED`)
- If the user exists with the correct organization → returns `SKIPPED`

**Interaction**: `NINJAONE_GROUP_ROLE_MAP_SOURCE=ssm` requires `NINJAONE_GROUP_ROLE_MAP_SSM_PARAM` to be non-empty. Startup validation raises if it is empty.

**Supported roles**: Only `END_USER` (case-insensitive) is supported at this time. If a group maps to any other role (e.g. `administrator`, `technician`), the event is skipped and a `WARNING` log line is emitted with `group_membership_skipped_unsupported_role`. Support for additional roles will be added in a future release.

**Authentication**: NinjaOne auth uses OAuth 2.0 with two grants. An operator manually generates a refresh token using the dashboard **Generate Refresh Token** button or `scripts/ninjaone_oauth_bootstrap.py`, and that token is stored in SSM SecureString (`NINJAONE_OAUTH_REFRESH_TOKEN_SSM_PARAM`). At runtime, the client exchanges that refresh token at `/oauth/token` (`grant_type=refresh_token`) to mint short-lived bearer access tokens, caches them in-process, and sends `Authorization: Bearer <token>` on API calls.

**Required callback registration**: Register this exact redirect URI in your NinjaOne OAuth app:

```
{DASHBOARD_PUBLIC_BASE_URL}{NINJAONE_OAUTH_REDIRECT_PATH}
```

Example: `https://conduit.example.com/dashboard/oauth/ninjaone/callback`.

**Callback implementation**: The app implements the callback route at `GET /dashboard/oauth/ninjaone/callback`, and the flow start endpoint at `POST /dashboard/oauth/ninjaone/start` (API key protected). `NINJAONE_OAUTH_REDIRECT_PATH` must match the registered callback path.

**Group name matching**: `NINJAONE_GROUP_ROLE_MAP` uses **exact, case-sensitive** string matching against the WorkOS group name. `"IT Admins"` and `"it admins"` are different groups.

**Implicit allow-list**: The groups listed in `NINJAONE_GROUP_ROLE_MAP` automatically define which users are processed on `dsync.user.created` and `dsync.user.updated` events. Users who do not belong to any mapped group are skipped at the engine level before handlers run. No separate allow-list configuration is needed.

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
| `CURSOR_BACKEND` | `str` | `aws` | No | Backend for cursor storage. `aws` (SSM Parameter Store), `local` (file-backed, survives restarts), or `memory` (in-process only, resets on restart — useful for tests). |
| `STATE_BACKEND` | `str` | `aws` | No | Backend for run record storage. `aws` (S3) or `local` (filesystem under `LOCAL_STATE_DIR`). |
| `LOCAL_STATE_DIR` | `str` | `.local-state` | No | Root directory for local backends. Cursor: `{dir}/cursor.txt`. Run records: `{dir}/runs/YYYYMMDDHHMMSS_{run_id[:8]}.json`. Not used when both backends are `aws`. |

**`local` backend**: intended for local development — no AWS credentials required. Cursor is persisted to `cursor.txt` and survives restarts (delete the file to reset). Run record filenames include a timestamp prefix (`YYYYMMDDHHMMSS`) so `ls` output is human-readable and naturally sorted. Both paths are gitignored.

**`memory` backend**: cursor only. State lives in-process and is lost on every restart. Use this in unit tests where you need isolation between test runs.

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
└── ninjaone/
    ├── group-role-map              ← JSON object (when NINJAONE_GROUP_ROLE_MAP_SOURCE=ssm)
    └── oauth-refresh-token         ← SecureString JSON blob for OAuth refresh token
```

---

## Server

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `SERVER_HOST` | `str` | `0.0.0.0` | No | Host to bind the uvicorn server to |
| `SERVER_PORT` | `int` | `8080` | No | Port to listen on |
| `API_SECRET_KEY` | `str` | `change-me-in-production` | **Yes** (in production) | Secret token for `X-API-Key` header authentication on `POST /api/v1/sync/trigger` and `POST /dashboard/oauth/ninjaone/start`. The default value is intentionally insecure — always override in production. |

---

## Dashboard

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `DASHBOARD_ENABLED` | `bool` | `true` | No | Enable or disable the Jinja2 HTML dashboard at `GET /`. When `false`, the route returns 404. |
| `DASHBOARD_RUN_HISTORY_LIMIT` | `int` | `50` | No | Maximum number of run records shown in the dashboard run history table |
| `DASHBOARD_AUTO_REFRESH_SECONDS` | `int` | `60` | No | Interval in seconds for the dashboard `<meta http-equiv="refresh">` tag. Set to `0` to disable auto-refresh. |
| `DASHBOARD_PUBLIC_BASE_URL` | `str` | `""` | Required for dashboard OAuth flow | Public app base URL used to construct the registered OAuth callback URI (`{base_url}/dashboard/oauth/ninjaone/callback`). |

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

Validation runs at startup. Any violation raises a `ValueError` and prevents the application from starting.

`Settings.validate_config` (config-level, checked on every startup):

| Condition | Error |
|---|---|
| `NINJAONE_GROUP_ROLE_MAP_SOURCE=ssm` and `NINJAONE_GROUP_ROLE_MAP_SSM_PARAM` is empty | `ninjaone_group_role_map_ssm_param required` |
| `WORKOS_EVENT_TYPES` is a JSON array string but is not valid JSON | `workos_event_types is not valid JSON` |

`NinjaOneAdapter.__init__` (adapter-level, checked when the adapter is first instantiated):

| Condition | Error |
|---|---|
| `NINJAONE_OAUTH_CLIENT_ID` is empty | `ninjaone_oauth_client_id is required when sync_target_adapter=ninjaone` |
| `NINJAONE_OAUTH_CLIENT_SECRET` is empty | `ninjaone_oauth_client_secret is required when sync_target_adapter=ninjaone` |

`S3StateBackend.__init__` (backend-level, checked when the backend is first instantiated):

| Condition | Error |
|---|---|
| `STATE_BACKEND=aws` and `S3_STATE_BUCKET` is empty | `s3_state_bucket is required when state_backend=aws` |
