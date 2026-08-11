# Employer-facing web application

Wave 13 replaces the architecture shell with a responsive React employer experience driven by `/api/v1`.

The frontend discovers the Stafford golden path by ConstructConnect project ID `1007341663`, loads backend assessment/evidence/account/contact/commercial/CRM state, and never reimplements scoring, verification, or CRM-readiness rules in browser code.

Included experiences: Command Center, six-step Guided CEO Review, Stafford Project Intelligence and Product Fit, Evidence Inspector, EE Reed Account Intelligence, Contact Resolution and First-Call Kit, contractor/rental-house Commercial Motion, Exception Queue, CRM Preview, Commercial Analyst, Monday Morning Brief, Raw → Clean → Commercial-Ready comparison, interactive backend score sensitivity, and the First 14 Days roadmap.

The employer UI is read-only by design. It does not expose raw private PDFs, private server paths, secrets, unnecessary unmasked PII, or a live external-write control. `DEMO_MODE` and write gates remain server-side authorities.

With registry access, normal development is `npm install && npm run dev`. The Wave 13 execution environment could not resolve npm packages, so a final Vite bundle is not falsely claimed in this wave. The source passes an offline strict TypeScript control check using local declaration shims; clean dependency installation and Vite/React build remain a Wave 17 release gate.
