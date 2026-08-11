# API Starter — Wave 03

Wave 3 establishes a runnable FastAPI boundary, pure domain state/port contracts, deterministic transition policy, and a server-side external-write gate. It intentionally does **not** fake the later PDF parser, database schema, scoring engine or integration behavior.

Run after installing Python dependencies:

```bash
PYTHONPATH=apps/api uvicorn app.main:app --reload
```

Current implemented routes are platform-only (`/api/v1/health`, `/api/v1/readiness`). Planned business routes are documented in `docs/API_SURFACE_BLUEPRINT.md` and are implemented in their owner waves.
