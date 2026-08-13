# Configuration Area

Qualification, trust and product behavior is executable, versioned configuration.

Current controlled configuration:

- `qualification.yaml` — factor weights/maxima, thresholds, Fit × Confidence action matrix, counterfactual labels and Decision-Changing Unknowns;
- `trust_confidence.yaml` — data-confidence components, source/validation treatment and quality penalties;
- `products.yaml` — KVT/KV6/KVP approved product facts, unknown specifications, fit rules and validation caps.

Rules:
- weights/thresholds live in versioned configuration, not hard-coded project logic;
- changing behavior requires a version bump before persistence;
- product facts must be Tier-1/verified evidence, while project/product fit remains commercial inference;
- no capacity/runtime/pricing/ROI/quantity/savings may be invented;
- environment-specific secrets never live here.

## Entity resolution

`entity_resolution.yaml` versions deterministic-first project/organization/person matching, phase parsing, no-silent-fuzzy-merge policy and account-freshness thresholds. Its content hash/version is persisted in `ConfigVersion` when entity resolution runs.

## Contact resolution

- `contact_resolution.yaml` — candidate-ranking model and fail-closed state policy (`contact-resolution-1.0`);
- `personas.yaml` — configurable Stafford investigation personas (`personas-1.0`);
- `source_precedence.yaml` — attribute-specific source authority (`source-precedence-1.0`).

Candidate rank means who to investigate first. It never changes rental authority to VERIFIED without qualifying authority evidence.

## Commercial workflow and integrations

`commercial_workflow.yaml` defines versioned contractor/rental motions, inferred demand thresholds, dependency-aware Stafford actions, the First-Call Kit and structured outcome categories. It must not be used to invent a rental provider, decision maker or commercial activity.

- `integrations.yaml` — Pipedrive readiness/mapping plus Sheets/Forms/Trello contract configuration (`pipedrive-1.0`, `reporting-integrations-1.0`).
