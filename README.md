<div align="center">
  <img src="assets/readme/hero.svg" width="100%" alt="Off Grid Commercial Intelligence Engine" />
</div>

<p align="center">
  <a href="#02--the-golden-path"><img alt="Stafford: Pursue and Verify" src="https://img.shields.io/badge/STAFFORD-PURSUE%20%2F%20VERIFY-18a558?style=for-the-badge&amp;labelColor=081b12" /></a>
  <a href="#evidence-is-a-first-class-type"><img alt="Evidence grounded" src="https://img.shields.io/badge/EVIDENCE-GROUNDED-25c46a?style=for-the-badge&amp;labelColor=081b12" /></a>
  <a href="#crm-readiness-not-crm-noise"><img alt="CRM mode: dry run" src="https://img.shields.io/badge/CRM-DRY%20RUN-f0ad38?style=for-the-badge&amp;labelColor=081b12" /></a>
  <a href="#07--run-the-engine"><img alt="Run locally with Docker" src="https://img.shields.io/badge/DOCKER-RUN%20LOCALLY-2496ed?style=for-the-badge&amp;labelColor=081b12&amp;logo=docker&amp;logoColor=white" /></a>
  <a href="#where-openai-fits"><img alt="OpenAI is optional" src="https://img.shields.io/badge/OPENAI-OPTIONAL-7c5ce7?style=for-the-badge&amp;labelColor=081b12&amp;logo=openai&amp;logoColor=white" /></a>
</p>

<p align="center">
  <strong>Turning construction-project data into qualified commercial action.</strong><br />
  <sub>Evidence-aware qualification · conservative identity resolution · explainable next action</sub>
</p>

---

## Why this exists

I built this project around one practical question:

> **How do you turn a messy construction record into an opportunity a salesperson can trust and act on?**

Off Grid's workflow spans ConstructConnect, Apollo, Pipedrive, Google Sheets/Forms, and Trello. Connecting those tools is not the hard part. The hard part is deciding what matters, what is trustworthy, who is relevant, what Off Grid could sell, and whether the record is clean enough to enter the CRM.

The **Off Grid Commercial Intelligence Engine** is a production-oriented proof of concept for that decision layer, built for the **Off Grid Innovation USA interview project**.

| The engine receives | The engine decides | The engine produces |
|---|---|---|
| Project and company records | Trust, fit, identity, authority, readiness | Evidence-backed next action |
| Conflicting or incomplete fields | What to accept, cap, verify, or block | A clean CRM preview |
| Commercial signals | Which unknowns matter most | Contractor and rental-house motion |

---

## 01 — How the engine thinks

<div align="center">
  <img src="assets/readme/pipeline.svg" width="100%" alt="Source data moves through trust, qualification, resolution, action and CRM readiness" />
</div>

The application never assumes that parsed source data is automatically true. Every important field or conclusion retains an evidence treatment.

<a id="evidence-is-a-first-class-type"></a>

### Evidence is a first-class type

| Treatment | Meaning | Allowed behavior |
|---|---|---|
| **Explicit** | The source directly states it | Preserve with provenance |
| **Derived** | Deterministic logic can reproduce it | Use under versioned rules |
| **Inferred** | Commercial reasoning suggests it | Explain and verify |
| **Questionable** | The source conflicts with itself or reality | Cap, warn, route, or block |
| **Unknown** | The evidence is not there yet | Keep it unknown; generate the next step |

> **Bad source data should not become bad CRM data faster.**

---

<a id="02--the-golden-path"></a>

## 02 — The golden path

### Stafford Technology Campus

The supplied **Stafford Technology Campus Phases 3 & 4** record is the primary end-to-end case. It contains strong commercial signals—data-center construction, site work, paving, a general contractor award, EE Reed involvement, and multiple phases—but it also reports a **$7.5B** value that should not be trusted blindly.

The source says the value and square footage reflect the larger development and that phase-level costs are not publicly confirmed. The system keeps the source value without letting it dominate the decision.

| Reported fact | Decision treatment |
|---|---|
| `$7.5B` reported value | Retained with provenance |
| ConstructConnect source | Explicit evidence |
| Phase-level confidence | Low |
| Scoring influence | Capped |
| Recommendation | **PURSUE / VERIFY** |

<a id="commercial-fit-and-data-confidence"></a>

