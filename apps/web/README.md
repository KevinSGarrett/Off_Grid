# Employer-facing web application

The responsive React application is driven by `/api/v1`. It discovers the Stafford golden path by ConstructConnect project ID `1007341663`, loads backend assessment, evidence, account, contact, commercial, and CRM state, and never reimplements scoring, verification, or CRM-readiness rules in browser code.

Included experiences: a six-step Guided CEO Review, Command Center, Stafford Project Intelligence, EE Reed Account Intelligence, Contact Resolution and First-Call Kit, Evidence & Trust, Product Fit, Exception Queue, CRM Preview, contractor/rental-house Commercial Motion, Commercial Analyst, Monday Morning Brief, and the First 14 Days roadmap. Each destination is URL-addressable through a hash route and uses current API responses.

The employer UI is read-only by design. It does not expose raw private PDFs, private server paths, secrets, unnecessary unmasked PII, or a live external-write control. `DEMO_MODE` and write gates remain server-side authorities.

Use `npm ci && npm run typecheck && npm run build` for a clean production build. The responsive shell keeps a full sidebar on wide screens, a visible navigation rail on compact desktop widths, and a keyboard-accessible drawer with an always-visible menu control on mobile. Browser zoom is not used as a breakpoint workaround.
