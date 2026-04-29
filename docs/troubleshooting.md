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
| `ninjaone_client_id and ninjaone_client_secret required` | `NINJAONE_CLIENT_ID` or `NINJAONE_CLIENT_SECRET` |
| `s3_state_bucket required when state_backend=aws` | `S3_STATE_BUCKET` |
| `sync_allowed_groups_ssm_param required` | `SYNC_ALLOWED_GROUPS_SSM_PARAM` (when source=ssm) |
| `ninjaone_group_role_map_ssm_param required` | `NINJAONE_GROUP_ROLE_MAP_SSM_PARAM` (when source=ssm) |

**Fix**: Set the missing variable in your ECS task definition or Secrets Manager and redeploy. For Secrets Manager variables (`WORKOS_API_KEY`, `NINJAONE_CLIENT_ID`, `NINJAONE_CLIENT_SECRET`, `API_SECRET_KEY`), ensure the ECS task role has `secretsmanager:GetSecretValue`.

---

## 2. Every run returns `status: error` — same event keeps failing

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

## 3. Manually advancing the cursor (break out of a retry loop)

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

## 4. `status: partial_failure` — reading errors from run detail

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

## 8. `SYNC_ALLOWED_GROUPS` not filtering as expected

**Symptom**: Groups you expected to be skipped are still being processed. Or all group events are being skipped even though the list should allow them.

**Common causes**:

### Wrong JSON format

The `SYNC_ALLOWED_GROUPS` value must be a valid JSON array string.

```bash
# Correct
SYNC_ALLOWED_GROUPS='["IT Admins", "Support Team"]'

# Wrong — missing quotes around values
SYNC_ALLOWED_GROUPS=[IT Admins, Support Team]

# Wrong — trailing comma (invalid JSON)
SYNC_ALLOWED_GROUPS='["IT Admins",]'
```

Test the JSON locally before deploying:
```bash
echo '["IT Admins", "Support Team"]' | python3 -c "import json,sys; print(json.load(sys.stdin))"
```

### Source mismatch

If `SYNC_ALLOWED_GROUPS_SOURCE=ssm` but the SSM parameter does not exist or has the wrong value, the application raises `ParameterNotFound` at event-processing time (not at startup). Check the SSM parameter:

```bash
aws ssm get-parameter --name /workos-conduit/allowed-groups --query 'Parameter.Value' --output text
```

### Case sensitivity

Group name matching is **exact and case-sensitive**. `"IT Admins"` and `"it admins"` are different groups. The group name in the allow-list must exactly match the WorkOS group name.

```bash
# Find the exact group name from a run detail
curl -s "http://localhost:8080/api/v1/runs/RUN_ID" \
  | jq '.results[].role' # for group events, check the group name via the dashboard

# Or look in structured logs
aws logs filter-log-events \
  --log-group-name /ecs/workos-conduit \
  --filter-pattern '"group_name"' \
  --limit 10 | jq '.events[].message | fromjson | .group_name'
```

### lru_cache not refreshing

When running locally and changing `.env`, the in-process settings cache is not automatically cleared. Restart the dev server after changing `SYNC_ALLOWED_GROUPS`.

When `SYNC_ALLOWED_GROUPS_SOURCE=ssm`, the allow-list is re-read on every `run_cycle()` call — no restart needed.

---

## 9. All group events returning `skipped`

**Symptom**: Group events (`dsync.group.user_added`, `dsync.group.user_removed`) all have `action: skipped`. User events process normally.

**There are two independent skip layers.** Work through them in order:

### Layer 1: Allow-list check (handler level)

Check whether `SYNC_ALLOWED_GROUPS` is non-empty and excludes your groups:

```bash
# If source=env
echo $SYNC_ALLOWED_GROUPS

# If source=ssm
aws ssm get-parameter --name /workos-conduit/allowed-groups --query 'Parameter.Value' --output text
```

If the allow-list is non-empty and the group name is not in it, the event is skipped at the handler level before the adapter is called. An empty list (`[]`) allows all groups through.

### Layer 2: Role map check (NinjaOne adapter level)

If the allow-list passes, the NinjaOne adapter checks `NINJAONE_GROUP_ROLE_MAP`. If the group name has no entry, the adapter returns `SKIPPED`.

```bash
# If source=env
echo $NINJAONE_GROUP_ROLE_MAP
# Expected: '{"IT Admins": "administrator", "Support": "technician"}'

# If source=ssm
aws ssm get-parameter --name /workos-conduit/ninjaone/group-role-map --query 'Parameter.Value' --output text
```

**An empty role map `{}` means ALL group events are skipped** at the adapter level — this is the default. You must add at least one entry for group events to be processed.

**Common role map mistakes**:

| Mistake | Symptom |
|---|---|
| Empty object `{}` | All group events SKIPPED |
| Wrong role name (e.g. `"Administrator"` vs `"administrator"`) | NinjaOne returns 400 or 422 |
| Group name case mismatch | Group not found in map → SKIPPED |

Verify that your role names match NinjaOne exactly:
```bash
# List NinjaOne roles via the API (requires auth)
curl -s -H "Authorization: Bearer TOKEN" \
  "https://app.ninjarmm.com/v2/roles" | jq '.[].name'
```

---

## 10. Dashboard showing no runs / blank history table

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

When `CURSOR_BACKEND=local`, the cursor resets to zero on every restart but run records persist in `.local-state/runs/`. If the directory was deleted or `LOCAL_STATE_DIR` changed, records are gone. Check:

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
