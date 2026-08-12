# Application Area

The runnable product is split into `apps/api` and `apps/web`:

- `apps/api` is the FastAPI modular-monolith backend for ingestion, evidence, trust, qualification, contact resolution, commercial workflow, CRM preview, metrics, and the bounded Commercial Analyst.
- `apps/web` is the React/TypeScript/Vite employer interface containing the 13 reference-aligned application views.

Business logic remains separated from HTTP and UI layers. Deterministic identity, scoring, provenance, verification, and workflow gates continue to operate when OpenAI or external integrations are disabled or unavailable.

For the supported clean local path, run the repository-level Docker instructions in `README.md`. Backend-only development commands are documented in `apps/api/README.md`.
