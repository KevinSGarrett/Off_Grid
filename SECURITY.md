# Security and private-data policy

## Repository visibility

The intended GitHub repository is **PRIVATE**. The local cumulative wave pack is broader than the Git repository and may contain private source continuity material.

## Never commit

- raw ConstructConnect PDFs or other licensed source exports;
- original project-design chat logs;
- unmasked contact-directory exports;
- `.env` files, API keys, AWS credentials, tokens, private keys, or session material;
- generated local databases/logs containing source PII.

`.gitignore` and `scripts/validate_git_privacy.py` enforce the primary path boundary. CI runs the same policy against `git ls-files` so ignored files cannot become silently tracked later.

## Reporting a security issue

Do not place secrets, licensed source material, or unnecessary PII in a GitHub issue. Contact the repository owner privately and provide only the minimum sanitized reproduction needed.

## Application safety boundaries

- Employer-facing demo mode is read-only and hides raw private source material.
- External-system writes remain off/dry-run unless an explicitly authorized live path passes deterministic gates.
- OpenAI is a controlled reasoning layer, not a source of deterministic truth and not a direct CRM writer.
- Optional provider outages do not make the deterministic core unavailable.

See `docs/SECURITY_AND_PRIVACY.md`, `docs/GITHUB_WORKFLOW.md`, and `project/privacy_policy.yaml` for the broader application policy.
