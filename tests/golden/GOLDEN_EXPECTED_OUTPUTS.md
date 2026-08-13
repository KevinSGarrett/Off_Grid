# Golden Expected Outputs — ConstructConnect Supplied Formats

Version: `W05-2026-08-10`
Parser: `constructconnect-pdf-0.5.0`

These expectations are regression gates derived from the **two real supplied ConstructConnect PDFs**. They are not manually seeded application answers. The parser must derive them from the files on each golden test run.

> **Supported-format claim:** Validated against the supplied Project and Company report formats; architecture supports additional adapters.

## Stafford project report

The Project-format parser must produce:

- report type `PROJECT`;
- project name `Stafford Technology Campus Phases 3 & 4`;
- ConstructConnect Project ID `1007341663`;
- reported value USD `7,500,000,000` **while separately retaining the source caveat that the phase value/square footage are estimates**;
- stage `POST BID - General Contractor Award`;
- city/state `Fredericksburg, VA`;
- source signals for site work, paving, new construction and data-center construction;
- report date 2026-07-08;
- event date 2026-10-05 labeled `Actual Start Date`;
- General Contractor `EE Reed Construction - Houston (HQ)`;
- Owner `Stack Infrastructure - Denver (HQ)`;
- Developer `The Peterson Companies`;
- source history `Viewed=True`, `Currently Tracked=False`;
- field-level observations/evidence that retain source page/excerpt provenance.

Required deterministic quality findings:

1. `PROJECT_VALUE_UNCERTAINTY` — HIGH;
2. `FUTURE_ACTUAL_DATE` — HIGH;
3. `MISSING_PROJECT_GC_CONTACT` — MEDIUM;
4. `VIEWED_NOT_TRACKED` — MEDIUM.

The project-value observation must remain `LOW` confidence, `REQUIRES_REVIEW`, and `CAPPED` for later scoring. Wave 5 does **not** compute the commercial qualification score.

## EE Reed company report

The Company-format parser must produce:

- report type `COMPANY`;
- company `EE Reed Construction - Houston (HQ)`;
- ConstructConnect Company ID `1000647848`;
- source header reconciliation:
  - Planning = **6 parsed / 6 expected**;
  - Post Bid = **87 / 87**;
  - Bidding Role = **74 / 74**;
- total project-table source rows = **167**;
- contact-directory rows = **32**;
- Stafford Phases 1 & 2 on source page 4 at `$2.5B`;
- Stafford Phases 3 & 4 on source page 5 at `$7.5B`;
- source history Viewed=True / Currently Tracked=False;
- observed domains including `eereed.com`, `eereedeast.com`, and `zapalacreed.com` without automatically asserting they are the same legal entity.

Required deterministic source-quality cases include:

- exact repeated-name source rows without publishing the licensed names;
- a malformed/fuzzy spelling candidate that remains review-only;
- repeated contact associations without authority inference;
- generic `info@...` inboxes assigned to named people;
- multiple domains inside one source account.

Required quality rule codes:

- `GENERIC_CONTACT_EMAIL`;
- `POSSIBLE_DUPLICATE_CONTACT`;
- `ORGANIZATION_DOMAIN_CONFLICT`;
- `VIEWED_NOT_TRACKED`.

These findings indicate **review candidates**, not automatic person/entity merges. Entity clustering and fuzzy resolution policy remains Wave 7 work.

## Idempotency gate

Processing the identical Stafford PDF twice must result in:

- one `SourceDocument` for that hash;
- one canonical Stafford project with external ID `1007341663`;
- no second set of source observations/evidence/quality flags;
- a second pipeline run that records one duplicate prevented.

## Malformed / unsupported gate

- non-PDF bytes must raise `MalformedPDFError`;
- a readable PDF that does not match either supplied report signature must raise `UnsupportedReportError` with the supported-format wording above;
- company source reconciliation failure must not be silently treated as success.

## Sanitized fixtures

