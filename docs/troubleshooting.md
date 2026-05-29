# Troubleshooting

Each scenario follows the pattern: **Symptom → Likely cause → Diagnosis → Fix**.

---

## 1. Container fails to start / health check never passes

**Symptom**: ECS task exits immediately or stays in ACTIVATING. `GET /health/` returns connection refused.

**Likely cause**: Application crashed at startup due to a missing required environment variable or a validation failure in `Settings.validate_config`.

**Diagnosis**:

```bash
# Check ECS task stopped reason
aws ecs describe-tasks --cluster YOUR_CLUSTER --tasks TASK_ARN \
  | jq '.tasks[0].stoppedReason'

# Check CloudWatch Logs for startup errors
aws logs get-log-events \
  --log-group-name /ecs/workos-conduit \
  --log-stream-name STREAM_NAME \
  --limit 50 | jq '.events[].message'
```

Look for a `ValueError` from `validate_config`. Common messages:

| Error message | Missing variable |
|---|---|
| `ninjaone_oauth_client_id is required when sync_target_adapter=ninjaone` | `NINJAONE_OAUTH_CLIENT_ID` |
| `ninjaone_oauth_client_secret is required when sync_target_adapter=ninjaone` | `NINJAONE_OAUTH_CLIENT_SECRET` |
| `s3_state_bucket required when state_backend=aws` | `S3_STATE_BUCKET` |
| `ninjaone_group_role_map_ssm_param required` | `NINJAONE_GROUP_ROLE_MAP_SSM_PARAM` (when source=ssm) |

**Fix**: Set the missing variable in your ECS task definition or Secrets Manager and redeploy. For Secrets Manager variables (`WORKOS_API_KEY`, `NINJAONE_OAUTH_CLIENT_SECRET`, `API_SECRET_KEY`), ensure the ECS task role has `secretsmanager:GetSecretValue`.

---

## 2. NinjaOne refresh token expired / missing

**Symptom**: Sync attempts fail with `invalid_grant`, `NinjaOne refresh token is missing`, or dashboard OAuth callback returns `oauth_status=error`.

**Likely cause**: The 30-day refresh token expired, was never generated, or callback configuration is wrong.

**Diagnosis**:

- Check run errors from dashboard or `/api/v1/runs/{run_id}` for `invalid_grant`.
- Verify the SSM parameter exists:

```bash
aws ssm get-parameter \
  --name /workos-conduit/ninjaone/oauth-refresh-token \
  --with-decryption
```

- If dashboard callback fails, confirm `DASHBOARD_PUBLIC_BASE_URL_*` for the active realm plus `/dashboard/oauth/ninjaone/callback` matches the redirect URI registered in NinjaOne and sent on `/start`.

**Fix**:

1. Regenerate via dashboard: click **Generate Refresh Token** and complete the browser flow.
2. If dashboard is unavailable, run:

```bash
python scripts/ninjaone_oauth_bootstrap.py --write-ssm
```

3. Retry a sync after the new token is stored.

---

## 2a. Dashboard shows `dashboard_oauth_store_unreachable` with JSON parse error

**Symptom**: Logs repeatedly show `dashboard_oauth_store_unreachable` with `Expecting value: line 1 column 1`.

**Likely cause**: `NINJAONE_OAUTH_REFRESH_TOKEN_SSM_PARAM` contains legacy plain-string token data instead of the new JSON payload format.

**Fix**:

1. Regenerate a token via dashboard **Generate Refresh Token** (recommended), or:
2. Run `python scripts/ninjaone_oauth_bootstrap.py --write-ssm` to rewrite the SSM parameter using the JSON envelope format.

This warning is non-fatal; sync can still run, but dashboard metadata (generated/expiry timestamps) may be incomplete until the parameter is rewritten.

---

## 3. Every run returns `status: error` — same event keeps failing

**Symptom**: Dashboard shows `status: error` on every run. The `errors` array in the run detail always contains the same event ID. The sync is stuck.

**Likely cause**: `SYNC_STOP_ON_ERROR=true` (the default). When an event fails, the cursor does not advance. Every subsequent cycle re-fetches the same event and fails again.

