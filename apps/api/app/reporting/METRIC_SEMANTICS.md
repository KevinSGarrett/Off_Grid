# Employer-Facing Metric Semantics

The code registry in `metrics.py` is the canonical contract for employer-facing metric names, calculations, and interpretation. The `/api/v1/metrics` and `/api/v1/monday-brief` responses expose those definitions with their values; the React application uses the returned labels instead of reinterpreting raw database counts.

Key truth boundaries:

- `canonical_projects_resolved` counts non-synthetic canonical Project records. It is not the number Off Grid should pursue.
- `source_project_rows` counts retained company-report project rows before resolution. Repeated rows are not independent opportunities.
- `projects_assessed` counts non-synthetic projects with a current persisted assessment. Unassessed projects were not rejected.
- `authority_verified_contacts` requires rental/equipment authority verification. Employment and project association do not qualify.
- `crm_leads_previewed` counts dry-run Lead previews, not live Pipedrive records or outreach-ready contacts.
- `open_workflow_exceptions` excludes standalone quality warnings.
- `quality_warnings_requiring_review` counts unresolved evidence-quality findings separately.
- `recorded_commercial_outcomes` counts observed records for non-synthetic projects; zero is a data-state statement, not a performance verdict.
- the headline KPI remains N/A until outcome history is connected. Its numeric display is not inferred from pipeline activity.

Internal deterministic scores remain available for ordering and audit. The employer UI presents Commercial Fit and Data Confidence as independent bands, never as probabilities or percentages.
