<div align="center">
  <img src="assets/readme/hero.svg" width="100%" alt="Off Grid Commercial Intelligence Engine — from construction data to qualified commercial action" />
</div>

<br />

<div align="center">
  <a href="#the-golden-path-stafford-technology-campus"><img src="assets/readme/button-golden-path.svg" width="230" alt="Explore the Golden Path" /></a>
  <a href="#commercial-fit-and-data-confidence"><img src="assets/readme/button-decision-logic.svg" width="230" alt="See the Decision Logic" /></a>
  <a href="#run-the-engine"><img src="assets/readme/button-run.svg" width="230" alt="Run the Engine" /></a>
  <a href="#architecture"><img src="assets/readme/button-architecture.svg" width="230" alt="Inspect the Architecture" /></a>
</div>

<br />

> **This is not a lead scraper with an AI summary attached.** It is an evidence-aware commercial decision system that knows the difference between *interesting*, *trustworthy*, and *ready to act on*.

## The question behind the project

How do you take a messy construction record and turn it into an opportunity that a salesperson can actually trust and act on?

Off Grid's commercial workflow spans ConstructConnect, Apollo, Pipedrive, Google Sheets/Forms, and Trello. Connecting those systems is the easy part. The hard part is deciding:

- which projects matter;
- whether the underlying evidence deserves trust;
- which company and person are actually relevant;
- which Off Grid product could fit the work;
- what must be verified next; and
- when the opportunity is clean enough to enter the CRM.

The **Off Grid Commercial Intelligence Engine** is a production-oriented proof of concept for that workflow, built for the **Off Grid Innovation USA interview project**.

<table>
  <tr>
    <td width="25%"><strong>INPUT</strong><br /><sub>Construction-project and company records</sub></td>
    <td width="25%"><strong>JUDGMENT</strong><br /><sub>Trust, qualification, fit, identity, authority</sub></td>
    <td width="25%"><strong>ACTION</strong><br /><sub>Next best action and CRM readiness</sub></td>
    <td width="25%"><strong>OUTCOME</strong><br /><sub>Evidence-backed commercial motion</sub></td>
  </tr>
</table>

## From source record to commercial action

<div align="center">
  <img src="assets/readme/pipeline.svg" width="100%" alt="Off Grid evidence-aware commercial pipeline" />
</div>

The application never assumes that parsed source data is automatically true. Every important field or conclusion retains a treatment:

| Treatment | What it means | What the system may do |
|---|---|---|
| **Explicit** | The source directly states it | Preserve it with provenance |
| **Derived** | Deterministic logic can reproduce it | Use it under versioned rules |
| **Inferred** | Commercial reasoning suggests it | Explain it; require evidence-aware handling |
| **Questionable** | The source conflicts with itself or reality | Cap, warn, route, or block |
| **Unknown** | The evidence is not there yet | Keep it unknown and generate the next verification step |

That distinction drives the architecture: **bad source data should not become bad CRM data faster.**

## The golden path: Stafford Technology Campus

The supplied **Stafford Technology Campus Phases 3 & 4** record is the primary end-to-end case.

At first glance, it looks like an obvious opportunity: data-center construction, site work, paving, a general contractor award, EE Reed involvement, multiple phases, and a reported value of **$7.5B**.

That last number is exactly the kind of field an automated sales system should not trust blindly. The source itself says the value and square footage reflect the larger development and that phase-level costs are not publicly confirmed.

| Field | Evidence-aware treatment |
|---|---|
| Reported value | `$7.5B` retained as source-reported data |
| Source | ConstructConnect |
| Evidence class | Explicit |
| Confidence | Low |
| Scoring treatment | Capped |
| Commercial conclusion | **PURSUE / VERIFY** |

<a id="commercial-fit-and-data-confidence"></a>

### Commercial fit ≠ data confidence

<div align="center">
  <img src="assets/readme/decision-model.svg" width="100%" alt="Commercial Fit and Data Confidence are separate dimensions" />
</div>

Stafford can be commercially attractive while some of its inputs remain unreliable. The current golden result makes that separation visible:

- **Commercial Fit:** `80 / 100`
- **Data Confidence:** `69.25 / 100`
- **Without the reported $7.5B value:** `75 / 100 — PURSUE`
- **CRM state:** `Lead-ready / Deal-blocked`

There is no single unexplained “AI score.” The platform evaluates separate dimensions for commercial fit, data confidence, KVT/KV6/KVP product fit, contact confidence, and CRM readiness.

### It can challenge its own recommendation

The application can ask a counterfactual question:

> Would Stafford still be worth pursuing if the reported value were completely wrong?

The backend recalculates the recommendation without that input and shows whether the decision changes. The same mechanism powers **Challenge This Recommendation**, where assumptions can be pressure-tested without rewriting application code.