### Commercial fit and data confidence are different questions

<div align="center">
  <img src="assets/readme/decision-model.svg" width="100%" alt="Commercial Fit and Data Confidence remain separate dimensions" />
</div>

| Current golden result | Value |
|---|---:|
| Commercial Fit | `80 / 100` |
| Data Confidence | `69.25 / 100` |
| Without the reported `$7.5B` | `75 / 100 — PURSUE` |
| CRM state | `Lead-ready / Deal-blocked` |

There is no single unexplained “AI score.” Commercial fit, data confidence, product fit, contact confidence, and CRM readiness remain independently inspectable.

<details>
<summary><strong>Challenge the recommendation</strong></summary>

The backend can remove the reported value from scoring and recalculate the recommendation. That answers a useful counterfactual:

> Would Stafford still be worth pursuing if the $7.5B value were completely wrong?

It also identifies the unknowns most likely to change the decision:

- Who controls temporary lighting and portable power?
- Has relevant equipment already been committed elsewhere?
- Which rental company serves the project?
- What work is actually underway?
- Does the site create meaningful KVT, KV6, or KVP demand?

</details>

---

## 03 — One project, two commercial motions

<div align="center">
  <img src="assets/readme/commercial-motions.svg" width="100%" alt="Contractor-demand and rental-house fleet motions" />
</div>

1. **Contractor demand** moves from a live project to the people experiencing the site need and able to request a demonstration.
2. **Rental-house / fleet opportunity** translates demonstrated demand into a partner, branch, fleet, demo, or channel-sale opportunity.

The paths are connected, but they are not interchangeable. If Stafford's rental provider is not identified, that node remains **UNRESOLVED**. The engine does not invent an answer to complete the diagram.

<details>
<summary><strong>What the EE Reed record reveals</strong></summary>

The supplied **EE Reed Construction — Houston (HQ)** record contains valuable account intelligence alongside repeated contacts, likely name variants, generic inboxes, multiple domains, mixed historical/current projects, and limited project-specific role evidence.

Rather than copying those rows into Pipedrive, the engine surfaces the issues first. It also recognizes related phases without automatically double-counting them:

```text
Stafford Technology Campus
├── Phases 1 & 2
└── Phases 3 & 4
```

That reveals a recurring account-level opportunity without pretending each phase is an independent pipeline record.

</details>

<details>
<summary><strong>Why contact resolution is a verification ladder</strong></summary>

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

A contact database can find people. It cannot prove who controls lighting or equipment rental on a particular site. A person may be a strong project contact without being the final decision-maker. If the evidence stops there, the application says so and generates the next verification questions.

</details>

---

## 04 — Deterministic truth, optional AI

| Deterministic software owns | OpenAI may assist with |
|---|---|
| IDs, money, dates, deduplication | Understanding construction descriptions |
| Provenance and evidence state | Extracting semantic commercial signals |
| Workflow and verification state | Evidence-grounded product reasoning |
| CRM identity and readiness gates | Explanations, summaries, and analysis |

<a id="where-openai-fits"></a>

### Where OpenAI fits

```text
Deterministic software + OpenAI reasoning
                    ↓
                 Evidence
                    ↓
           Grounding validation
                    ↓
          Commercial recommendation
```

AI-generated factual claims must point back to evidence already available to the application. Unsupported claims are rejected instead of promoted into company data. The deterministic core remains usable when OpenAI is disabled, unavailable, or budget-blocked.

<details>
<summary><strong>Questions the Commercial Analyst can answer</strong></summary>

- Why should we pursue Stafford?
- What data should I not trust?
- Would the recommendation change without the `$7.5B` value?
- Which product appears to fit best?
- Who should we investigate next?
- What blocks this opportunity from entering Pipedrive?
- What should I ask on the first call?

The analyst retrieves current project, evidence, quality, scoring, contact, exception, and CRM state rather than relying on conversational memory.

</details>

---

## 05 — Where automation stops

Ambiguous records enter an **Exception Queue** instead of quietly continuing.

| Severity | Example | Treatment |
|---|---|---|
| `CRITICAL` | Parser reconciliation failure | Stop and escalate |
| `HIGH` | Future date labeled “Actual” | Verify before progression |
| `HIGH` | Project-value uncertainty | Cap influence and warn |
| `HIGH` | Ambiguous organization match | Require human resolution |
| `MEDIUM` | Possible duplicate or generic email | Review before merge |

