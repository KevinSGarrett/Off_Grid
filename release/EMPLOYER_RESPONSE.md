# Off Grid Innovation USA - Commercial Intelligence Exercise

## 1. Is Stafford worth pursuing?

**It is a promising candidate that should be verified before commercial progression.** The supplied record is a large multi-phase data-center development with new construction, paving and site work, and it is already at General Contractor Award with EE Reed identified as GC. Under `qualification-2.0`, the assessment is **Promising candidate / VERIFY** with an internal deterministic ordering score of **57** and a separate **MEDIUM Data Confidence** band. Neither measure is a probability. Removing the source-reported $7.5B value leaves the same band and action because that uncertain value contributes zero qualification points, so it cannot control the disposition. KVT, KV6 and KVP each remain **UNVERIFIED_APPLICABILITY** until direct lighting or power need is confirmed.

I would automate the same judgment across hundreds of incoming detailed project records using deterministic parsing and validation, source-semantic assessment coverage, config-versioned commercial scoring, product-fit rules, project/phase clustering, and an exception queue. A generic batch triage first routes `FULL`, `PARTIAL`, `SOURCE_ONLY`, and `INSUFFICIENT` records; only legitimately `FULL` records enter qualification and deterministic ordering. The supplied files do **not** contain 165 equivalent detailed project reports: they contain one detailed Stafford project report plus EE Reed company-history data. AI can interpret unstructured narrative, but IDs, money, dates, dedupe and CRM promotion remain deterministic.

## 2. How do we get to the person who decides what gets rented?

Treat contact resolution as an evidence ladder, not an Apollo lookup. First resolve the operating EE Reed entity, then find project-associated leadership, then verify role relevance, and only then verify rental/equipment authority. Public research gives **Doug Meadows** as the strongest current Stafford-associated organizational anchor; his Stafford association and senior operational role are supported, but **rental authority remains UNKNOWN**.

The next action is direct validation: determine who controls temporary lighting/mobile power, whether that is the project team, field operations, procurement or the rental company, and which rental branch serves the site. Apollo should be used after ranking candidates, to enrich the best few rather than enriching a large noisy list.

## 3. What stands out in the EE Reed file?

- It is not a clean account object. The record mixes multiple domains/organizational signals and should not be copied directly into CRM.
- It reports **6 planning, 0 bidding, 87 post-bid and 74 bidding-role rows**. “Bidding Projects” and “Bidding Role Projects” are different source fields, not contradictory counts.
- The company report contains **167 source project rows resolved to 165 canonical history projects**. They mix historical, current and undated activity and are not 165 active leads, equally detailed opportunities or completed qualifications.
- Its contact directory contains **32 source rows**. That directory and the six Stafford-specific public-research candidates are parallel evidence streams; one is not a 32-to-6 filtering funnel.
- Stafford appears across multiple phases, so project/phase clustering is required to avoid double-counting a campus as unrelated pipeline.
- Contacts include duplicates/malformed names (for example Curtis/Curits Rakosi), repeated records, generic `info@` inboxes attached to named people, and missing role context.
- A contact marked "Active" does not mean that person works on Stafford or controls rentals.
- The source was viewed but not currently tracked - a small example of the exact discovery-to-workflow gap the automation should eliminate.

## 4. Where does the pipeline break, and what would I not trust?

The biggest failure mode is automating ambiguous data into Pipedrive faster. I would not trust the $7.5B as a confirmed Phase 3/4 construction cost because the record itself says value/square footage are estimated from the broader development. I would also flag the October 5, 2026 start date being labeled "Actual Start Date" in a July 8 report, the Houston-HQ GC attribution on a Virginia project, generic/duplicate contact data, and any unverified claim about who owns rental decisions.

Operationally, unsafe records go to **quarantine / review / remediation / retry** rather than silently progressing.

## 5. Monday morning - one number

**System-sourced demos booked - rolling 30 days.** That is the business outcome the pipeline exists to produce. Under it I would keep diagnostics for projects qualified, contacts verified, CRM-ready leads, replies and demos. In this interview environment the KPI is correctly displayed as **N/A** because production outcome history is not connected.

## 6. First two weeks

Selling and learning begin in Week 1: targeted calls are part of verification and data acquisition while the system is improved in parallel. No new paid software is required initially.

**Days 1-2:** inspect the current ConstructConnect workflow and Apollo/Pipedrive fields, observe the manual copy/paste process, agree current qualification criteria, and speak directly with users and commercial contacts. Determine who actually owns temporary-equipment/rental decisions, validate the contractor/rental-house path, and agree the KPI and operating feedback loop before automating it.

**Days 3-4:** establish canonical project/company/contact identities and dedupe rules; use early conversations to test responsibility assumptions.

**Days 5-6:** automate ConstructConnect ingestion, validation, qualification and exception handling.

**Days 7-8:** implement Apollo search -> rank -> enrich and human verification.

**Days 9-10:** add idempotent Pipedrive organization/person/lead sync with deal-readiness gates.

**Days 11-12:** connect reporting/feedback and exception handoffs into existing Google/Trello workflows.

**Days 13-14:** validate on live history, instrument the funnel, document runbooks, and establish the feedback loop needed to recalibrate scoring from real outcomes.

**Bottom line:** Stafford is a promising candidate for targeted verification because of its project characteristics and stage, not because a $7.5B field looks impressive. Product need and rental authority remain unconfirmed. The system preserves those distinctions all the way from source evidence to the next sales action.

## Questions for Ash

- Where does the rental decision usually sit on a successful project: project team, procurement/equipment, rental branch, regional fleet, or a combination?
- What has been different about demos that turned into fleet purchases versus demos that went nowhere?
- Which bottleneck costs the most today: finding projects early, finding the right human, getting a response, or getting equipment placed through the rental channel?
- If this hire is working exceptionally well 90 days in, which number or behavior in the business should have changed?
