# Architecture

WorkOS Conduit is a single-purpose provisioning bridge. It consumes WorkOS Directory Sync events produced when Google Workspace users and groups change, then applies those changes to a target system (NinjaOne by default). Cursor state is stored in SSM (or local file/memory in dev), and run records are append-only in S3 (or local files in dev); no database is required. The application runs as a single-process FastAPI service on AWS ECS Fargate.

---

## Data Flow

```
Google Workspace
      │  SCIM / sync
      ▼
  WorkOS Directory Sync
      │  Event stream (dsync.user.*, dsync.group.*)
      ▼
  POST /api/v1/sync/trigger          ← EventBridge Scheduler (every 5 min)
      │                              ← Dashboard "Trigger Sync Now" button
      │                              ← Direct API call (curl, CI)
      ▼
  SyncEngine.run_cycle()
      │
      ├─ WorkOSEventsClient.list_events(after=cursor)
      │        Returns paginated events since last cursor position
      │
      └─ For each event (sequential order preserved):
             │
             ├─ SyncEngine._process_event()
             │       │
             │       ├─ [dsync.user.created / dsync.user.updated only]
             │       │       Group membership check via WorkOS API
             │       │       Watched groups derived from adapter.watched_groups()
             │       │       (role map keys from NINJAONE_GROUP_ROLE_MAP)
             │       │       Skip if user not in any watched group
             │       │       Skip if NINJAONE_GROUP_ADMINS set and user in admin group
             │       │       (delete events bypass this check)
             │       │
             │       └─ EventRouter.route(event, adapter)
             │               │
             │               └─ GroupMembershipHandler / UserCreatedHandler / ...
             │                       │
             │                       └─ BaseTargetAdapter.provision_*(user/group)
             │                               │
             │                               └─ NinjaOne REST API
             │
             ├─ On success: cursor_backend.save(event_id) → advance cursor
             └─ On error: record error; break (stop_on_error=true) or continue

      ▼
  SyncRunContext.finalize() → RunRecord
      │
      └─ state_backend.write_run(record) → S3 (append-only)
```

---

## Sync Cycle: Step-by-Step

The entire cycle is synchronous and single-threaded, preserving WorkOS event ordering.

**1. Start the Unit of Work**

`SyncRunContext.start()` (`src/core/sync_run.py`) generates a UUID v4 `run_id`, records `started_at`, and reads the current cursor position (`cursor_before`). All mutable state for the run lives here — results, errors, cursor progression.

**2. Fetch events**

`WorkOSEventsClient.list_events(after=cursor_before)` (`src/workos/client.py`) calls the WorkOS SDK with the configured event types and page size. Returns `(events_list, last_event_id)`. The `after` parameter tells WorkOS to return only events newer than the last processed event ID.

**3. Process each event**

For every event in order:

- `EventRouter.route(event, adapter)` (`src/core/event_router.py`) finds the first handler where `can_handle(event_type)` is true. If no handler matches, it returns `SyncAction.SKIPPED`. If the handler raises an exception, the router catches it and returns `SyncAction.ERROR` — exceptions never propagate out of the router.

- The handler converts the raw WorkOS event dict into a typed `ProvisioningUser` or `ProvisioningGroup` object, then calls the adapter method.

- The adapter returns a `HandlerResult` with the outcome action (`CREATED`, `UPDATED`, `SKIPPED`, etc.).

**4. Cursor advance**

After each successful event, `cursor_backend.save(event_id)` writes the event ID to SSM Parameter Store and `ctx.advance_cursor(event_id)` records it in the run context. The cursor only advances on success — a failing event retains the cursor at its position so the next cycle retries it.

**5. Error handling**

When a result has `action=ERROR`:
- `SYNC_STOP_ON_ERROR=true` (default): record the error and break the loop. The run status will be `ERROR`. The cursor has not advanced past the failing event — the next cycle retries it from the same position.
- `SYNC_STOP_ON_ERROR=false`: record the error and continue to the next event. The cursor does NOT advance past the failing event. Subsequent successful events advance the cursor past it permanently, so the failing event is effectively skipped forever.

**6. Finalize and persist**

`SyncRunContext.finalize()` computes the final `RunStatus` and returns an immutable `RunRecord`. `state_backend.write_run(record)` serialises it to JSON and appends it to S3 at `s3://bucket/runs/YYYY/MM/DD/{run_id}.json`. The S3 key is never overwritten.

---