The goal is not merely to produce a score. It is to show **what drives the score** and identify the unknowns most likely to change it:

- Who controls temporary lighting and portable power?
- Has relevant equipment already been committed elsewhere?
- Which rental company serves the project?
- What work is actually underway?
- Does the site create meaningful KVT, KV6, or KVP demand?

## What the EE Reed record reveals

The supplied **EE Reed Construction — Houston (HQ)** record demonstrates why CRM automation needs a data-quality layer. It contains useful account and project intelligence, but also repeated contacts, likely name variants, generic inboxes attached to people, multiple domains, mixed historical/current projects, and limited project-specific role evidence.

Rather than copying those rows into Pipedrive, the engine surfaces the problems first. It also recognizes related phases without automatically double-counting them:

```text
Stafford Technology Campus
├── Phases 1 & 2
└── Phases 3 & 4
```

That preserves a more useful commercial insight: the account relationship may extend beyond one isolated project record.

## Finding the right person is a verification problem

A contact database can find people. It cannot prove who controls lighting or equipment rental on a particular site.

```text
Discovered
    ↓
Employment Verified
    ↓
Project Association Verified
    ↓
Role Relevant
    ↓
Authority Verified
```

Those states are intentionally separate. A person may be a strong project contact without being the final rental decision-maker. If the evidence stops there, the system says so and produces the questions required to close the gap.

> Sometimes the correct next automation step is a phone call. The engine is designed to recognize that.

## One project, two commercial motions

<div align="center">
  <img src="assets/readme/commercial-motions.svg" width="100%" alt="Off Grid contractor-demand and rental-house commercial motions" />
</div>

Off Grid has two connected audiences:

1. **Contractor demand motion** — move from a live project to the people who experience the site need and can request a demonstration.
2. **Rental-house / fleet motion** — translate demonstrated contractor demand into a partner, branch, fleet, demo, or channel-sale opportunity.

The platform models both. If Stafford's rental provider is not identified, that node remains **UNRESOLVED**. The system does not invent an answer to complete the diagram.

## Where OpenAI fits—and where it does not

Deterministic software remains responsible for identity, money, dates, deduplication, provenance, workflow state, verification state, CRM identity, and CRM readiness.

OpenAI is reserved for work where semantic reasoning adds value:

- understanding construction descriptions;
- extracting commercial signals;
- evidence-grounded product reasoning;
- explaining data-quality problems;
- reasoning about contact candidates;
- composing next-best-action explanations;
- executive summaries and natural-language analysis.

```text
Deterministic software + OpenAI reasoning
                    ↓
                 Evidence
                    ↓
           Grounding validation
                    ↓
          Commercial recommendation
```

AI-generated factual claims must point back to evidence already available to the system. Unsupported claims are rejected instead of promoted into company data. The deterministic core remains usable when OpenAI is disabled, unavailable, or budget-blocked.

<details>
<summary><strong>Ask Off Grid Intelligence</strong></summary>

The Commercial Analyst operates over current application state rather than conversational memory. It can answer questions such as:

- Why should we pursue Stafford?
- What data should I not trust?
- Would the recommendation change without the $7.5B value?
- Which product appears to fit best?
- Who should we investigate next?
- What prevents this opportunity from entering Pipedrive?
- What should I ask on the first call?

Controlled application tools retrieve the project, evidence, quality flags, scores, contacts, exceptions, and CRM state used to compose the answer.

</details>

## Keeping Pipedrive clean

```text
Raw intelligence → Qualified opportunity → Entity resolution
      → Contact resolution → CRM readiness → Pipedrive Lead
      → Commercial validation → Pipedrive Deal
```

Finding a project does not automatically create a Deal. External adapters default to safe modes:

```dotenv
PIPEDRIVE_MODE=dry_run
APOLLO_MODE=off
DEMO_MODE=true
```

The demo can show the object or payload the platform *would* create without requiring access to production systems or performing a consequential write.

## Built for repeated processing

```text
Input → Hash → Detect format → Extract → Normalize → Validate
      → Deduplicate → Score → Resolve → Prioritize → Act
```

Reprocessing the same ConstructConnect record does not create duplicate opportunities. When the source changes, the engine records what changed and can rerun the affected commercial logic. Examples include a GC award, stage change, date change, project-value change, contact discovery, cancellation, or new phase.

A clearly labeled synthetic portfolio supports volume demonstrations without pretending synthetic projects are real evidence.

## When automation should stop

Bad or ambiguous records enter an **Exception Queue** instead of quietly continuing:

