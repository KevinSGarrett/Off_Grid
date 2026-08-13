# Off Grid FastAPI application

This is the implemented backend for the Off Grid Commercial Intelligence Engine. It contains the relational persistence and migration path, deterministic ingestion and scoring, source evidence and trust controls, account/contact resolution, commercial workflow, CRM preview/safety gates, operational metrics, and optional server-side OpenAI analysis.

Run after installing Python dependencies:

```bash
PYTHONPATH=apps/api uvicorn app.main:app --reload
```

The application mounts all routes under `/api/v1`, including:

- platform health and readiness;
- ingestion, projects, organizations, evidence, quality, assessment, and sensitivity;
- contacts and verification;
- exceptions, actions, commercial motions, pipeline runs, outcomes, metrics, and Monday Brief;
- CRM readiness, preview, and deterministically gated sync;
- Commercial Analyst queries and executive-brief generation.

Health, the employer-demo dashboard, and demo-safe read APIs are publicly viewable without login. External writes remain off or dry-run unless their deterministic authorization gates explicitly permit them; OpenAI failure or disablement falls back without disabling the deterministic core.
