# Security and private-data policy

## Repository boundary

This GitHub repository is intentionally **PUBLIC**. Only the sanitized runnable application, public-safe tests, configuration, prompts, and minimized demo seed belong here. The canonical local workspace is broader and may contain licensed source documents, private project controls, and credentials that must never cross the publication boundary.

CI validates the tracked-file boundary with `scripts/validate_git_privacy.py --require-git`. The Docker context and built image are separate security boundaries and must also exclude protected material.

## Never publish

- raw ConstructConnect PDFs or other licensed source exports;
- original project-design chats, local Jira/control data, or private research continuity;
- unmasked contact-directory exports or unnecessary PII;
- `.env`, API keys, AWS credentials, tokens, private keys, passwords, or session material;
- generated databases or logs containing private source data.

Do not place sensitive material in a public GitHub issue. Report a security concern privately to the repository owner with the minimum sanitized reproduction necessary.

## Runtime boundaries

- Employer demo mode is read-only and hides raw private source material.
- Public employer-demo dashboard and demo-safe read APIs require no viewer login.
- Health, application, assets, and demo-safe read APIs are intentionally publicly viewable.
- External-system writes remain off/dry-run unless an explicitly authorized live path passes deterministic gates.
- OpenAI is optional, server-side, budgeted, and not a source of deterministic truth or a direct CRM writer. The authorized AWS demo enables only the bounded read-only analyst path; the deterministic fallback remains available.
- Provider outages must not make the deterministic core unavailable.
- The authorized demo is deployed to AWS account `257851647752` in `us-east-1` through GitHub Actions OIDC. Cloud credentials and provider secrets remain server-side; the public repository contains only reproducible IaC and workflow definitions.
- Removing the dashboard viewing login does not weaken deterministic authorization gates for Apollo calls, CRM writes, or other consequential external actions.

If a credential may have entered Git history, revoke it first, then privately coordinate history remediation and a clean privacy revalidation.