## Cursor Semantics

The cursor is a single string value — the WorkOS event ID of the last successfully processed event. It is stored in AWS SSM Parameter Store at the path configured by `SSM_CURSOR_PARAM` (default `/workos-conduit/cursor`).

| Scenario | Cursor behaviour |
|---|---|
| First run (no cursor) | Fetches from beginning of event stream |
| Successful event | Cursor advances to that event ID |
| Failed event (`stop_on_error=true`) | Cursor stays at previous position; cycle stops; next cycle retries same event |
| Failed event (`stop_on_error=false`) | Cursor stays at previous position; cycle continues; if later events succeed cursor advances past the failed one |
| Crash mid-cycle | Cursor holds the last successfully saved position; next cycle resumes from there |

The `stop_on_error=false` mode is suitable when you want non-blocking operation and accept that a repeatedly-failing event will eventually be skipped permanently once the cursor advances past it.

---

## RunStatus State Machine

`SyncRunContext.finalize()` computes status using this ordered decision tree:

```
events_fetched == 0   →  NO_EVENTS
_terminated_early     →  ERROR         (stop_on_error=true hit a failure)
any ERROR in results  →  PARTIAL_FAILURE (stop_on_error=false, some failed)
else                  →  SUCCESS
```

`PARTIAL_FAILURE` means at least one event errored but the cycle completed (because `SYNC_STOP_ON_ERROR=false`). The cursor has advanced past all successful events; failing events were not advanced past.

---

## Unit of Work: SyncRunContext

`SyncRunContext` (`src/core/sync_run.py`) owns all mutable state for one `run_cycle()` execution. `SyncEngine` is a thin orchestrator that delegates all state accumulation to it.

| Method | What it does |
|---|---|
| `SyncRunContext.start(adapter_key, trigger_source, cursor_before)` | Generates run_id (UUID4), records started_at, stores cursor_before |
| `record_fetched(count)` | Sets total events fetched |
| `record_result(result)` | Appends a HandlerResult to the results list |
| `record_error(event, exc, terminated)` | Appends a RunError; sets `_terminated_early=True` only when `terminated=True` |
| `advance_cursor(event_id)` | Updates `_cursor_after` (only called after successful save) |
| `finalize()` | Computes RunStatus, calculates duration, returns immutable RunRecord |

---

## Adapter Pattern

### BaseTargetAdapter ABC

`src/adapters/base.py` defines the contract all provisioning targets must satisfy:

```
adapter_key: str                         # unique identifier e.g. "ninjaone"
provision_user_created(user) → HandlerResult
provision_user_updated(user) → HandlerResult
provision_user_deactivated(user) → HandlerResult
provision_group_membership(group) → HandlerResult
health_check() → bool
```

**Idempotency contracts** — every method must be safe to call multiple times:

| Method | If already in target state |
|---|---|
| `provision_user_created` | Returns `SKIPPED` (user already exists) |
| `provision_user_updated` | Returns `NO_CHANGE` (no diff detected) |
| `provision_user_deactivated` | Returns `ALREADY_INACTIVE` (already disabled) |
| `provision_group_membership` | Returns `NOT_FOUND_SKIPPED` if user not in target; `SKIPPED` if group not in role map |

### Registry / Factory

`src/adapters/registry.py` maps adapter keys to factory callables:

```python
_REGISTRY: dict[str, Callable[[Settings], BaseTargetAdapter]]
register_adapter(key, factory)   # called at module import time
get_adapter(key, settings)       # called by deps.get_adapter_dep()
```

NinjaOne registers itself when `src/adapters/ninjaone/__init__.py` is imported. Adding a new adapter requires only creating the module and calling `register_adapter` — no changes to core code.

### NinjaOneAdapter

`src/adapters/ninjaone/adapter.py` — full implementation:

- **Client** (`ninjaone/client.py`): HTTP client with OAuth 2.0 auth. One-time `authorization_code` flow generates a 30-day refresh token stored in SSM SecureString; runtime calls exchange it at `/oauth/token` (`grant_type=refresh_token`) to mint bearer access tokens cached in-process. Per-request retry: 429 → sleep Retry-After, 5xx → exponential backoff, 4xx → raise immediately. A 401 response triggers one access-token refresh-and-retry.
- **Mapper** (`ninjaone/mapper.py`): converts `ProvisioningUser` → NinjaOne end-user payload (`firstName`, `lastName`, `email`, `fullPortalAccess: false`, optional `organizationId`).
- **Role map** (`ninjaone/group_role_map.py`): loads `dict[group_name → OrgGroupMapping]` from env var or SSM. Each `OrgGroupMapping` carries `ninjaone_organization_id` (UUID string), `google_workspace_group_name`, and `ninjaone_role`. Only `END_USER` role is processed; other roles log a warning and return `SKIPPED`. On `user_added`, the adapter creates the user with the mapped org ID or patches it if the org changed.

