# Contributing to WorkOS Conduit

Thank you for contributing! This file explains how to set up a local dev environment, run tests, and add new adapters or cloud backends.

## Local Development

```bash
# 1. Clone and create virtualenv
git clone https://github.com/YOUR_ORG/workos-conduit.git
cd workos-conduit
make install          # creates .venv and installs all deps

# 2. Copy .env.example and fill in credentials
cp .env.example .env

# 3. Run with hot-reload + console logging
make dev              # → http://localhost:8080
# or
bash scripts/dev.sh
```

To run via Docker (closest to production):
```bash
docker-compose up --build
```

## Running Tests

```bash
make test             # pytest + coverage
make fmt-check        # black + ruff (same as CI)
make fmt              # auto-fix formatting
```

Coverage must stay at or above **80% line coverage**. PRs that reduce coverage are rejected.

## Adding a New Target Adapter

To add a new provisioning target (e.g. Zendesk):

1. Create `src/adapters/zendesk/` directory
2. `client.py` — Zendesk REST API client
3. `mapper.py` — maps `ProvisioningUser` → Zendesk payload
4. `adapter.py` — implements all `BaseTargetAdapter` abstract methods:
   - `provision_user_created`
   - `provision_user_updated`
   - `provision_user_deactivated`
   - `provision_group_membership`
   - `health_check`
5. Register in `src/adapters/registry.py`:
   ```python
   from src.adapters.zendesk.adapter import ZendeskAdapter
   register_adapter("zendesk", lambda s: ZendeskAdapter(s))
   ```
6. Add `ZENDESK_*` env vars to `src/config.py` and `.env.example`
7. Write tests in `tests/unit/` and `tests/integration/`

**No other files need to change.**

## Adding a New Cloud Backend

To add a new cloud (e.g. Azure):

1. Create `src/backends/azure/` directory
2. Implement `CursorBackend` subclass (e.g. `AppConfigCursorBackend`)
3. Implement `StateBackend` subclass (e.g. `BlobStateBackend`)
4. Register in `src/backends/registry.py`:
   ```python
   register_cursor_backend("azure", lambda s: AppConfigCursorBackend(s))
   register_state_backend("azure", lambda s: BlobStateBackend(s))
   ```
5. Add `AZURE_*` env vars to `src/config.py` and `.env.example`
6. Add deployment manifests under `infra/azure/`
7. Write tests using the Azure SDK's mocking equivalent (`azure-sdk-for-python` provides test fakes)

**No other files need to change.**

## Cursor-Advance Semantics

The cursor only advances past events that processed without error.

- `SYNC_STOP_ON_ERROR=true` (default): if an event fails, the run stops. On the next run, the same event is retried. Safe for most adapters.
- `SYNC_STOP_ON_ERROR=false`: if an event fails, it is logged and skipped. Subsequent successful events advance the cursor past it, so the failing event is never retried. Use only if your target adapter is idempotent and replay is not desired.

## Code Style

Black (formatter) and ruff (linter) are enforced in CI. Run before submitting:

```bash
make fmt          # format + lint fix
make fmt-check    # check only (what CI runs)
```

## PR Checklist

- [ ] Tests pass (`make test`)
- [ ] Code formatted (`make fmt-check`)
- [ ] New env vars documented in `.env.example`
- [ ] New adapter/backend documented in `CONTRIBUTING.md`
- [ ] Coverage not decreased

## License

By contributing you agree your code is licensed under **GPL-3.0-or-later**.
Add the SPDX header to every new `.py` file:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors
```
