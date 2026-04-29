# API Reference

WorkOS Conduit exposes a JSON REST API and an HTML dashboard. All API responses use `Content-Type: application/json`. The dashboard returns `Content-Type: text/html`.

---

## Authentication

Only the `POST /api/v1/sync/trigger` endpoint requires authentication. It uses a static API key passed as an HTTP header.

| Header | Value |
|---|---|
| `X-API-Key` | Must match the `API_SECRET_KEY` environment variable |

All other endpoints are unauthenticated. In production, restrict access to the trigger endpoint via network policy (security group, ALB listener rule, or IP allowlist) in addition to the API key.

**401 response** (missing or wrong key):
```json
{"detail": "Invalid or missing X-API-Key"}
```

---

## Endpoints

### `GET /health/`

**Liveness probe.** Always returns 200 regardless of downstream connectivity. Used by ECS container health checks and load-balancer target group health checks.

**Auth**: None

**Response `200 OK`**:
```json
{"status": "ok"}
```

**curl**:
```bash
curl -s http://localhost:8080/health/
```

---

### `GET /health/ready`

**Readiness probe.** Calls `health_check()` on the adapter, cursor backend, and state backend. Returns 200 only if all three pass. Returns 503 if any component is unavailable.

**Auth**: None

**Response `200 OK`** (all healthy):
```json
{
  "status": "ready",
  "adapter": "ninjaone",
  "components": {
    "adapter": true,
    "cursor_backend": true,
    "state_backend": true
  }
}
```

**Response `503 Service Unavailable`** (one or more unhealthy):
```json
{
  "status": "unavailable",
  "adapter": "ninjaone",
  "components": {
    "adapter": false,
    "cursor_backend": true,
    "state_backend": true
  }
}
```

| Field | Type | Description |
|---|---|---|
| `status` | `string` | `"ready"` or `"unavailable"` |
| `adapter` | `string` | Adapter key in use (e.g. `ninjaone`) |
| `components.adapter` | `boolean` | Whether the target adapter is reachable (NinjaOne token endpoint) |
| `components.cursor_backend` | `boolean` | Whether SSM Parameter Store is accessible |
| `components.state_backend` | `boolean` | Whether the S3 state bucket is accessible |

**curl**:
```bash
curl -s http://localhost:8080/health/ready | jq
```

---

### `POST /api/v1/sync/trigger`

**Triggers a full sync cycle synchronously.** Fetches all WorkOS events since the last cursor position, processes each event in order, and returns the completed run record summary. The cycle completes before the HTTP response is sent — typical latency is 1–10 seconds depending on event volume and NinjaOne API response time.

**Auth**: `X-API-Key` header required

**Request body** (`application/json`, all fields optional):

| Field | Type | Default | Description |
|---|---|---|---|
| `trigger_source` | `string` | `"api"` | Label recorded in the run record. Use `"api"` for direct calls, `"scheduler"` for EventBridge Scheduler, `"dashboard"` for the UI button. |

Sending an empty body `{}` or no body is valid — `trigger_source` defaults to `"api"`.

**Response `200 OK`**:

| Field | Type | Description |
|---|---|---|
| `run_id` | `string` | UUID v4 uniquely identifying this run |
| `status` | `string` | Final run status: `success`, `partial_failure`, `error`, `no_events` |
| `events_processed` | `integer` | Number of non-skipped events processed |
| `duration_seconds` | `float` | Wall-clock time for the full sync cycle |
| `adapter` | `string` | Adapter key used (e.g. `ninjaone`) |
| `message` | `string` | Human-readable summary: `"Sync completed with status: success"` |

```json
{
  "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "success",
  "events_processed": 3,
  "duration_seconds": 1.24,
  "adapter": "ninjaone",
  "message": "Sync completed with status: success"
}
```

**Error responses**:

| Status | Condition | Body |
|---|---|---|
| `401 Unauthorized` | Missing or wrong `X-API-Key` | `{"detail": "Invalid or missing X-API-Key"}` |
| `422 Unprocessable Entity` | Malformed JSON body | FastAPI validation error object |
| `500 Internal Server Error` | Unhandled exception in the sync engine | `{"detail": "Internal Server Error"}` |

**curl**:
```bash
# Minimal (no body)
curl -s -X POST http://localhost:8080/api/v1/sync/trigger \
  -H "X-API-Key: local-dev-key" \
  -H "Content-Type: application/json" \
  -d '{}' | jq

# With explicit trigger source
curl -s -X POST http://localhost:8080/api/v1/sync/trigger \
  -H "X-API-Key: local-dev-key" \
  -H "Content-Type: application/json" \
  -d '{"trigger_source": "api"}' | jq
```

---

