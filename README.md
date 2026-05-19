# WorkOS Conduit

A **generic, extensible, open-source** user provisioning bridge that syncs WorkOS Directory Sync events to third-party targets.

```
Google Workspace → WorkOS → workos-conduit → NinjaOne (+ future targets)
```

## Features

- **Pluggable adapters**: NinjaOne ships today. Add Zendesk, Freshservice, Jira SM by implementing one class.
- **Pluggable cloud backends**: AWS SSM + S3 today. Azure / GCS / local filesystem via the same registry pattern.
- **API-driven sync**: No internal timer. Trigger via `POST /api/v1/sync/trigger` from EventBridge, cron, or the built-in dashboard.
- **Immutable audit log**: Every run is written to S3 (or local filesystem) as append-only JSON — no database needed.
- **Built-in dashboard**: Dark-mode HTML dashboard served by FastAPI. Trigger sync, browse run history, inspect errors.
- **Stdout-first JSON logs**: CloudWatch, Datadog, and Splunk consume stdout unchanged via the ECS `awslogs` driver.
- **GPL-3.0**: All contributions stay open source.

## Quick Start

```bash
git clone https://github.com/YOUR_ORG/workos-conduit.git
cd workos-conduit
make install
cp .env.example .env   # fill in credentials
make dev               # → http://localhost:8080
```

## Configuration

All settings are environment variables. See [.env.example](.env.example) for the full list with defaults.

Key variables:

| Variable | Default | Description |
|---|---|---|
| `WORKOS_API_KEY` | required | WorkOS API key |
| `WORKOS_DIRECTORY_ID` | required | WorkOS directory ID |
| `SYNC_TARGET_ADAPTER` | `ninjaone` | Target adapter key |
| `NINJAONE_OAUTH_CLIENT_ID` | required (ninjaone) | NinjaOne OAuth app client ID |
| `NINJAONE_OAUTH_CLIENT_SECRET` | required (ninjaone) | NinjaOne OAuth app client secret |
| `NINJAONE_OAUTH_REFRESH_TOKEN_SSM_PARAM` | `/workos-conduit/ninjaone/oauth-refresh-token` | SecureString parameter storing refresh-token payload |
| `DASHBOARD_PUBLIC_BASE_URL` | required for dashboard OAuth flow | Public base URL used to build OAuth callback URI |
| `CURSOR_BACKEND` | `aws` | Cursor persistence: `aws` (SSM), `local` (file, survives restarts), `memory` (in-process only) |
| `STATE_BACKEND` | `aws` | Run record persistence: `aws` (S3) or `local` (filesystem under `LOCAL_STATE_DIR`) |
| `LOCAL_STATE_DIR` | `.local-state` | Root dir for local backends. Cursor: `cursor.txt`. Runs: `runs/YYYYMMDDHHMMSS_{id}.json` |
| `API_SECRET_KEY` | required | `X-API-Key` header value for `/sync/trigger` |
| `S3_STATE_BUCKET` | required (aws) | S3 bucket for run records |
| `SYNC_STOP_ON_ERROR` | `true` | Stop on first error (retry next cycle) vs continue |
| `LOG_FORMAT` | `json` | `json` for production, `console` for local dev |
| `DASHBOARD_ENABLED` | `true` | Enable built-in HTML dashboard |

For the complete OAuth setup, callback URI format, and refresh-token rotation workflow, see [docs/configuration.md](docs/configuration.md).

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/sync/trigger` | Trigger a sync cycle (`X-API-Key` required) |
| `GET` | `/api/v1/sync/status` | Most recent run summary |
| `GET` | `/api/v1/runs/` | List recent runs |
| `GET` | `/api/v1/runs/{run_id}` | Single run detail |
| `GET` | `/health/` | Liveness (always 200) |
| `GET` | `/health/ready` | Readiness (checks adapter + backends) |
| `GET` | `/` | Dashboard HTML |
| `POST` | `/dashboard/oauth/ninjaone/start` | Starts dashboard OAuth flow, returns `authorize_url` (`X-API-Key` required) |
| `GET` | `/dashboard/oauth/ninjaone/callback` | OAuth callback endpoint that exchanges code and stores refresh token in SSM |

## AWS Deployment

```bash
# 1. Bootstrap existing users
python scripts/bootstrap.py --dry-run
python scripts/bootstrap.py

# 2. Deploy to ECS Fargate
bash scripts/deploy.sh us-east-1 123456.dkr.ecr.us-east-1.amazonaws.com/workos-conduit my-cluster workos-conduit-svc

# 3. Schedule syncs via EventBridge (optional)
# See infra/aws/eventbridge-schedule.json
```

Infrastructure files:
- [`infra/aws/task-definition.json`](infra/aws/task-definition.json)
- [`infra/aws/iam-task-role-policy.json`](infra/aws/iam-task-role-policy.json)
- [`infra/aws/eventbridge-schedule.json`](infra/aws/eventbridge-schedule.json)

## Extending

- **New target adapter**: See [CONTRIBUTING.md](CONTRIBUTING.md#adding-a-new-target-adapter)
- **New cloud backend**: See [CONTRIBUTING.md](CONTRIBUTING.md#adding-a-new-cloud-backend)

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).