Files under `tests/golden/sanitized/` are synthetic, privacy-safe structural fixtures. They are deliberately not copies of the licensed source reports and contain no real individual contact data from EE Reed.

## Wave 6 qualification/product semantic contract

Wave 6 deliberately **does not** add an exact Stafford Commercial Fit number to the golden contract. The score must emerge from the current normalized observations and the versioned configuration.

Required scoring semantics:

- active qualification model = `qualification-2.0`; `qualification-1.0` remains an immutable historical configuration;
- confidence model = `confidence-1.0`;
- product registry = `products-1.0`;
- Commercial Fit and Data Confidence are separately computed and persisted;
- the score equals the sum of configuration-driven factor contributions and is reproducible for identical inputs/config;
- the source-caveated project value contributes zero qualification points and remains visible only as provenance-bearing context;
- removing reported value must not change the current Stafford band/action under `qualification-2.0`; this is a robustness assertion, not a fixed score assertion;
- the future `Actual Start Date` remains REVIEW/non-decision-eligible and therefore cannot add trusted-timing points;
- EXPLICIT/DERIVED/VERIFIED signals may drive deterministic qualification when eligible; INFERRED/UNKNOWN signals may not;
- KVT, KV6 and KVP receive separate applicability assessments and each remains `UNVERIFIED_APPLICABILITY` until direct product need is confirmed;
- product fit must surface missing direct-use-case evidence and must not invent product capacity/runtime/pricing/ROI/quantity/savings;
- Decision-Changing Unknowns must rank named GC project leadership, temporary lighting/power responsibility and incumbent rental supplier above exact phase value;
- Commercial Fit and Data Confidence remain independent; the deterministic action is not their product and neither is a probability.

Machine-readable semantic expectations: `tests/golden/stafford_wave06_expected.json`.

## Wave 07 semantic entity/account expectations

Machine-readable companion: `tests/golden/stafford_wave07_expected.json`.

- Stafford Phases 1 & 2 and Phases 3 & 4 remain separate canonical Project records and become members of one `Stafford Technology Campus` ProjectGroup.
- The cluster relationship is evidence-backed and `SUPPORTED`; phase values are not blindly aggregated as independent pipeline value.
- EE Reed canonical source-account label becomes `EE Reed Construction` while `EE Reed Construction - Houston (HQ)` remains an alias.
- `eereed.com` remains supported/primary; `eereedeast.com` and `zapalacreed.com` remain UNKNOWN relationship evidence.
- EE Reed source project sections remain 6 planning / 87 post-bid / 74 bidding-role, but unique canonical project count is 165 rather than 167 source rows.
- Contact recurrence is source-association evidence only and never verifies rental authority.
- Fuzzy organization/person evidence may trigger review but cannot silently merge entities.

## Wave 09 — dual commercial motion / Next Best Action

The Stafford golden workflow must now also satisfy:

- exactly two linked project motions: `CONTRACTOR` and `RENTAL_HOUSE`;
- contractor motion status `VALIDATING`;
- contractor organization is the source-backed canonical EE Reed source account;
- Doug Meadows may be the highest-priority Stafford investigation anchor but remains rental-authority `UNKNOWN` on the current evidence snapshot;
- current Stafford demand signal is derived from actual product-fit assessments and classified `INFERRED`;
- rental provider, rental branch, fleet buyer and fleet opportunity remain `UNRESOLVED` until evidence establishes them;
- current NBA is `VERIFY_SITE_EQUIPMENT_RESPONSIBILITY`;
- dependent need/provider/branch/fleet/demo actions are blocked until prerequisites are completed;
- First-Call Kit includes the required temporary-lighting/mobile-power/rental-provider/current-equipment/upcoming-need/demo-contact questions;
- base workflow run creates no commercial outcomes, external writes or outreach;
- no predictive ML is trained or claimed;
- rerunning the workflow is idempotent for motions/actions.

See `tests/golden/stafford_wave09_expected.json` for the machine-readable Wave 09 contract.
