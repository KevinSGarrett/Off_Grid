## Purpose

Describe the user/business problem this PR solves and the smallest coherent change made.

## Evidence / source-of-truth impact

- [ ] No employer-facing factual claim was added without source evidence or an explicit inference/unknown label.
- [ ] Golden Stafford/EE Reed expectations are unchanged, or the change is justified with source evidence and a decision-log entry.
- [ ] No AI inference is promoted to `EXPLICIT` or `VERIFIED` truth.

## Safety / privacy

- [ ] No raw ConstructConnect PDF, original chat log, private source export, `.env`, token, or unmasked contact directory is included.
- [ ] `DEMO_MODE` and external-write gates remain fail-closed.
- [ ] Pipedrive/Google/Trello/email/OpenAI mutations are not introduced without the existing deterministic authorization/readiness boundary.

## Validation

- [ ] `make test`
- [ ] `make github-check`
- [ ] `make privacy-check`
- [ ] Frontend type/build check run when package-registry access is available.
- [ ] Relevant docs / traceability / issue state updated.

## Release impact

Risk: `low | medium | high`

Rollback / recovery notes:

Reviewer notes:
