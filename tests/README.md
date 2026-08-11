# Test Area

Testing is risk-driven rather than vanity-coverage driven. Waves 1-13 establish pack, architecture, model, parser, scoring, resolution, integration, OpenAI, API and frontend contracts. Wave 14 adds formal reliability lanes:

- `tests/golden/` - real Stafford/EE Reed golden truth and regression invariants;
- `tests/integration/` - service/API integration;
- `tests/contract/` - observability, health, privacy and API-boundary contracts;
- `tests/e2e/` - employer golden path over the real backend state;
- `tests/failure/` - malformed input and provider degradation/recovery;
- `tests/load/` - clearly labeled synthetic scale/idempotency checks;
- `tests/unit/` - deterministic component contracts.

Synthetic data is used only for scale/load behavior. It is never evidence for the six employer questions. External writes remain disabled/dry-run unless explicitly authorized by the owner integration boundary.
