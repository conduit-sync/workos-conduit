# Changelog

All notable changes to this project follow [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

## [v0.1.0]

### Added

- Initial implementation: WorkOS Directory Sync → NinjaOne provisioning
- Generic `BaseTargetAdapter` interface and registry for multi-target extensibility
- Generic `CursorBackend` / `StateBackend` interfaces for multi-cloud extensibility
- AWS backend implementations: `SsmCursorBackend` (SSM Parameter Store) and `S3StateBackend` (S3)
- FastAPI server: `POST /api/v1/sync/trigger`, `GET /api/v1/runs`, `GET /health` endpoints
- Built-in HTML dashboard (toggleable via `DASHBOARD_ENABLED`), dark-mode GitHub-style UI
- `SyncRunContext` (Unit of Work) for clean, testable run-cycle state management
- Configurable HTTP retries, page sizes, logging output (`stdout`/`file`/`both`) and format (`json`/`console`)
- `SYNC_STOP_ON_ERROR` flag: `true` retries on failure, `false` skips and continues
- Black + ruff linting enforced in CI
- SonarQube project configuration (`sonar-project.properties`)
- GPL-3.0-or-later license
- GitHub Actions CI (lint + test + SonarQube) and release (GHCR push on tag) workflows
- Python 3.13 target
- Makefile for local dev workflow (`make install`, `make dev`, `make test`, `make fmt`)
- `scripts/bootstrap.py` for one-time full user import
- `scripts/deploy.sh` for ECS Fargate deployment
- AWS infra manifests: ECS task definition, IAM task role policy, EventBridge schedule