### `GET /api/v1/sync/status`

**Returns the most recent run summary.** Retrieves the single most recent `RunRecord` from the state backend and returns a compact summary. Returns `{"status": "no_runs"}` if no runs have been recorded yet.

**Auth**: None

**Response `200 OK`** (at least one run exists):

| Field | Type | Description |
|---|---|---|
| `status` | `string` | Status of the most recent run: `success`, `partial_failure`, `error`, `no_events` |
| `last_run.run_id` | `string` | UUID of the most recent run |
| `last_run.started_at` | `string` | ISO 8601 UTC timestamp |
| `last_run.duration_seconds` | `float` | Wall-clock time in seconds |
| `last_run.events_processed` | `integer` | Non-skipped events in that run |

```json
{
  "status": "success",
  "last_run": {
    "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "started_at": "2024-04-01T12:00:01.234000+00:00",
    "duration_seconds": 1.24,
    "events_processed": 3
  }
}
```

**Response `200 OK`** (no runs yet):
```json
{"status": "no_runs", "last_run": null}
```

**curl**:
```bash
curl -s http://localhost:8080/api/v1/sync/status | jq
```

---

### `GET /api/v1/runs/`

**Lists recent run records.** Returns the `limit` most recent runs in descending order by `started_at` (newest first). Each item is a full `RunRecord` including all handler results and errors.

**Auth**: None

**Query parameters**:

| Parameter | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `limit` | `integer` | `50` | 1 – 200 | Maximum number of runs to return |

