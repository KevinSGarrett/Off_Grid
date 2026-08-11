# Off Grid Commercial Intelligence Engine

[![CI](https://github.com/KevinSGarrett/Off_Grid/actions/workflows/ci.yml/badge.svg)](https://github.com/KevinSGarrett/Off_Grid/actions/workflows/ci.yml)

A local-first FastAPI and React application that turns construction-project records into evidence-backed commercial opportunities. It keeps source trust separate from commercial fit, resolves organizations and people conservatively, and prevents uncertain records from becoming false CRM certainty.

## Release status

The public repository is runnable from a clean clone. The release gates currently prove:

- reproducible Python 3.12 installation and public-safe test matrix;
- `npm ci`, TypeScript validation, and a production Vite bundle;
- a combined Docker image with a sanitized deterministic demo seed;
- HTTP health, Basic access control, read-only employer UI, and deterministic reset;
- Git, Docker-context, built-image, secret, and private-source boundaries;
- green required GitHub checks on protected `main`.

This is a release-ready interview/demo application, not a claimed production deployment. No AWS environment is deployed from this repository, and Apollo, Pipedrive, Google, Trello, OpenAI, outreach, and other consequential external writes remain off or dry-run unless separately authorized.

## Run with Docker

Docker is the smallest supported employer-demo path:

```bash
docker build -t offgrid-commercial-intelligence:local .
docker run --rm -p 8080:8000 \
  -e REQUIRE_ACCESS_CONTROL=true \
  -e APP_ACCESS_PASSWORD='choose-a-temporary-password' \
  offgrid-commercial-intelligence:local
```

Then verify `http://localhost:8080/api/v1/health` and open `http://localhost:8080`. The username may be any non-empty value; the password is the value supplied through `APP_ACCESS_PASSWORD`.

The container resets its writable runtime database from the sanitized seed at startup by default. Raw licensed PDFs are not present in Git or in the image.

## Develop and test

Requirements: Python 3.12, Node.js 22, npm, and Docker for the image gate.

```bash
python -m venv .venv
# Activate .venv using your shell's normal command.
python -m pip install -e ".[dev]"
python scripts/run_public_test_matrix.py

npm --prefix apps/web ci --no-audit --no-fund
npm --prefix apps/web run typecheck
npm --prefix apps/web run build

python scripts/validate_git_privacy.py --require-git
python scripts/validate_github_config.py
python scripts/validate_aws_infra.py
```

`make test` runs the same public-safe Python matrix as CI. `make test-private` is reserved for the canonical private workspace, where the licensed Stafford and EE Reed source PDFs are available. Their tests remain visible in the repository, but their source documents are intentionally not published.

## Golden commercial conclusion

Stafford remains **PURSUE / VERIFY, Lead-ready / Deal-blocked**. Commercial Fit is **80/100** and Data Confidence is **69.25/100**. Removing the source-reported `$7.5B` value still yields **75/100 (PURSUE)**, so the recommendation is not driven by an unverified headline amount.

Doug Meadows remains a source-supported Stafford-associated investigation anchor; rental authority remains **UNKNOWN**. EE Reed source totals reconcile to **6 planning / 87 post-bid / 74 bidding-role**. The interview KPI remains **N/A** because production outcome history is not connected.

## Privacy and safety

This repository is intentionally public and contains only the sanitized release boundary. Licensed source PDFs, original chat logs, local Jira/control records, private research continuity, credentials, and unnecessary PII remain excluded by policy and validators. The demo database is a minimized derivative snapshot, not a copy of the raw documents.

See [SECURITY.md](SECURITY.md) for disclosure and data-handling rules and [CONTRIBUTING.md](CONTRIBUTING.md) for the required development workflow.
