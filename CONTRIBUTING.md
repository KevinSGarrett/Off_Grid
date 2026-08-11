# Contributing

This repository is a private interview-project codebase with real licensed construction-source data in the local cumulative pack. Contributions must preserve the evidence/trust and external-write boundaries that make the system credible.

## Workflow

1. Start from an up-to-date `main`.
2. Use a short-lived branch: `wave/<n>-<slug>`, `feat/<slug>`, `fix/<slug>`, `docs/<slug>`, or `chore/<slug>`.
3. Make one coherent change. Do not combine an architecture rewrite, UI redesign, and unrelated cleanup in one PR.
4. Run `make test`, `make github-check`, and `make privacy-check`.
5. Open a pull request using the repository template.
6. Merge only after required CI checks pass. Prefer squash merge to keep the interview-project history concise.

## Source / evidence rules

- Supplied employer material and preserved source evidence outrank assumptions.
- Do not change a golden expectation merely to make a failing implementation pass.
- `INFERRED` is not `EXPLICIT`; `ROLE_RELEVANT` is not `AUTHORITY_VERIFIED`.
- Do not invent a project value, product specification, contact authority, rental partner, demo, outcome, or KPI.
- Any intentional change to a locked decision or architecture boundary must be documented in `project/DECISION_LOG.md` and, when architectural, an ADR.

## Privacy and secrets

Never commit:

- `context/private_source_documents/`;
- `context/original_chat_logs/`;
- `data/private/`;
- `.env` or credentials;
- raw ConstructConnect exports or unnecessary contact PII.

The local cumulative pack may contain private continuity material even though the Git repository must not. Run `make privacy-check` before push.

## External writes

Live writes to Off Grid systems, prospect outreach, and billable AWS provisioning are not normal development actions. Preserve existing feature flags, deterministic readiness gates, idempotency controls, and explicit authorization requirements.