---

## Backend Pattern

### CursorBackend ABC

`src/backends/base.py`:

```
get() → str | None      # None on first run
save(event_id: str)     # overwrites with new cursor
health_check() → bool
```

### StateBackend ABC

```
write_run(record) → str                     # returns storage key; append-only
get_run(run_id) → RunRecord | None
list_recent_runs(limit) → list[RunRecord]   # newest-first
health_check() → bool
```

### Registry

`src/backends/registry.py` maintains separate registries for cursor and state backends, following the same factory pattern as adapters.

### AWS Implementations

**SsmCursorBackend** (`src/backends/aws/cursor_ssm.py`):
- `get()`: `GetParameter` with `WithDecryption=False`; returns `None` on `ParameterNotFound`
- `save()`: `PutParameter` with `Overwrite=True`

**S3StateBackend** (`src/backends/aws/state_s3.py`):
- Key scheme: `{s3_state_prefix}{YYYY}/{MM}/{DD}/{run_id}.json`
  - Example: `runs/2024/04/01/abc123.json`
- `write_run()`: `PutObject` with `ContentType=application/json`; never overwrites because run IDs are UUID4
- `list_recent_runs()`: fetches all objects under the prefix, deserialises each, sorts by `started_at` descending, returns first `limit`
- Append-only: there is no delete or update operation in the codebase

### Local Implementations

**FileCursorBackend** (`src/backends/local/cursor_file.py`):
- Persists cursor to `{LOCAL_STATE_DIR}/cursor.txt`
- Survives server restarts — delete the file to reset the cursor
- Registered under key `"local"`

**MemoryCursorBackend** (`src/backends/local/cursor_memory.py`):
- In-process only; resets on restart
- Registered under key `"memory"` — intended for unit tests

**FileStateBackend** (`src/backends/local/state_file.py`):
- Writes one JSON file per run to `{LOCAL_STATE_DIR}/runs/`
- File naming: `YYYYMMDDHHMMSS_{run_id[:8]}.json` — timestamp prefix makes `ls` output human-readable and naturally sorted
- `list_recent_runs()`: sorts by filename descending, slices to `limit` before loading — avoids reading all files just to sort
- Registered under key `"local"`

---

## Handler Pattern

### BaseEventHandler ABC

`src/handlers/base.py`:

```
can_handle(event_type: str) → bool
handle(event: dict, adapter: BaseTargetAdapter) → HandlerResult
_workos_event_to_user(event_data: dict) → ProvisioningUser  # shared utility
```

`_workos_event_to_user` extracts: `email`, `first_name`, `last_name`, `is_active` (from `state=="active"`), `department`/`job_title` from `custom_attributes`, `external_id` from `id`.

### Handler Registry

`src/handlers/registry.py` registers handler classes and instantiates them on demand — the same factory pattern used by adapters and backends.

```python
register_handler(cls)   # called for each handler class in registry.py
get_handlers()          # returns [cls() for cls in _HANDLERS] — used by deps.get_event_router()
```

Adding a new event handler requires only creating the handler module and calling `register_handler` in `registry.py` — no changes to `deps.py` or any other core file.

### EventRouter

`src/core/event_router.py` receives a list of handlers at construction. `route(event, adapter)`:

1. Finds the first handler where `can_handle(event["event"])` is true
2. If none found → returns `HandlerResult(action=SKIPPED)`
3. Calls `handler.handle(event, adapter)` inside a try/except
4. On exception → returns `HandlerResult(action=ERROR, error_message=str(exc))` — the exception is logged but never re-raised

---

## Group Filtering and Role Mapping

Two independent filter layers apply before any NinjaOne API call is made:

**Layer 0 — User event group check** (in `SyncEngine._process_event`, `src/core/sync_engine.py`):

