# Contributing

This public repository is the sanitized application boundary for an interview/demo project. A broader local workspace may contain licensed construction-source material; none of that private continuity material belongs in GitHub issues, commits, pull requests, logs, screenshots, or container images.

## Workflow

1. Start from an up-to-date `main` and use a short-lived branch.
2. Make one coherent change and preserve the evidence/trust boundaries.
3. Run `python scripts/run_public_test_matrix.py` (or `make test`).
4. Run `python scripts/validate_github_config.py` and `python scripts/validate_git_privacy.py --require-git`.
5. For frontend changes, run `npm --prefix apps/web ci`, typecheck, and build.
6. For release-boundary changes, build the Docker image and verify health, access control, reset, and image privacy.
7. Open a pull request and merge only after every required check passes.

The canonical private workspace may additionally run `make test-private` with the protected Stafford and EE Reed PDFs. Public CI uses the tracked public-safe matrix and sanitized demo seed.

## Truth rules

- Supplied evidence outranks assumptions; do not change a golden expectation merely to make a regression green.
- `INFERRED` is not `EXPLICIT`; `ROLE_RELEVANT` is not `AUTHORITY_VERIFIED`.
- Do not invent a project value, product specification, contact authority, rental partner, demo, outcome, or KPI.
- Keep Lead readiness and Deal readiness separate.
- Any intentional change to a locked decision or architecture boundary requires explicit, reviewable evidence.

## Never commit

- `context/private_source_documents/` or raw ConstructConnect exports;
- original chat logs, local Jira/control packs, or private research continuity;
- `.env`, credentials, access tokens, private keys, or session material;
- unmasked contact exports or runtime databases containing source PII.

External employer-system writes, prospect outreach, and billable cloud provisioning require separate explicit authorization. Preserve off/dry-run defaults, deterministic readiness gates, and idempotency controls.
