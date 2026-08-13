# Public Data Boundary

Off Grid publishes application code, reproducibility assets, sanitized tests, and one publicly viewable sanitized demo database. It does not publish the supplied licensed PDFs, raw contact directories, live credentials, private research continuity, or source-derived direct contact channels.

The committed demo database preserves the decision-useful project and company facts needed for the employer workflow. Its data classes are:

- Public project context: project identity, location, stage, broad type, organization relationships, and caveated source-reported value.
- Publicly researched people/entities: only records backed by retained first-party or other public evidence. Employment, project association, role relevance, and rental authority remain separate states.
- Licensed-source-only contacts: retained only as deterministic `Source Contact NN` structural records. Their names, aliases, emails, phones, addresses, original observation fingerprints, and report prose are not redistributed.

Private source-document filenames, content hashes, filesystem paths, and binary references are replaced by deterministic public-demo sentinels. Long licensed descriptions are replaced by a short decision-useful summary. This preserves source relationships and failure/anomaly behavior without publishing the underlying material.

`scripts/audit_public_data_boundary.py` enumerates every SQLite table and text-bearing column, verifies those rules, classifies every tracked file with a public rationale, and can compare the current seed and full Git history against private source values without writing those values to its report.

Questionable tracked-file decisions:

| File or category | Decision | Public benefit and boundary |
| --- | --- | --- |
| `data/demo_seed/offgrid_demo_seed.db` | Public after machine audit | Enables a clean, reproducible demo; contains only the minimized representation described above. |
| `.env.example` | Public | Documents variable names and safe placeholders; `.env` and credential values remain ignored. |
| `tests/golden/sanitized/` and public tests | Public | Demonstrate expected behavior with sanitized facts; private-PDF regressions remain local. |
| Build, privacy, deployment, and validation scripts | Public | Let a reviewer reproduce release and safety gates without private inputs. |
| GitHub workflows and IaC | Public | Establish repeatable OIDC deployment and cost-controlled architecture; no credentials are embedded. |
| Root/application/release documentation | Public | Explains operation, evidence boundaries, security, and limitations without private continuity records. |
| Raw PDFs, contact exports, `.env`, Jira mirror, research continuity, screenshots, and release working evidence | Private/ignored | Not required to review the application and may contain licensed, personal, credential, or internal process material. |

Full-history cleanup is intentionally not performed by the audit. If the history comparison finds a private-source-only value in an older public blob, the report fails with `FAIL_REQUIRES_GOVERNED_HISTORY_DECISION`; remediation requires explicit repository-governance approval because it rewrites shared history.