For `dsync.user.created` and `dsync.user.updated` events, the engine calls the WorkOS API to get the user's groups. The watched groups are derived from `adapter.watched_groups()`, which returns the role map keys from `NINJAONE_GROUP_ROLE_MAP`. If the user is not in any watched group, the event is skipped before being routed to any handler. Additionally, if `NINJAONE_GROUP_ADMINS` is set and the user belongs to that group, the event is also skipped — admin users are managed separately. Delete events (`dsync.user.deleted`) bypass both checks — deactivation always proceeds if the user exists.

A per-cycle group membership prefetch runs upfront (batch WorkOS queries before any NinjaOne calls) when `watched_groups` or `admin_group` is configured, covering all users seen in the cycle. A per-cycle group cache (`dict[user_id → list[group_names]]`) prevents duplicate WorkOS API calls within one cycle.

**Layer 1 — Org+role map** (in `NinjaOneAdapter`, `src/adapters/ninjaone/adapter.py`):

The adapter looks up the group in `NINJAONE_GROUP_ROLE_MAP` (which holds `OrgGroupMapping` objects). If the group has no entry, returns `SyncAction.SKIPPED`. If the mapped role is not `END_USER`, returns `SKIPPED` with a `WARNING` log. For `action=added`, the adapter also checks whether the user's `organizationId` matches the mapping — patching it if it changed. This is the final filter layer — there is no separate allow-list layer between the engine and the adapter for group events.

```
dsync.user.created / dsync.user.updated event
        │
        ▼
  SyncEngine._process_event()
        │
        ├─ NINJAONE_GROUP_ADMINS set and user in admin group?
        │       Yes → SKIPPED (admin users managed separately)
        │
        ├─ adapter.watched_groups() non-empty?
        │       Yes → user in any watched group? No → SKIPPED (engine level)
        │
        ▼
  UserCreatedHandler / UserUpdatedHandler → NinjaOneAdapter

dsync.group.user_added event
        │
        ▼
  GroupMembershipHandler.handle()
        │
        ▼
  NinjaOneAdapter.provision_group_membership()
        │
        ├─ Group in NINJAONE_GROUP_ROLE_MAP?
        │       No → SKIPPED (adapter level)
        │
        ├─ Mapped role == END_USER?
        │       No → SKIPPED + WARNING log (unsupported role)
        │
        ├─ User exists in NinjaOne?
        │       No → create end-user with mapped organizationId → CREATED
        │       Yes, org matches → SKIPPED
        │       Yes, org differs → PATCH organizationId → UPDATED
        │
        └─ action==removed → deactivate_end_user() → DEACTIVATED
```

Both maps can be loaded from an env var (default) or SSM Parameter Store without a redeploy. See [configuration.md](configuration.md) for the full JSON format and field descriptions.

---

## RunRecord Data Model

`RunRecord` (`src/core/models.py`) is an immutable Pydantic model written once to S3 per cycle.

| Field | Type | Description |
|---|---|---|
| `run_id` | `str` | UUID4, unique per cycle |
| `adapter` | `str` | Adapter key used (e.g. `ninjaone`) |
| `started_at` | `datetime` | UTC timestamp when cycle started |
| `finished_at` | `datetime` | UTC timestamp when cycle completed |
| `duration_seconds` | `float` | Wall-clock time for the full cycle |
| `status` | `RunStatus` | `success`, `partial_failure`, `error`, `no_events` |
| `trigger_source` | `str` | `api`, `dashboard`, or `scheduler` |
| `events_fetched` | `int` | Total events returned by WorkOS |
| `events_processed` | `int` | Non-SKIPPED results |
| `cursor_before` | `str \| None` | Cursor at start (None = first run) |
| `cursor_after` | `str \| None` | Cursor after successful processing |
| `results` | `list[HandlerResult]` | One per event |
| `errors` | `list[RunError]` | Structured errors with tracebacks |

The `counts` property aggregates `results` into `dict[SyncAction, int]` for a single run. The `aggregate_counts(runs)` classmethod aggregates across a list of runs — used by the dashboard.

### SyncAction values

| Value | Meaning |
|---|---|
| `created` | New user provisioned in target |
| `updated` | Existing user updated |
| `deactivated` | User soft-disabled in target |
| `skipped` | User already exists / group not in role map / user filtered by group check |
| `no_change` | Update requested but no diff detected |
| `role_assigned` | Reserved for future role-assignment flows (not currently emitted) |
| `not_found_skipped` | User not found in target; skip rather than error |
| `already_inactive` | Deactivation requested but user already inactive |
| `error` | Handler raised an exception |