**Diagnosis**:

```bash
# Get the failing run detail
RUN_ID=$(curl -s http://localhost:8080/api/v1/sync/status | jq -r '.last_run.run_id')
curl -s "http://localhost:8080/api/v1/runs/${RUN_ID}" | jq '.errors'
```

The `error_message` in the errors array will identify the root cause (NinjaOne API error, missing role mapping, network timeout, etc.).

**Fix options**:

1. **Fix the underlying error** — correct the configuration (e.g. add a role mapping, fix credentials) and trigger a sync. The event will retry successfully and the cursor advances.

2. **Manually advance the cursor** past the failing event — see [section 3](#3-manually-advancing-the-cursor) below.

3. **Switch to non-blocking mode** — set `SYNC_STOP_ON_ERROR=false`. Failing events are logged and skipped; the cursor advances past them permanently once a later event succeeds. Use this only if losing events is acceptable.

---

## 4. Manually advancing the cursor (break out of a retry loop)

**Symptom**: A specific WorkOS event is permanently broken (e.g. malformed data, deleted user) and will never succeed. You need to skip it without fixing the underlying event.

**When to use**: Only when you have confirmed the event cannot be processed and you accept that it will be permanently skipped.

**Steps**:

```bash
# 1. Find the current cursor (the stuck event's ID is just ahead of this)
aws ssm get-parameter --name /workos-conduit/cursor --query 'Parameter.Value' --output text

# 2. Find the event ID immediately after the failing one
#    Look at the run's errors array to find the failing event_id
RUN_ID="..."
FAILING_EVENT=$(curl -s "http://localhost:8080/api/v1/runs/${RUN_ID}" \
  | jq -r '.errors[0].event_id')
echo "Failing event: $FAILING_EVENT"

# 3. Identify the next event ID from WorkOS (the one after the failing one)
#    You can find this from a previous run's results list, or from the WorkOS dashboard.

# 4. Write the next event ID as the new cursor
NEXT_EVENT_ID="evt_XXXXX"  # ID of the event AFTER the failing one
aws ssm put-parameter \
  --name /workos-conduit/cursor \
  --value "$NEXT_EVENT_ID" \
  --overwrite

# 5. Trigger a sync to confirm it resumes cleanly
curl -s -X POST http://localhost:8080/api/v1/sync/trigger \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}' | jq .status
```

**Caution**: The failing event will be permanently skipped. The user or group change it represented will not be applied to NinjaOne. If the event was a user creation, you may need to manually create that user in NinjaOne or run the bootstrap script.

---

## 5. `status: partial_failure` — reading errors from run detail

**Symptom**: Dashboard shows `status: partial_failure`. Some events were processed; others failed. The cycle completed.

**Cause**: `SYNC_STOP_ON_ERROR=false` is set. One or more events raised exceptions. The cursor advanced past successful events; failing events were not retried.

**Diagnosis**:

```bash
RUN_ID="..."

# Show all errored events
curl -s "http://localhost:8080/api/v1/runs/${RUN_ID}" \
  | jq '.errors[] | {event_id, event_type, error_message}'

# Show action breakdown
curl -s "http://localhost:8080/api/v1/runs/${RUN_ID}" \
  | jq '[.results[].action] | group_by(.) | map({key: .[0], value: length}) | from_entries'

# Check if cursor advanced (partial success means cursor is ahead of where it was)
curl -s "http://localhost:8080/api/v1/runs/${RUN_ID}" \
  | jq '{cursor_before, cursor_after}'
```

**Fix**: Treat each `error_message` as a separate incident. Common causes: NinjaOne rate limits (see [section 6](#6-ninjaone-429-rate-limit-errors)), missing role mappings ([section 9](#9-all-group-events-returning-skipped)), or network timeouts.

---

## 5. WorkOS 401 / 403 errors

**Symptom**: Run detail shows errors with messages like `401 Unauthorized` or `403 Forbidden` from WorkOS. No events are fetched.

**Likely cause**: `WORKOS_API_KEY` is invalid, expired, or has the wrong permissions.

**Diagnosis**:

```bash
# Verify the key starts with the expected prefix
aws secretsmanager get-secret-value --secret-id workos-conduit/workos-api-key \
  | jq -r '.SecretString' | cut -c1-12
# Should show: sk_live_ or sk_test_

# Test the key directly against WorkOS
curl -s -H "Authorization: Bearer YOUR_KEY" \
  "https://api.workos.com/events?limit=1" | jq .
```

**Fix**:

- **sk_test_ key in production**: WorkOS test keys do not have access to production data. Generate a live API key from the WorkOS dashboard.
- **Key expired or revoked**: Generate a new key from the WorkOS dashboard → API Keys and update the Secrets Manager secret. The ECS task will pick it up on the next deploy or task restart (Secrets Manager values are injected at task start, not runtime).
- **Wrong directory**: Verify `WORKOS_DIRECTORY_ID` starts with `directory_` and matches the directory in your WorkOS tenant.

---

## 6. NinjaOne 429 rate-limit errors

**Symptom**: Run detail shows errors with `429` or `Too Many Requests`. Runs succeed during off-peak hours but fail during high-volume periods.

**Cause**: The NinjaOne API is returning HTTP 429. The client reads the `Retry-After` response header and sleeps before retrying, but may exhaust all retry attempts (`HTTP_RETRY_MAX_ATTEMPTS`) if rate-limiting persists.

**Diagnosis**:

```bash
# Check error messages in recent runs
curl -s "http://localhost:8080/api/v1/runs/?limit=10" \
  | jq '.[] | select(.status == "error" or .status == "partial_failure") | {run_id, started_at, errors: [.errors[].error_message]}'
```

**Fix**:

1. **Increase retry attempts**: Set `HTTP_RETRY_MAX_ATTEMPTS=5` to give the client more attempts.

2. **Increase backoff base**: Set `HTTP_RETRY_BACKOFF_BASE_SECONDS=2.0`. With 5 attempts this gives: 2s, 4s, 8s waits — giving NinjaOne more time to recover.

3. **Reduce sync frequency**: If triggered by EventBridge Scheduler, increase the interval from 5 minutes to 10 or 15 minutes.

4. **Contact NinjaOne support**: Request a rate limit increase if the volume is legitimately high.

Relevant settings (set as ECS environment variables):
```
HTTP_RETRY_MAX_ATTEMPTS=5
HTTP_RETRY_BACKOFF_BASE_SECONDS=2.0
```

---

## 7. S3 `AccessDenied` or SSM `AccessDenied`

**Symptom**: Runs fail with errors like `An error occurred (AccessDenied) when calling the PutObject operation` or `An error occurred (AccessDenied) when calling the PutParameter operation`.

**Likely cause**: The ECS task role is missing IAM permissions for S3 or SSM.

**Diagnosis**:

```bash
# Get the ECS task role ARN
aws ecs describe-task-definition --task-definition workos-conduit \
  | jq '.taskDefinition.taskRoleArn'

# List attached policies
ROLE_NAME="workos-conduit-task-role"
aws iam list-attached-role-policies --role-name $ROLE_NAME
aws iam list-role-policies --role-name $ROLE_NAME
```

**Required permissions** (see `infra/aws/iam-task-role-policy.json` for the reference policy):

| Service | Actions | Resource |
|---|---|---|
| SSM | `ssm:GetParameter`, `ssm:PutParameter` | `arn:aws:ssm:*:*:parameter/workos-conduit/*` |
| S3 | `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` | State bucket ARN |

**Fix**: Attach the reference policy from `infra/aws/iam-task-role-policy.json` to the task role, or add the missing actions inline. Changes take effect immediately for new API calls (no task restart needed).

**SSM `ParameterNotFound` on first run**: The cursor SSM parameter does not exist yet. This is normal — the application handles `ParameterNotFound` gracefully and treats it as "no prior cursor" (full event history fetch). The parameter is created automatically after the first successful event.

---

## 8. Group events returning `skipped` unexpectedly

**Symptom**: Group events (`dsync.group.user_added`, `dsync.group.user_removed`) are returning `action: skipped` for groups you expect to be processed.

**Cause**: The set of groups that are processed is derived solely from `NINJAONE_GROUP_ROLE_MAP`. There is no separate allow-list variable. If a group name from the event does not match any entry in the `organizations_groups_mapping` array of `NINJAONE_GROUP_ROLE_MAP`, the event is skipped.

**Common causes**:

### Group name not in role map

The `google_workspace_group_name` field in `NINJAONE_GROUP_ROLE_MAP` must exactly match the WorkOS group name. Matching is **exact and case-sensitive**. `"IT Admins"` and `"it admins"` are treated as different groups.

```bash
# Check the current role map
echo $NINJAONE_GROUP_ROLE_MAP
# or, if source=ssm:
aws ssm get-parameter --name /workos-conduit/ninjaone/group-role-map --query 'Parameter.Value' --output text

# Find the exact group name from structured logs
aws logs filter-log-events \
  --log-group-name /ecs/workos-conduit \
  --filter-pattern '"group_name"' \
  --limit 10 | jq '.events[].message | fromjson | .group_name'
```

**Fix**: Ensure the `google_workspace_group_name` field in each role map entry exactly matches the WorkOS group name (including capitalisation and spacing).

### Role map is empty

If `organizations_groups_mapping` is an empty array (`[]`), all group events are skipped. At least one entry is required for group events to be processed.

### Role is not `END_USER`

If an entry exists but `ninjaone_role` is not `END_USER`, the event is also skipped and a `WARNING` log line is emitted. Only the `END_USER` role is supported for group-driven provisioning.

---

## 9. All group events returning `skipped`

**Symptom**: Group events (`dsync.group.user_added`, `dsync.group.user_removed`) all have `action: skipped`. User events process normally.

**There are two independent skip layers.** Work through them in order:

### Layer 0: Engine-level user-event check

The engine derives the set of watched groups from `adapter.watched_groups()`, which returns the group names listed as `google_workspace_group_name` keys in `NINJAONE_GROUP_ROLE_MAP`. This is used for user-event filtering (see [section 10](#10-user-createdupdated-events-skipped-even-though-the-user-is-in-a-watched-group)); for group events themselves this layer is not the primary gate.

### Layer 1: Role map check (adapter level)

The NinjaOne adapter checks `NINJAONE_GROUP_ROLE_MAP`. If the group name from the event has no matching entry in `organizations_groups_mapping`, the adapter returns `SKIPPED`. If the group maps to a role other than `END_USER` (case-insensitive), the event is also skipped and a `WARNING` log line is emitted.

```bash
# If source=env
echo $NINJAONE_GROUP_ROLE_MAP
# Expected format:
# '{"organizations_groups_mapping": [{"ninjaone_organization_name": "...", "ninjaone_organization_id": "uuid", "google_workspace_group_name": "ninjaone-users", "ninjaone_role": "END_USER"}]}'

# If source=ssm
aws ssm get-parameter --name /workos-conduit/ninjaone/group-role-map --query 'Parameter.Value' --output text
```

**An empty `organizations_groups_mapping` array means ALL group events are skipped** at the adapter level — this is the default. You must add at least one entry for group events to be processed.

**Only `END_USER` role is supported.** Other role values (e.g. `administrator`, `technician`) will produce a WARNING log and return SKIPPED:

```bash
# Look for unsupported role warnings in logs
aws logs filter-log-events \
  --log-group-name /ecs/workos-conduit \
  --filter-pattern '"group_membership_skipped_unsupported_role"' \
  --limit 10 | jq '.events[].message | fromjson | {group, role, reason}'
```

**Common role map mistakes**:

| Mistake | Symptom |
|---|---|
| Empty array `[]` | All group events SKIPPED |
| Role other than `END_USER` (e.g. `"administrator"`) | WARNING log + SKIPPED; not an error |
| Group name case mismatch | Group not found in map → SKIPPED |
| `ninjaone_organization_id` is an integer, not a string | JSON parse error or wrong org assigned |

**Note on org changes**: When a user is moved from one Google Workspace group to another (which maps to a different NinjaOne organization), the next `dsync.group.user_added` event for the new group will patch the user's `organizationId` in NinjaOne automatically. The result will be `action: updated` with `organizationId` in `changed_fields`.

---

## 10. User created/updated events skipped even though the user is in a watched group

**Symptom**: `dsync.user.created` or `dsync.user.updated` events have `action: skipped`. The user exists in your WorkOS directory and belongs to an allowed group, but is not being provisioned.

**Cause**: The engine derives the set of watched groups from `adapter.watched_groups()`, which returns the `google_workspace_group_name` keys from `NINJAONE_GROUP_ROLE_MAP`. On every `dsync.user.created`/`dsync.user.updated` event the engine checks (via the WorkOS API) whether the user belongs to any of those groups. If the user is not in any watched group, the event is skipped — this check is independent of the event's payload.

**Additional note**: If `NINJAONE_GROUP_ADMINS` is set and the user belongs to that group, the event is intentionally skipped. Admin users are managed separately and are not provisioned through the standard user-event pipeline.

**Diagnosis**:

```bash
# Check the role map to see which group names are watched
echo $NINJAONE_GROUP_ROLE_MAP
# or: aws ssm get-parameter --name /workos-conduit/ninjaone/group-role-map --query 'Parameter.Value' --output text

# Check logs for the skip event
aws logs filter-log-events \
  --log-group-name /ecs/workos-conduit \
  --filter-pattern '"user_not_in_allowed_group"' \
  --limit 10 | jq '.events[].message | fromjson | {email, event_type}'
```

**Fix**:

1. **Group name mismatch**: Verify the `google_workspace_group_name` values in `NINJAONE_GROUP_ROLE_MAP` exactly match the WorkOS group names (case-sensitive).
2. **User not yet in group**: The WorkOS API is queried at event processing time. If the user was not added to the group before the event fired, they will be skipped. Wait for a `dsync.group.user_added` event which will create them via the group membership handler.
3. **Admin group membership**: If the user is in the group specified by `NINJAONE_GROUP_ADMINS`, the skip is intentional. Admin users are not provisioned via the user-event handler.

**Note**: `dsync.user.deleted` events always bypass the group check — deactivation proceeds regardless of current group membership.

---

## 11. Dashboard showing no runs / blank history table

**Symptom**: Opening `http://localhost:8080/` shows the dashboard but the run history table is empty. `GET /api/v1/runs/` returns `[]`.

**Possible causes**:

### No syncs have run yet

Trigger a sync manually to create the first run record:
```bash
curl -s -X POST http://localhost:8080/api/v1/sync/trigger \
  -H "X-API-Key: local-dev-key" \
  -H "Content-Type: application/json" \
  -d '{}' | jq .
```

### Using the `local` backend but the server restarted

When `CURSOR_BACKEND=local`, the cursor is persisted in `.local-state/cursor.txt` and survives restarts. If `.local-state/` was deleted or `LOCAL_STATE_DIR` changed, both cursor and run history may appear reset. Check:

```bash
ls .local-state/runs/
```

### Wrong S3 bucket or prefix (when `STATE_BACKEND=aws`)

The `S3_STATE_BUCKET` or `S3_STATE_PREFIX` does not match where run records were written. Run records are stored at `s3://{bucket}/{prefix}YYYY/MM/DD/{run_id}.json`.

```bash
aws s3 ls "s3://${S3_STATE_BUCKET}/${S3_STATE_PREFIX}" --recursive | head -20
```

If the prefix differs between environments (e.g. `prod/runs/` vs `runs/`), set `S3_STATE_PREFIX` to match.

### S3 `ListBucket` permission missing (when `STATE_BACKEND=aws`)

`list_recent_runs` calls `s3:ListObjectsV2` before fetching individual objects. If the task role is missing `s3:ListBucket`, the list returns empty rather than an error (boto3 silently returns an empty list on access-denied for `ListObjects`).

Verify the task role has `s3:ListBucket` on the state bucket (see [section 7](#7-s3-accessdenied-or-ssm-accessdenied)).

### Dashboard disabled

Verify `DASHBOARD_ENABLED` is not set to `false`:
```bash
curl -sv http://localhost:8080/ 2>&1 | grep -E "HTTP|detail"
# If disabled: {"detail": "Dashboard disabled"}
```