**Response `200 OK`**: Array of `RunRecord` objects (see [RunRecord schema](#runrecord-schema) below).

```json
[
  {
    "run_id": "a1b2c3d4-...",
    "adapter": "ninjaone",
    "started_at": "2024-04-01T12:00:01.234000+00:00",
    "finished_at": "2024-04-01T12:00:02.458000+00:00",
    "duration_seconds": 1.24,
    "status": "success",
    "trigger_source": "scheduler",
    "events_fetched": 5,
    "events_processed": 3,
    "cursor_before": "evt_prev_001",
    "cursor_after": "evt_grp_005",
    "results": [...],
    "errors": []
  }
]
```

**curl**:
```bash
# Most recent 5 runs
curl -s "http://localhost:8080/api/v1/runs/?limit=5" | jq

# Full default (50 runs)
curl -s http://localhost:8080/api/v1/runs/ | jq 'length'
```

---

### `GET /api/v1/runs/{run_id}`

**Returns a single run record by ID.** Returns the full `RunRecord` including all per-event handler results and any structured errors.

**Auth**: None

**Path parameters**:

| Parameter | Type | Description |
|---|---|---|
| `run_id` | `string` | UUID v4 run identifier (from trigger response or list runs) |

**Response `200 OK`**: Single `RunRecord` object (see [RunRecord schema](#runrecord-schema) below).

**Response `404 Not Found`**:
```json
{"detail": "Run 'abc123' not found"}
```

**curl**:
```bash
RUN_ID="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
curl -s "http://localhost:8080/api/v1/runs/${RUN_ID}" | jq

# Print just the action counts
curl -s "http://localhost:8080/api/v1/runs/${RUN_ID}" | jq '{status: .status, counts: [.results[].action] | group_by(.) | map({(.[0]): length}) | add}'

# Show only errored results
curl -s "http://localhost:8080/api/v1/runs/${RUN_ID}" | jq '.results[] | select(.action == "error")'

# Show only skipped results
curl -s "http://localhost:8080/api/v1/runs/${RUN_ID}" | jq '.results[] | select(.action == "skipped")'
```

---

### `GET /`

**HTML dashboard.** Returns the Jinja2-rendered run history dashboard. Returns 404 if `DASHBOARD_ENABLED=false`.

**Auth**: None

**Response `200 OK`**: HTML page showing:
- System health indicator (`healthy`, `degraded`, `down`, `unknown`)
- Last run status and timestamp
- Events processed in the last 24 hours
- Run history table (most recent `DASHBOARD_RUN_HISTORY_LIMIT` runs)
- Action breakdown chart
- "Trigger Sync Now" button (prompts for `API_SECRET_KEY` via JavaScript)

**Response `404 Not Found`** (when `DASHBOARD_ENABLED=false`):
```json
{"detail": "Dashboard disabled"}
```

**Auto-refresh**: When `DASHBOARD_AUTO_REFRESH_SECONDS > 0`, the page includes a `<meta http-equiv="refresh">` tag. Set to `0` to disable.

---

### `GET /runs/{run_id}` (dashboard)

**HTML run detail page.** Returns a detailed view of a single run including the per-event results table and error tracebacks. Returns 404 if the run ID does not exist or if `DASHBOARD_ENABLED=false`.

**Auth**: None

**Response `200 OK`**: HTML page showing:
- Run metadata (ID, status, duration, trigger source, cursor progression)
- Per-event results table (action, email, event type, role, error message)
- Structured error details with tracebacks (if any errors)

**Response `404 Not Found`**:
```json
{"detail": "Run 'abc123' not found"}
```
or
```json
{"detail": "Dashboard disabled"}
```

---

## RunRecord Schema

Full schema for `RunRecord` objects returned by the runs API.

| Field | Type | Description |
|---|---|---|
| `run_id` | `string` | UUID v4 unique per cycle |
| `adapter` | `string` | Adapter key used (e.g. `"ninjaone"`) |
| `started_at` | `string` (ISO 8601 UTC) | When the sync cycle began |
| `finished_at` | `string` (ISO 8601 UTC) | When the sync cycle completed |
| `duration_seconds` | `float` | Wall-clock time for the full cycle |
| `status` | `string` | See [RunStatus values](#runstatus-values) |
| `trigger_source` | `string` | `"api"`, `"dashboard"`, or `"scheduler"` |
| `events_fetched` | `integer` | Total events returned by WorkOS (includes skipped) |
| `events_processed` | `integer` | Events with a non-SKIPPED outcome |
| `cursor_before` | `string \| null` | Cursor position at cycle start; `null` on first run |
| `cursor_after` | `string \| null` | Cursor position after successful processing; `null` if no events succeeded |
| `results` | `array[HandlerResult]` | One entry per event fetched |
| `errors` | `array[RunError]` | Structured errors for events that raised exceptions |

### HandlerResult Schema

| Field | Type | Description |
|---|---|---|
| `event_id` | `string` | WorkOS event ID (`evt_...`) |
| `event_type` | `string` | WorkOS event type (e.g. `dsync.user.created`) |
| `action` | `string` | Outcome — see [SyncAction values](#syncaction-values) |
| `target_adapter` | `string` | Adapter key (e.g. `"ninjaone"`) |
| `email` | `string \| null` | User email address |
| `target_user_id` | `string \| null` | Target system user ID if known |
| `changed_fields` | `array[string] \| null` | Fields that changed on update (e.g. `["first_name"]`) |
| `role` | `string \| null` | NinjaOne role assigned (for `role_assigned` action) |
| `error_message` | `string \| null` | Error description (for `error` action) |
| `duration_ms` | `integer` | Time to process this event in milliseconds |

### RunError Schema

| Field | Type | Description |
|---|---|---|
| `event_id` | `string` | WorkOS event ID that caused the error |
| `event_type` | `string` | WorkOS event type |
| `error_message` | `string` | Exception message |
| `traceback` | `string \| null` | Full Python traceback (when available) |

---

## SyncAction Values

| Value | Meaning |
|---|---|
| `created` | New user provisioned in the target system |
| `updated` | Existing user record updated |
| `deactivated` | User soft-disabled in the target system |
| `skipped` | Already exists / group not in allow-list or role map |
| `no_change` | Update requested but no diff detected — no API call made |
| `role_assigned` | Group membership event processed; role applied |
| `not_found_skipped` | User not found in target; event skipped rather than errored |
| `already_inactive` | Deactivation requested but user already inactive |
| `error` | Handler raised an exception; see `error_message` and `errors` array |

---

## RunStatus Values

| Value | Meaning |
|---|---|
| `success` | All fetched events processed without errors |
| `partial_failure` | At least one event errored; cycle continued (`SYNC_STOP_ON_ERROR=false`) |
| `error` | At least one event errored; cycle stopped (`SYNC_STOP_ON_ERROR=true` default) |
| `no_events` | WorkOS returned zero events since last cursor position |

---

## Complete Example: Trigger and Inspect

```bash
# 1. Trigger a sync
RESPONSE=$(curl -s -X POST http://localhost:8080/api/v1/sync/trigger \
  -H "X-API-Key: local-dev-key" \
  -H "Content-Type: application/json" \
  -d '{"trigger_source": "api"}')
echo $RESPONSE | jq .

# 2. Extract the run ID
RUN_ID=$(echo $RESPONSE | jq -r .run_id)

# 3. Fetch full run detail
curl -s "http://localhost:8080/api/v1/runs/${RUN_ID}" | jq .

# 4. Count actions
curl -s "http://localhost:8080/api/v1/runs/${RUN_ID}" \
  | jq '[.results[].action] | group_by(.) | map({key: .[0], value: length}) | from_entries'

# 5. Check for errors
curl -s "http://localhost:8080/api/v1/runs/${RUN_ID}" \
  | jq '.errors[] | {event_id, error_message}'
```