| Severity | Example | Treatment |
|---|---|---|
| `CRITICAL` | Parser reconciliation failure | Stop and escalate |
| `HIGH` | Future date labeled “Actual” | Verify before progression |
| `HIGH` | Project-value uncertainty | Cap influence and surface warning |
| `HIGH` | Ambiguous organization match | Require human resolution |
| `MEDIUM` | Possible duplicate contact | Review before merge |
| `MEDIUM` | Generic email | Preserve but do not overstate identity |

Exceptions can be verified, corrected, deferred, retried, or escalated. Uncertainty has somewhere explicit to go.

## The Monday-morning number

The intended production KPI is:

> **System-Sourced Demos Booked — Rolling 30 Days**

Projects ingested, qualified records, verified contacts, CRM-ready opportunities, and engagement are diagnostics—not substitutes for a commercial outcome. Because the interview environment contains no Off Grid production sales history, the KPI is displayed as **N/A** instead of invented.

## Guided interview review

The application includes a concise guided review around the original assignment:

1. Is Stafford worth pursuing?
2. Who should we contact?
3. What stands out in the EE Reed record?
4. Where does the pipeline break?
5. What belongs on Monday morning?
6. What would the first two weeks look like?

The aim is to make the value legible in a few minutes, while keeping the complete evidence and technical system available for deeper inspection.

## Architecture

<div align="center">
  <img src="assets/readme/architecture.svg" width="100%" alt="Off Grid application architecture" />
</div>

The interview implementation deliberately stays compact: one React frontend, one FastAPI backend, and one relational database. Complexity lives in the commercial rules and evidence boundaries—not unnecessary infrastructure.

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite |
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Data | SQLite demo runtime with portable relational models |
| Document processing | PyMuPDF, pdfplumber |
| Entity resolution | Deterministic normalization + RapidFuzz-assisted ambiguous matching |
| AI | Optional OpenAI Responses API, structured outputs, controlled tools, grounding |
| Quality | pytest golden, unit, integration, contract, failure, load, and end-to-end lanes |
| Delivery | Multi-stage Docker, GitHub Actions, AWS CloudFormation/ECS Express Mode definitions |

## Run the engine

### Docker — fastest path

```bash
git clone https://github.com/KevinSGarrett/Off_Grid.git
cd Off_Grid

docker build -t offgrid-commercial-intelligence:local .
docker run --rm -p 8080:8000 \
  -e REQUIRE_ACCESS_CONTROL=true \
  -e APP_ACCESS_PASSWORD='replace-with-a-strong-local-password' \
  offgrid-commercial-intelligence:local
```

Then open `http://localhost:8080` and verify `http://localhost:8080/api/v1/health`.

The username may be any non-empty value; the password is the value supplied through `APP_ACCESS_PASSWORD`. The container restores its writable database from the sanitized demo seed at startup. Raw licensed PDFs are not present in Git or in the image.

### Developer workflow

Requirements: Python 3.12, Node.js 22, npm, and Docker.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts\run_public_test_matrix.py

npm --prefix apps/web ci --no-audit --no-fund
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

The deterministic core works without OpenAI, Apollo, or Pipedrive credentials. Optional integrations are enabled explicitly through environment configuration.

## Repository map

```text
apps/api/           FastAPI application, domain services, migrations
apps/web/           React + TypeScript employer/analyst interface
config/             Versioned qualification, trust, product and workflow rules
prompts/            Versioned, evidence-aware OpenAI prompts
data/demo_seed/     Sanitized deterministic demo database
tests/              Golden, unit, integration, contract, failure and E2E tests
scripts/            Public validation, reset, scoring and privacy tools
infra/aws/          ECR, ECS Express Mode, Secrets Manager and OIDC templates
```

## Design principles

> **Parsed does not mean trusted.**<br />
> **A likely contact is not a verified decision-maker.**<br />
> **Commercial fit and data confidence are not the same thing.**<br />
> **AI may reason and explain; it may not quietly redefine company facts.**<br />
> **Unknown is better than fabricated certainty.**<br />
> **Bad source data should not become bad CRM data faster.**

The system only matters if it helps create real, defensible commercial outcomes.

## Privacy and safety

This public repository contains the sanitized release boundary. Licensed source PDFs, original chat logs, credentials, private research continuity, local Jira and control records, and unnecessary PII remain excluded by policy and validators. The demo database is a minimized derivative snapshot—not a copy of raw documents.

See [SECURITY.md](SECURITY.md) for disclosure and data-handling rules and [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow.

---

<div align="center">
  <strong>Kevin Garrett</strong><br />
  <sub>AI Solutions Architect · Applied AI & ML/LLM Engineering · Systems & Cloud Architecture</sub><br /><br />
  <a href="https://github.com/KevinSGarrett">GitHub profile</a>
  &nbsp;·&nbsp;
  Built for the Off Grid Innovation USA technical interview
</div>