Exceptions can be verified, corrected, deferred, retried, or escalated. Uncertainty has somewhere explicit to go.

<a id="crm-readiness-not-crm-noise"></a>

### CRM readiness, not CRM noise

```text
Raw intelligence → Qualified opportunity → Entity resolution
      → Contact resolution → CRM readiness → Pipedrive Lead
      → Commercial validation → Pipedrive Deal
```

External adapters default to safe modes:

```dotenv
PIPEDRIVE_MODE=dry_run
APOLLO_MODE=off
DEMO_MODE=true
```

Finding a project does not automatically create a Deal. The demo can show the object it *would* create without performing a consequential production write.

### The Monday-morning number

> **System-Sourced Demos Booked — Rolling 30 Days**

Projects ingested, qualified records, verified contacts, CRM-ready opportunities, and engagement are diagnostics—not substitutes for a commercial outcome. Because the interview environment contains no Off Grid production sales history, the KPI displays **N/A** instead of invented performance.

---

## 06 — Architecture

<div align="center">
  <img src="assets/readme/architecture.svg" width="100%" alt="Off Grid application architecture" />
</div>

The implementation deliberately stays compact: one React frontend, one FastAPI backend, and one relational database. Complexity lives in the commercial rules and evidence boundaries—not unnecessary infrastructure.

| Layer | Technology |
|---|---|
| Frontend | React 19 · TypeScript · Vite |
| Backend | Python 3.12 · FastAPI · Pydantic · SQLAlchemy · Alembic |
| Data | SQLite demo runtime · portable relational models |
| Documents | PyMuPDF · pdfplumber |
| Entity resolution | Deterministic normalization · RapidFuzz-assisted matching |
| AI | Optional OpenAI Responses API · structured outputs · controlled tools |
| Quality | Golden · unit · integration · contract · failure · load · E2E tests |
| Delivery | Multi-stage Docker · GitHub Actions · AWS CloudFormation/ECS definitions |

---

<a id="07--run-the-engine"></a>

## 07 — Run the engine

### Fastest path: Docker

```bash
git clone https://github.com/KevinSGarrett/Off_Grid.git
cd Off_Grid

docker build -t offgrid-commercial-intelligence:local .
docker run --rm -p 8080:8000 \
  -e REQUIRE_ACCESS_CONTROL=true \
  -e APP_ACCESS_PASSWORD='replace-with-a-strong-local-password' \
  offgrid-commercial-intelligence:local
```

Open `http://localhost:8080` and verify `http://localhost:8080/api/v1/health`.

The username may be any non-empty value; the password is the value supplied through `APP_ACCESS_PASSWORD`. The deterministic core works without OpenAI, Apollo, or Pipedrive credentials.

<details>
<summary><strong>Developer setup</strong></summary>

Requirements: Python 3.12, Node.js 22, npm, and Docker.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts\run_public_test_matrix.py

npm --prefix apps/web ci --no-audit --no-fund
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

</details>

---

## 08 — Explore the repository

```text
apps/api/           FastAPI application, domain services, migrations
apps/web/           React + TypeScript employer/analyst interface
config/             Qualification, trust, product and workflow rules
prompts/            Versioned, evidence-aware OpenAI prompts
data/demo_seed/     Sanitized deterministic demo database
tests/              Golden, unit, integration, failure and E2E tests
scripts/            Validation, reset, scoring and privacy tools
infra/aws/          ECR, ECS, Secrets Manager and OIDC templates
```

### Design rules

> **Parsed does not mean trusted.**<br />
> **A likely contact is not a verified decision-maker.**<br />
> **Commercial fit and data confidence are not the same thing.**<br />
> **AI may reason and explain; it may not quietly redefine company facts.**<br />
> **Unknown is better than fabricated certainty.**

---

<div align="center">
  <strong>Kevin Garrett</strong><br />
  <sub>AI Solutions Architect · Applied AI & ML/LLM Engineering · Systems & Cloud Architecture</sub><br /><br />
  <a href="https://github.com/KevinSGarrett">GitHub profile</a>
  &nbsp;·&nbsp;
  Built for the Off Grid Innovation USA technical interview
</div>
