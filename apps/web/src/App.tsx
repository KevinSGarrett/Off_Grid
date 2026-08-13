import {
  ArrowRight,
  BarChart3,
  Bell,
  Box,
  Building2,
  CalendarDays,
  Check,
  ChevronRight,
  CircleCheck,
  CircleHelp,
  Clock3,
  Database,
  Eye,
  FileSearch,
  Flag,
  Gauge,
  GitBranch,
  Handshake,
  Info,
  LayoutDashboard,
  Lightbulb,
  LockKeyhole,
  MapPin,
  Menu,
  MessageSquareText,
  Network,
  PackageCheck,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  TriangleAlert,
  UserRound,
  UsersRound,
  Workflow,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import {
  type FormEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ApiRequestError,
  askAnalyst,
  loadInitialApplication,
  retryOptionalDependency,
} from "./api";
import { dateStamp, money, score, titleCase } from "./format";
import type {
  AnalystResponse,
  CRMRequest,
  DashboardData,
  Evidence,
  GeneralizationData,
  MetricDefinition,
  OptionalDependencyFailure,
  OptionalDependencyKey,
  PortfolioProject,
  SourceContact,
} from "./types";

type ViewKey =
  | "guided"
  | "portfolio"
  | "source"
  | "command"
  | "project"
  | "account"
  | "contacts"
  | "evidence"
  | "product"
  | "exceptions"
  | "crm"
  | "commercial"
  | "analyst"
  | "monday"
  | "roadmap";

type NavItem = {
  key: ViewKey;
  label: string;
  group: "Data" | "Decide" | "Resolve" | "Act" | "Explain";
  icon: LucideIcon;
};

const nav: NavItem[] = [
  {
    key: "portfolio",
    label: "Project Data",
    group: "Data",
    icon: Database,
  },
  {
    key: "source",
    label: "Account / Source Data",
    group: "Data",
    icon: FileSearch,
  },
  {
    key: "command",
    label: "Command Center",
    group: "Decide",
    icon: LayoutDashboard,
  },
  {
    key: "project",
    label: "Project Intelligence",
    group: "Decide",
    icon: BarChart3,
  },
  {
    key: "account",
    label: "Account Intelligence",
    group: "Resolve",
    icon: Building2,
  },
  {
    key: "contacts",
    label: "Contact Resolution",
    group: "Resolve",
    icon: UsersRound,
  },
  {
    key: "evidence",
    label: "Evidence & Trust",
    group: "Resolve",
    icon: ShieldCheck,
  },
  { key: "product", label: "Product Fit", group: "Resolve", icon: Box },
  {
    key: "exceptions",
    label: "Exception Queue",
    group: "Act",
    icon: TriangleAlert,
  },
  { key: "crm", label: "CRM Preview", group: "Act", icon: PackageCheck },
  {
    key: "commercial",
    label: "Commercial Motion",
    group: "Act",
    icon: Workflow,
  },
  {
    key: "analyst",
    label: "Commercial Analyst",
    group: "Explain",
    icon: MessageSquareText,
  },
  {
    key: "monday",
    label: "Monday Morning Brief",
    group: "Explain",
    icon: CalendarDays,
  },
  { key: "roadmap", label: "First 14 Days", group: "Explain", icon: Flag },
];

const guided = [
  {
    q: "Question 1",
    title: "Is Stafford worth pursuing?",
    view: "project" as ViewKey,
    focus:
      "Validate commercial fit, source confidence, timing, and product relevance.",
    icon: Target,
  },
  {
    q: "Question 2",
    title: "Who should we contact?",
    view: "contacts" as ViewKey,
    focus:
      "Investigate people while keeping rental authority explicitly unverified.",
    icon: UsersRound,
  },
  {
    q: "Question 3",
    title: "What stands out in EE Reed?",
    view: "account" as ViewKey,
    focus:
      "Review recurrence, entity quality, domains, duplicates, and generic inboxes.",
    icon: Building2,
  },
  {
    q: "Question 4",
    title: "Where does the pipeline break?",
    view: "exceptions" as ViewKey,
    focus: "Surface source-quality risks and dependency-blocked progression.",
    icon: TriangleAlert,
  },
  {
    q: "Question 5",
    title: "What matters Monday morning?",
    view: "monday" as ViewKey,
    focus:
      "Lead with the intended KPI while clearly preserving the current N/A state.",
    icon: BarChart3,
  },
  {
    q: "Question 6",
    title: "What happens in the first two weeks?",
    view: "roadmap" as ViewKey,
    focus:
      "Follow a practical sequence using Off Grid's existing operating stack.",
    icon: CalendarDays,
  },
];

function tone(value: unknown) {
  const text = String(value ?? "UNKNOWN").toLowerCase();
  if (
    /verified|pursue|ready|supported|accept|excellent|good/.test(text) &&
    !/unverified|unknown|not|blocked/.test(text)
  )
    return "good";
  if (/blocked|critical|failed|conflicted|error/.test(text)) return "bad";
  if (
    /unknown|verify|review|medium|inferred|preview|low|warning|partial/.test(
      text,
    )
  )
    return "warn";
  return "neutral";
}

function scoreBand(value: unknown) {
  const n = Number(value) || 0;
  if (n >= 80) return "Strong";
  if (n >= 60) return "Moderate";
  return "Needs review";
}

function relevanceIndex(value: unknown): string {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? String(Math.round(numeric)) : "N/A";
}

function relevanceBand(value: unknown): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return "Not indicated";
  if (numeric >= 70) return "Strong context";
  if (numeric >= 45) return "Moderate context";
  return "Limited context";
}

function pillText(value: unknown): string {
  if (Array.isArray(value)) return value.map(pillText).join("");
  return String(value ?? "");
}

function primaryRelationship(project: PortfolioProject) {
  return project.relationships.find((item) => /general contractor/i.test(item.role)) || project.relationships[0];
}

function Pill({ children }: { children: unknown }) {
  const text = pillText(children);
  return <span className={`pill ${tone(text)}`}>{titleCase(text)}</span>;
}

function Logo() {
  return (
    <div className="logo" aria-label="Off Grid Commercial Intelligence">
      <span className="logo-mark">
        <i />
      </span>
      <span className="logo-copy">
        <b>OFF GRID</b>
        <small>Commercial Intelligence</small>
      </span>
    </div>
  );
}

function PageHeader({
  eyebrow,
  title,
  subtitle,
  d,
  actions,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  d?: DashboardData;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="page-heading">
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {d && (
        <div className="project-facts" aria-label="Project context">
          <span>
            <MapPin size={14} />
            {d.project.city}, {d.project.region}
          </span>
          <span>
            <b>ID</b>
            {d.project.external_id}
          </span>
          <span>
            <b>Stage</b>
            {titleCase(d.project.stage)}
          </span>
          <Pill>
            {d.assessment.assessment.overall_band} ·{" "}
            {d.assessment.assessment.operational_action}
          </Pill>
        </div>
      )}
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

function SectionHead({
  eyebrow,
  title,
  aside,
  icon: Icon,
}: {
  eyebrow?: string;
  title: string;
  aside?: string;
  icon?: LucideIcon;
}) {
  return (
    <header className="section-head">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h2>
          {Icon && <Icon size={18} />}
          {title}
        </h2>
      </div>
      {aside && <p className="aside">{aside}</p>}
    </header>
  );
}

function Metric({
  label,
  value,
  note,
  icon: Icon,
  kind = "good",
}: {
  label: string;
  value: unknown;
  note?: string;
  icon?: LucideIcon;
  kind?: "good" | "warn" | "bad";
}) {
  return (
    <article className={`metric ${kind}`}>
      <div className="metric-icon">{Icon && <Icon size={20} />}</div>
      <div>
        <span>{label}</span>
        <strong>{String(value)}</strong>
        {note && <small>{note}</small>}
      </div>
    </article>
  );
}

function metricLabel(
  definitions: Record<string, MetricDefinition> | undefined,
  key: string,
) {
  return definitions?.[key]?.label || titleCase(key);
}

function DecisionCard({
  label,
  value,
  note,
  icon: Icon,
  action,
}: {
  label: string;
  value: unknown;
  note: string;
  icon?: LucideIcon;
  action?: unknown;
}) {
  return (
    <article className="score-card decision-card">
      <div className="score-top">
        <span className="score-icon warn">{Icon && <Icon size={23} />}</span>
        <div>
          <span>{label}</span>
          <strong>{String(value)}</strong>
        </div>
        {action !== undefined && action !== null && <Pill>{action}</Pill>}
      </div>
      <small>{note}</small>
    </article>
  );
}

function Empty({
  title,
  detail,
  kind = "warn",
}: {
  title: string;
  detail: string;
  kind?: "warn" | "bad";
}) {
  const Icon = kind === "bad" ? TriangleAlert : Info;
  return (
    <div className={`empty-state ${kind}`}>
      <Icon size={20} />
      <div>
        <b>{title}</b>
        <p>{detail}</p>
      </div>
    </div>
  );
}

function DegradedPanel({
  failure,
  retry,
  retrying,
}: {
  failure: OptionalDependencyFailure;
  retry: (key: OptionalDependencyKey) => void;
  retrying: boolean;
}) {
  return (
    <div className="degraded-panel" role="status">
      <span className="degraded-icon">
        <TriangleAlert />
      </span>
      <div>
        <p className="eyebrow">Optional service unavailable</p>
        <h2>{failure.label}</h2>
        <p>{failure.message}</p>
        {failure.request_id && <small>Request ID: {failure.request_id}</small>}
      </div>
      <button
        className="button secondary"
        onClick={() => retry(failure.key)}
        disabled={retrying}
      >
        {retrying ? <RefreshCw className="spin" /> : <RefreshCw />}
        {retrying ? "Retrying…" : "Retry"}
      </button>
    </div>
  );
}

function failureFor(
  d: DashboardData,
  key: OptionalDependencyKey,
  label: string,
): OptionalDependencyFailure {
  return (
    d.optionalFailures[key] || {
      key,
      label,
      status: null,
      request_id: null,
      message: `${label} is temporarily unavailable. Core intelligence remains available.`,
    }
  );
}

function evidenceFor(d: DashboardData, key: string) {
  return (
    d.evidence.find((item) => item.field_name === key) ||
    d.evidence.find((item) => item.field_name.includes(key))
  );
}

function rationale(value: unknown) {
  if (!value) return "No rationale stored.";
  try {
    const parsed = JSON.parse(String(value));
    return `${parsed.public_role_label ?? "Role under investigation"}. ${parsed.warning ?? "Ranking does not prove authority."}`;
  } catch {
    return String(value);
  }
}

function stringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).filter(Boolean);
  if (typeof value !== "string" || !value.trim()) return [];
  try {
    const parsed = JSON.parse(value);
    if (Array.isArray(parsed)) return parsed.map(String).filter(Boolean);
  } catch {
    // The API also returns newline-delimited evidence requirements.
  }
  return value
    .split(/\r?\n|\s+·\s+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function EvidenceDrawer({
  item,
  close,
}: {
  item: Evidence;
  close: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);
  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={close}>
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button
          ref={closeRef}
          className="icon-button drawer-close"
          onClick={close}
          aria-label="Close evidence inspector"
        >
          <X size={19} />
        </button>
        <p className="eyebrow">Evidence Inspector</p>
        <h2 id="evidence-title">{titleCase(item.field_name)}</h2>
        <div className="pill-row">
          <Pill>{item.classification}</Pill>
          <Pill>{item.confidence_state}</Pill>
          <Pill>{item.scoring_treatment}</Pill>
        </div>
        <dl className="detail-grid">
          <div>
            <dt>Evidence ID</dt>
            <dd>{item.evidence_id}</dd>
          </div>
          <div>
            <dt>Page</dt>
            <dd>{item.page_number ?? "Unknown"}</dd>
          </div>
          <div>
            <dt>Section</dt>
            <dd>{item.section_name ?? "Unknown"}</dd>
          </div>
          <div>
            <dt>Validation</dt>
            <dd>{titleCase(item.validation_state)}</dd>
          </div>
        </dl>
        <span className="label">Demo-safe source excerpt</span>
        <blockquote>{item.excerpt || "No excerpt available."}</blockquote>
        <div className="privacy-note">
          <LockKeyhole size={16} />
          <span>
            Raw private documents and server paths are never exposed here.
          </span>
        </div>
      </aside>
    </div>
  );
}

function GuidedReview({
  d,
  start,
  setView,
}: {
  d: DashboardData;
  start: () => void;
  setView: (view: ViewKey) => void;
}) {
  const assessment = d.assessment.assessment;
  const warnings = d.quality.slice(0, 3);
  return (
    <div className="page guided-page" data-view="guided">
      <section className="guided-hero">
        <div className="guided-copy">
          <p className="eyebrow">Guided CEO Review</p>
          <h1>Make smarter go/no-go decisions. Faster.</h1>
          <p>
            Walk through six employer questions and see the evidence-backed
            workflow built from the current Stafford and EE Reed records.
          </p>
          <button className="button primary large" onClick={start}>
            <ArrowRight size={21} />
            Start guided review <small>3–5 minute walkthrough</small>
          </button>
        </div>
        <article className="opportunity-card">
          <div className="location">
            <MapPin size={15} />
            {d.project.city}, {d.project.region}
          </div>
          <h2>{d.project.canonical_name}</h2>
          <div className="recommendation">
            <span>Deterministic recommendation</span>
            <strong>
              {assessment.overall_band} · {assessment.operational_action}
            </strong>
          </div>
          <div className="score-triplet">
            <div>
              <Target />
              <span>Commercial Fit</span>
              <b>{assessment.overall_band}</b>
            </div>
            <div>
              <ShieldCheck />
              <span>Data Confidence</span>
              <b>{titleCase(assessment.confidence_state)}</b>
            </div>
            <div>
              <Eye />
              <span>Evidence Records</span>
              <b>{d.evidence.length}</b>
            </div>
          </div>
          <p className="assessment-disclaimer">
            Decision support only—not a success probability, forecast, or
            verified demand.
          </p>
          <div className="warning-list">
            <b>{warnings.length} trust warnings</b>
            {warnings.map((warning: any) => (
              <button key={warning.id} onClick={() => setView("evidence")}>
                <TriangleAlert size={14} />
                <span>{warning.title}</span>
                <ChevronRight size={14} />
              </button>
            ))}
          </div>
        </article>
      </section>
      <section
        className="guided-questions"
        aria-label="Guided review questions"
      >
        {guided.map((step, index) => {
          const Icon = step.icon;
          return (
            <button key={step.q} onClick={() => setView(step.view)}>
              <span className="step-number">{index + 1}</span>
              <Icon size={22} />
              <b>{step.title}</b>
              <p>{step.focus}</p>
              <span className="start-link">
                Start <ArrowRight size={15} />
              </span>
            </button>
          );
        })}
      </section>
      <section className="shortcut-grid">
        {[
          [
            BarChart3,
            "Project Intelligence",
            "Inspect qualification, trust, and sensitivity.",
            "project",
          ],
          [
            UsersRound,
            "Contact Resolution",
            "Review evidence-supported investigation priorities.",
            "contacts",
          ],
          [
            PackageCheck,
            "CRM Preview",
            "See why Lead and Deal gates remain separate.",
            "crm",
          ],
          [
            MessageSquareText,
            "Commercial Analyst",
            "Ask grounded questions without enabling writes.",
            "analyst",
          ],
        ].map(([Icon, label, copy, key]) => (
          <button key={String(key)} onClick={() => setView(key as ViewKey)}>
            <Icon size={24} />
            <div>
              <b>{String(label)}</b>
              <p>{String(copy)}</p>
            </div>
            <ArrowRight size={17} />
          </button>
        ))}
      </section>
    </div>
  );
}

function CommandCenter({
  d,
  setView,
  retry,
  retrying,
}: {
  d: DashboardData;
  setView: (view: ViewKey) => void;
  retry: (key: OptionalDependencyKey) => void;
  retrying: OptionalDependencyKey | null;
}) {
  const a = d.assessment.assessment;
  const metrics = d.metrics;
  const diagnosticEntries = metrics
    ? Object.entries(metrics.diagnostics).map(([key, value]) => ({
        key,
        value: Number(value) || 0,
      }))
    : [];
  const maxDiagnosticValue = Math.max(
    1,
    ...diagnosticEntries.map((item) => item.value),
  );
  const action =
    d.actions.items.find((item: any) => item.status === "OPEN") ||
    d.actions.items[0];
  return (
    <div className="page" data-view="command">
      <PageHeader
        eyebrow="Executive overview"
        title="Command Center"
        subtitle="A decision-first view of the current commercial intelligence engine."
        d={d}
      />
      <section className="command-grid">
        <article className="panel command-opportunity">
          <div className="opportunity-title">
            <span className="feature-icon">
              <Building2 />
            </span>
            <div>
              <h2>{d.project.canonical_name}</h2>
              <div className="context-line">
                <MapPin size={14} />
                {d.project.city}, {d.project.region}
                <span>•</span>
                {titleCase(d.project.stage)}
              </div>
            </div>
            <Pill>
              {a.overall_band} · {a.operational_action}
            </Pill>
          </div>
          <div className="command-score-row">
            <DecisionCard
              label="Commercial Fit"
              value={a.overall_band}
              action={a.operational_action}
              note="Deterministic ordering band; not a probability"
              icon={Target}
            />
            <DecisionCard
              label="Data Confidence"
              value={titleCase(a.confidence_state)}
              note="Independent evidence reliability and completeness"
              icon={ShieldCheck}
            />
            <div className="reasons">
              <b>Key reasons</b>
              {d.assessment.dimensions.slice(0, 4).map((item: any) => (
                <span key={item.key}>
                  <CircleCheck size={15} />
                  {item.label}: {titleCase(item.band)}
                </span>
              ))}
            </div>
          </div>
        </article>
        <article className="panel trust-panel">
          <SectionHead
            title={`Top ${Math.min(3, d.quality.length)} of ${d.quality.length} trust issues`}
            icon={ShieldCheck}
          />
          {d.quality.slice(0, 3).map((item) => (
            <button key={item.id} onClick={() => setView("evidence")}>
              <span className="alert-icon">
                <TriangleAlert size={18} />
              </span>
              <div>
                <b>{item.title}</b>
                <p>
                  Decision impact:{" "}
                  {titleCase(item.decision_impact || "Not specified")}
                </p>
              </div>
              <ChevronRight size={16} />
            </button>
          ))}
        </article>
        <article className="panel funnel">
          <SectionHead title="Current system diagnostics" icon={BarChart3} />
          {metrics ? (
            <>
              <div className="diagnostic-bars">
                {diagnosticEntries.map(({ key, value }) => (
                  <div className="diagnostic-row" key={key}>
                    <span>{metricLabel(metrics.definitions, key)}</span>
                    <div className="diagnostic-track" aria-hidden="true">
                      <i
                        style={{
                          width: value
                            ? `${Math.max(3, (value / maxDiagnosticValue) * 100)}%`
                            : "0%",
                        }}
                      />
                    </div>
                    <b>{value}</b>
                  </div>
                ))}
              </div>
              <p className="note">
                Independently scaled inventory diagnostics; not funnel stages,
                conversion rates, or production outcomes.
              </p>
            </>
          ) : (
            <DegradedPanel
              failure={failureFor(d, "metrics", "System diagnostics")}
              retry={retry}
              retrying={retrying === "metrics"}
            />
          )}
        </article>
        <article className="panel account-snapshot">
          <SectionHead
            title={`${d.organization?.canonical_name || "EE Reed"} intelligence`}
            icon={Building2}
          />
          {(d.organization?.domains || []).slice(0, 3).map((item: any) => (
            <div className="list-row" key={item.domain}>
              <div>
                <b>{item.domain}</b>
                <small>Domain relationship</small>
              </div>
              <Pill>{item.relationship_state}</Pill>
            </div>
          ))}
          <button className="text-button" onClick={() => setView("account")}>
            View account profile <ArrowRight size={15} />
          </button>
        </article>
        <article className="panel next-action">
          <SectionHead title="Next best action" icon={Target} />
          {action ? (
            <div className="ranked-action">
              <span>1</span>
              <div>
                <b>{titleCase(action.action_type)}</b>
                <p>{action.reason}</p>
                <small>
                  Priority {action.priority} · progress only when prerequisites
                  clear
                </small>
              </div>
            </div>
          ) : (
            <Empty
              title="No action generated"
              detail="The backend did not return a current action."
            />
          )}
          <button className="text-button" onClick={() => setView("commercial")}>
            View commercial motion <ArrowRight size={15} />
          </button>
        </article>
      </section>
    </div>
  );
}

function ApolloPreviewPanel({ d, mode, close }: { d: DashboardData; mode: "search" | "enrichment"; close: () => void }) {
  const request = mode === "search" ? d.apollo.search : d.apollo.enrichment?.request;
  return <div className="drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) close(); }}><aside className="drawer" role="dialog" aria-modal="true" aria-label={mode === "search" ? "Apollo search preview" : "Apollo enrichment preview"}><button className="icon-button drawer-close" onClick={close} aria-label="Close Apollo preview"><X /></button><p className="eyebrow">Apollo {mode} preview</p><h2>{mode === "search" ? d.apollo.organization : d.apollo.enrichment?.display_name}</h2><div className="dry-run-banner"><Info size={17} /><span><b>PREVIEW ONLY</b> · External request executed: NO</span><Pill>{request?.credit_consuming ? "MAY_CONSUME_CREDITS_LIVE" : "NO_CREDITS_SPENT"}</Pill></div>{request ? <><dl className="detail-grid"><div><dt>Project</dt><dd>{d.apollo.project}</dd></div><div><dt>Organization</dt><dd>{d.apollo.organization}</dd></div><div><dt>Operation</dt><dd>{mode === "search" ? "People Search" : "People Enrichment"}</dd></div><div><dt>Mode</dt><dd>{request.mode}</dd></div><div><dt>Method</dt><dd>{request.method}</dd></div><div><dt>Results requested</dt><dd>{String(request.params.per_page || "Selected person")}</dd></div></dl>{mode === "search" ? <><h3>Target personas</h3><div className="pill-row">{d.apollo.target_personas?.map((item) => <Pill key={item}>{item}</Pill>)}</div><h3>Supported domains and location</h3><p>{d.apollo.supported_domains?.join(" · ")} · {d.apollo.location_filters?.join(" · ") || "No location filter"}</p><h3>Reason for search</h3><p>{d.apollo.purpose}</p></> : <><h3>Evidence before enrichment</h3><div className="detail-list">{Object.entries(d.apollo.enrichment?.before || {}).map(([key, value]) => <div key={key}><span>{titleCase(key)}</span><Pill>{value}</Pill></div>)}</div><h3>What enrichment can and cannot change</h3><ul className="check-list">{d.apollo.enrichment?.constraints.map((item) => <li key={item}>{item}</li>)}</ul></>}<details><summary>Inspect demo-safe request</summary><pre>{JSON.stringify({ endpoint: request.endpoint, params: request.params }, null, 2)}</pre></details></> : <Empty title="Preview unavailable" detail={d.apollo.reason || "This project does not have the context required for Apollo."} />}</aside></div>;
}

function IntegrationStatus({ d }: { d: DashboardData }) {
  const integrations = d.systemReadiness?.integrations || {};
  const rows = [
    ["ConstructConnect", integrations.constructconnect, "Supplied reports ingested; recurring production feed NOT CONNECTED"],
    ["Apollo", integrations.apollo, "Preview request construction only; no employer-demo network call"],
    ["Pipedrive", integrations.pipedrive, "Dry-run request construction only; employer-demo writes disabled"],
    ["OpenAI", integrations.openai, "Optional grounded Commercial Analyst runtime"],
    ["Google / Trello", integrations.google, "Preview contracts only"],
  ] as const;
  return <article className="panel integration-status"><SectionHead title="Integration readiness" icon={Network} aside="Configuration state; not a live connection claim" />{rows.map(([label, state, note]) => <div className="integration-row" key={label}><div><b>{label}</b><small>{note}</small></div><Pill>{state?.status || state?.mode || "OFF"}</Pill><span>{state?.credentials_present === true ? "Credentials configured" : state?.credentials_present === false ? "Credentials missing" : "No credential required"}</span></div>)}</article>;
}

function ProjectIntelligence({
  d,
  open,
  setView,
}: {
  d: DashboardData;
  open: (item: Evidence) => void;
  setView: (view: ViewKey) => void;
}) {
  const [apolloPreview, setApolloPreview] = useState<"search" | "enrichment" | null>(null);
  const a = d.assessment.assessment;
  const counterfactual =
    d.sensitivity.counterfactuals.find(
      (item: any) => item.key === "without_reported_value",
    ) ||
    d.sensitivity.counterfactuals[0] ||
    {};
  const reportedValue =
    evidenceFor(d, "reported_value") || evidenceFor(d, "project_value");
  return (
    <div className="page" data-view="project">
      <PageHeader
        eyebrow="Project Intelligence"
        title={d.project.canonical_name}
        d={d}
      />
      <section className="score-band">
        <DecisionCard
          label="Commercial Fit"
          value={a.overall_band}
          action={a.operational_action}
          note="qualification-2.0 deterministic band"
          icon={Target}
        />
        <DecisionCard
          label="Data Confidence"
          value={titleCase(a.confidence_state)}
          note="Independent evidence state"
          icon={ShieldCheck}
        />
        {d.assessment.product_fits.map((fit: any) => (
          <DecisionCard
            key={fit.product_code}
            label={`${fit.product_code} applicability`}
            value={titleCase(fit.applicability_status)}
            note="Possible relevance only; direct need unconfirmed"
            icon={Zap}
          />
        ))}
      </section>
      <section className="panel">
        <SectionHead title="Source facts and trust boundaries" icon={FileSearch} aside="Detailed PROJECT report" />
        <div className="detail-grid">
          <div><dt>ConstructConnect ID</dt><dd>{d.project.external_id}</dd></div>
          <div><dt>Source category</dt><dd>{d.project.category || "Not retained"}</dd></div>
          <div><dt>Location</dt><dd>{d.project.city}, {d.project.region} {d.project.country_code || ""}</dd></div>
          <div><dt>Stage</dt><dd>{titleCase(d.project.stage)}</dd></div>
          <div><dt>Reported value</dt><dd>{money(d.project.reported_value)} — zero scoring influence</dd></div>
          <div><dt>Source-labeled start</dt><dd>{dateStamp(d.project.start_date)}</dd></div>
          <div><dt>Related phases</dt><dd>{d.projectOrganizations.project_group?.projects.length || 0} records in supported campus group</dd></div>
          <div><dt>Rental / equipment authority</dt><dd>UNKNOWN</dd></div>
        </div>
        <div className="warning-list">
          {d.quality.slice(0, 5).map((item) => <button key={item.id} onClick={() => setView("evidence")}><TriangleAlert /><span><b>{item.title}</b><small>{item.detail || item.decision_impact}</small></span><Pill>{item.review_status}</Pill></button>)}
        </div>
        <p className="assessment-disclaimer">The source category says Offices while the narrative describes a data center. The supplied report also identifies broader-development projections, a future-dated “Actual Start Date,” and no verified project-level rental authority.</p>
      </section>
      <section className="panel commercial-actions">
        <SectionHead title="Commercial Actions" icon={Workflow} aside="Every action remains server-policy controlled" />
        <div className="action-cards">
          <div><span>Assessment</span><b>{a.overall_band} · {a.operational_action}</b><small>qualification-2.0 current</small></div>
          <div><span>Contacts</span><b>{d.candidates.count} Stafford candidates</b><button onClick={() => setView("contacts")}>Review candidates <ArrowRight size={14} /></button></div>
          <div><span>Top candidate</span><b>{d.candidates.items[0]?.display_name || "Not available"}</b><small>Authority: {d.candidates.items[0]?.verification?.rental_authority || "UNKNOWN"}</small></div>
          <div><span>Apollo</span><b>Preview ready</b><button onClick={() => setApolloPreview("search")} disabled={!d.apollo.eligible}>Preview Apollo Search</button></div>
          <div><span>Enrichment</span><b>{d.apollo.enrichment?.display_name || "Candidate required"}</b><button onClick={() => setApolloPreview("enrichment")} disabled={!d.apollo.enrichment}>Preview Enrichment</button></div>
          <div><span>CRM</span><b>Lead ready · Deal blocked</b><button onClick={() => setView("crm")}>Preview Pipedrive Sync <ArrowRight size={14} /></button></div>
        </div>
        <div className="automation-pipeline" aria-label="Commercial automation pipeline"><div><CircleCheck /><span>Project</span><b>Ingested</b></div><div><CircleCheck /><span>Qualification</span><b>Assessed</b></div><div><CircleCheck /><span>Account</span><b>GC identified</b></div><div><CircleCheck /><span>Contacts</span><b>Candidates available</b></div><div><CircleHelp /><span>Apollo</span><b>Not searched</b></div><div><TriangleAlert /><span>Verification</span><b>Authority unknown</b></div><div><CircleCheck /><span>CRM</span><b>Lead ready</b></div><div><LockKeyhole /><span>Deal</span><b>Blocked</b></div></div>
      </section>
      <section className="project-grid">
        <article className="panel signals-panel">
          <SectionHead title="Project signals" icon={Gauge} />
          {d.signals.slice(0, 7).map((item: any) => (
            <div className="list-row" key={item.id}>
              <span className="row-icon">
                <Zap size={16} />
              </span>
              <div>
                <b>{titleCase(item.key)}</b>
                <small>{item.explanation || item.value}</small>
              </div>
              <Pill>{item.classification}</Pill>
            </div>
          ))}
        </article>
        <article className="panel evidence-summary">
          <SectionHead title="Evidence & trust" icon={ShieldCheck} />
          {d.evidence.slice(0, 6).map((item) => (
            <button
              className="table-row evidence-row"
              key={item.evidence_id}
              onClick={() => open(item)}
            >
              <div>
                <b>{titleCase(item.field_name)}</b>
                <small>{item.section_name || "Source"}</small>
              </div>
              <Pill>{item.classification}</Pill>
              <Pill>{item.confidence_state}</Pill>
              <ChevronRight size={15} />
            </button>
          ))}
        </article>
        <article className="panel contact-summary">
          <SectionHead title="Contact resolution" icon={UsersRound} />
          {d.candidates.items.slice(0, 4).map((person) => (
            <div className="table-row contact-row" key={person.candidate_id}>
              <span className="avatar">
                {String(person.display_name)
                  .split(" ")
                  .map((part: string) => part[0])
                  .slice(0, 2)
                  .join("")}
              </span>
              <div>
                <b>{person.display_name}</b>
                <small>{titleCase(person.target_persona)}</small>
              </div>
              <Pill>{person.verification?.rental_authority || "UNKNOWN"}</Pill>
              <span className="candidate-priority">
                <b>{score(person.candidate_score)}</b>
                <small>Investigation priority</small>
              </span>
            </div>
          ))}
        </article>
        <article className="panel action-summary">
          <SectionHead title="Next best action" icon={Target} />
          {d.actions.items.slice(0, 4).map((item: any, index: number) => (
            <div className="ranked-action compact" key={item.id}>
              <span>{index + 1}</span>
              <div>
                <b>{titleCase(item.action_type)}</b>
                <p>{item.reason}</p>
              </div>
              <Pill>{item.status}</Pill>
            </div>
          ))}
        </article>
        <article className="panel first-call">
          <SectionHead
            title="First-call kit"
            aside={d.actions.first_call_kit.version}
            icon={MessageSquareText}
          />
          <ol>
            {d.actions.first_call_kit.questions.map((item: string) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        </article>
        <article className="panel challenge">
          <SectionHead
            title="Counterfactual sensitivity"
            icon={RefreshCw}
            aside="Deterministic qualification-2.0"
          />
          <div className="comparison">
            <div>
              <span>Baseline</span>
              <b>{d.sensitivity.baseline.overall_band}</b>
              <Pill>{d.sensitivity.baseline.operational_action}</Pill>
            </div>
            <ArrowRight />
            <div>
              <span>{counterfactual.label || "Reported value removed"}</span>
              <b>{counterfactual.band || "Unknown"}</b>
              <Pill>{counterfactual.action || "UNKNOWN"}</Pill>
            </div>
          </div>
          <p className="assessment-disclaimer">
            Reported value contributes zero qualification points and cannot
            control disposition.
          </p>
          <button
            className="text-button"
            onClick={() => reportedValue && open(reportedValue)}
          >
            Inspect source-reported {money(d.project.reported_value)} value{" "}
            <ArrowRight size={15} />
          </button>
        </article>
      </section>
      <IntegrationStatus d={d} />
      {apolloPreview && <ApolloPreviewPanel d={d} mode={apolloPreview} close={() => setApolloPreview(null)} />}
    </div>
  );
}

function ProjectPortfolio({
  g,
  selectedProjectId,
  openProject,
}: {
  g: GeneralizationData;
  selectedProjectId: string;
  openProject: (project: PortfolioProject) => void;
}) {
  const [query, setQuery] = useState("");
  const [coverage, setCoverage] = useState("ALL");
  const [section, setSection] = useState("ALL");
  const [dataSet, setDataSet] = useState<"detailed" | "history">("history");
  const items = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return g.portfolio.items.filter((project) => {
      const searchable = [
        project.canonical_name,
        project.external_id,
        project.city,
        project.region,
        ...project.source_roles,
        ...project.relationships.map((item) => item.organization),
      ]
        .join(" ")
        .toLowerCase();
      return (
        (dataSet === "detailed"
          ? project.assessment_coverage === "FULL"
          : project.source_report_types.includes("COMPANY")) &&
        (!needle || searchable.includes(needle)) &&
        (coverage === "ALL" || project.assessment_coverage === coverage) &&
        (section === "ALL" || project.source_sections.includes(section))
      );
    });
  }, [coverage, dataSet, g.portfolio.items, query, section]);
  const summary = g.portfolio.summary;
  return (
    <div className="page" data-view="portfolio">
      <PageHeader
        eyebrow="Data / Project Data"
        title="Detailed qualification and company history"
        subtitle="The broader EE Reed company history is shown first. Stafford remains the one source record with enough project-level evidence for full qualification."
      />
      <section className="score-band portfolio-summary eight">
        <Metric label="Source documents" value={summary.source_documents} note={`${summary.detailed_project_documents} project · ${summary.company_documents} company`} icon={Database} />
        <Metric label="Detailed project records" value={summary.detailed_project_records} note="Eligible for full triage" icon={Target} />
        <Metric label="Company-history rows" value={summary.source_project_rows} note="Not independent opportunities" icon={FileSearch} />
        <Metric label="Canonical history projects" value={summary.company_history_projects} note="Resolved EE Reed history" icon={Building2} />
        <Metric label="Full assessments" value={summary.projects_assessed} note="Current qualification-2.0" icon={CircleCheck} />
        <Metric label="Partial" value={summary.projects_partially_assessable} note="More evidence required" icon={CircleHelp} kind="warn" />
        <Metric label="Source only" value={summary.source_only_projects} note="No score inferred" icon={FileSearch} kind="warn" />
        <Metric label="Review findings" value={summary.project_quality_warnings} note="Quality warnings, not leads" icon={TriangleAlert} kind="warn" />
      </section>
      <div className="objective-banner"><Workflow /><span><b>Generic batch triage:</b> {g.triage.full_eligible} FULL record assessed; {g.triage.source_only} SOURCE_ONLY records routed without scores; {g.triage.external_writes_executed} external writes. {g.triage.semantics}</span></div>
      <div className="tab-list" role="tablist" aria-label="Project data type">
        <button role="tab" aria-selected={dataSet === "history"} className={dataSet === "history" ? "active" : ""} onClick={() => { setDataSet("history"); setCoverage("ALL"); }}>EE Reed project history ({summary.company_history_projects} source records)</button>
        <button role="tab" aria-selected={dataSet === "detailed"} className={dataSet === "detailed" ? "active" : ""} onClick={() => { setDataSet("detailed"); setCoverage("ALL"); }}>Detailed assessment queue ({summary.detailed_project_records} eligible)</button>
      </div>
      <section className="panel portfolio-table-panel">
        <SectionHead
          title={dataSet === "detailed" ? `Detailed records (${items.length})` : `Company-history projects (${items.length})`}
          aside="Select a row to open project intelligence"
          icon={Database}
        />
        <div className="portfolio-filters" aria-label="Portfolio filters">
          <label>
            <span>Search projects</span>
            <div className="field-with-icon"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, location, role, or account" /></div>
          </label>
          <label>
            <span>Assessment coverage</span>
            <select value={coverage} onChange={(event) => setCoverage(event.target.value)}>
              <option value="ALL">All coverage states</option>
              <option value="FULL">Fully assessed</option>
              <option value="PARTIAL">Partial</option>
              <option value="SOURCE_ONLY">Source-only</option>
              <option value="INSUFFICIENT">Insufficient evidence</option>
            </select>
          </label>
          <label>
            <span>Source section</span>
            <select value={section} onChange={(event) => setSection(event.target.value)}>
              <option value="ALL">All sections</option>
              <option value="PLANNING">Planning</option>
              <option value="PRE_BID">Pre-bid</option>
              <option value="POST_BID">Post-bid</option>
              <option value="BIDDING_ROLE">Bidding role</option>
            </select>
          </label>
        </div>
        <div className="table-scroll portfolio-scroll">
          <div className="table-head portfolio-grid">
            <span>Project</span><span>Source / stage</span><span>Account role</span>
            <span>Coverage</span><span>Fit / confidence</span><span>Quality</span><span />
          </div>
          {items.map((project) => (
            <button
              className={`portfolio-grid portfolio-project-row ${selectedProjectId === project.id ? "selected" : ""}`}
              key={project.id}
              onClick={() => openProject(project)}
            >
              <div><b>{project.canonical_name}</b><small>{project.city}, {project.region} · {project.external_id}</small></div>
              <div><b>{project.source_sections.map(titleCase).join(" · ")}</b><small>{titleCase(project.stage)} · {project.source_occurrence_count} source row{project.source_occurrence_count === 1 ? "" : "s"}</small></div>
              <div><b>{primaryRelationship(project)?.organization || "Account unresolved"}</b><small>{primaryRelationship(project) ? titleCase(primaryRelationship(project)?.role) : project.source_roles.map(titleCase).join(" · ") || "Role unavailable"}</small></div>
              <div><Pill>{project.assessment_coverage}</Pill><small>{project.source_report_types.map(titleCase).join(" · ")} source</small></div>
              <div>{dataSet === "detailed" && project.assessment_coverage === "FULL" ? <><b>{project.commercial_band}</b><small>{titleCase(project.data_confidence)} · {titleCase(project.operational_action)}</small></> : <><b>N/A — source only</b><small>No qualification score inferred</small></>}</div>
              <div><Pill>{project.quality_state}</Pill><small>{project.quality_warning_count} warnings</small></div>
              <ChevronRight size={16} />
            </button>
          ))}
          {!items.length && <Empty title="No projects match these filters" detail="Adjust the search or coverage filters to restore results." />}
        </div>
      </section>
      <p className="assessment-disclaimer">Stafford is the featured supplied detailed case; it is not ranked against 165 equivalent detailed reports. {g.portfolio.semantics.source_rows} {g.portfolio.semantics.scores}</p>
    </div>
  );
}

function SourceExplorer({ g }: { g: GeneralizationData }) {
  const [tab, setTab] = useState<"projects" | "contacts">("projects");
  const sections = g.account.source_section_counts;
  return (
    <div className="page" data-view="source">
      <PageHeader
        eyebrow="Data / Account and Source Data"
        title="EE Reed company history and contact sources"
        subtitle="Demo-safe source coverage, quality, and resolution state without exposing private raw documents or treating a directory row as a Stafford decision-maker. Licensed-source names and contact details are masked; duplicate and malformed-name findings remain visible as quality state."
      />
      <section className="score-band portfolio-summary">
        <Metric label="Planning" value={sections.PLANNING || 0} note="Source project rows" icon={FileSearch} />
        <Metric label="Pre-bid" value={sections.PRE_BID || 0} note="Source project rows" icon={FileSearch} />
        <Metric label="Post-bid" value={sections.POST_BID || 0} note="Source project rows" icon={FileSearch} />
        <Metric label="Bidding role" value={sections.BIDDING_ROLE || 0} note="Source project rows" icon={FileSearch} />
      </section>
      <section className="evidence-streams" aria-label="Two independent contact evidence streams">
        <article><p className="eyebrow">Source 1</p><h2>EE Reed source directory</h2><p>ConstructConnect company-report occurrences and canonical identities.</p><div><span>Directory rows <b>{g.sourceContacts.funnel.source_directory_rows}</b></span><span>Canonical identities <b>{g.sourceContacts.funnel.canonical_source_identities}</b></span><span>Any project association <b>{g.sourceContacts.funnel.source_people_with_any_project_association}</b></span></div></article>
        <span className="stream-join"><ArrowRight /><b>Identity / evidence reconciliation</b></span>
        <article><p className="eyebrow">Source 2</p><h2>Stafford-specific research</h2><p>Project-specific public/company research and future Apollo evidence.</p><div><span>Research candidates <b>{g.sourceContacts.funnel.project_research_candidates}</b></span><span>Top investigation candidate <b>{g.sourceContacts.funnel.current_top_investigation_candidates}</b></span><span>Authority verified <b>{g.sourceContacts.funnel.authority_verified}</b></span></div></article>
      </section>
      <div className="reconciliation-path"><span>Employment</span><ArrowRight /><span>Project association</span><ArrowRight /><span>Role relevance</span><ArrowRight /><span>Investigation priority</span><ArrowRight /><span>Rental / equipment authority</span></div>
      <p className="assessment-disclaimer prominent">These are parallel evidence streams, not a 32-to-6 filtering funnel. A source-directory person may never become a Stafford candidate, and a Stafford research candidate may not appear in the original directory.</p>
      <div className="tab-list" role="tablist" aria-label="Source explorer data set">
        <button role="tab" aria-selected={tab === "projects"} className={tab === "projects" ? "active" : ""} onClick={() => setTab("projects")}>Project source rows</button>
        <button role="tab" aria-selected={tab === "contacts"} className={tab === "contacts" ? "active" : ""} onClick={() => setTab("contacts")}>Source contacts ({g.sourceContacts.count})</button>
      </div>
      {tab === "projects" ? (
        <section className="panel source-table-panel">
          <SectionHead title={`${g.portfolio.summary.source_project_rows} source rows → ${g.portfolio.summary.canonical_projects} canonical projects`} icon={Database} />
          <div className="table-scroll">
            <div className="table-head source-project-grid"><span>Canonical project</span><span>Source sections</span><span>Occurrences</span><span>Role</span><span>Resolution</span></div>
            {g.portfolio.items.map((project) => <div className="source-project-grid" key={project.id}><div><b>{project.canonical_name}</b><small>{project.external_id}</small></div><div>{project.source_sections.map(titleCase).join(" · ")}</div><div>{project.source_occurrence_count}</div><div>{project.source_roles.map(titleCase).join(" · ")}</div><Pill>{project.source_occurrence_count > 1 ? "RESOLVED_MULTI_ROW" : "RESOLVED"}</Pill></div>)}
          </div>
        </section>
      ) : (
        <section className="panel source-table-panel">
          <SectionHead title={`Demo-safe source contacts (${g.sourceContacts.count})`} aside="Directory rows are not Stafford candidate rankings" icon={UsersRound} />
          <div className="table-scroll">
            <div className="table-head source-contact-grid"><span>Source identity</span><span>Status</span><span>Contact state</span><span>Quality</span><span>Associations</span><span>Rank eligibility</span></div>
            {g.sourceContacts.items.map((person: SourceContact) => <div className="source-contact-grid" key={person.person_id}><div><b>{person.display_name}</b><small>{person.source_occurrence_count} source occurrence{person.source_occurrence_count === 1 ? "" : "s"}</small></div><Pill>{person.source_status}</Pill><div><b>{person.contact_points.length ? person.contact_points.map((point) => titleCase(point.type)).join(" · ") : "No contact point"}</b><small>{person.domains.join(" · ") || "Domain unavailable"}</small></div><div><Pill>{person.identity_quality}</Pill><small>{person.quality_findings.length} findings</small></div><div><b>{person.project_association_count} projects</b><small>Selected project: {titleCase(person.selected_project_association)}</small></div><div><Pill>{person.rank_eligible ? "ELIGIBLE" : "NOT_ELIGIBLE"}</Pill><small>{person.rank_eligibility_reason}</small></div></div>)}
          </div>
        </section>
      )}
      <p className="assessment-disclaimer">{g.sourceContacts.semantics.directory} {g.sourceContacts.semantics.candidates}</p>
    </div>
  );
}

function SourceOnlyProject({ project }: { project: PortfolioProject }) {
  return (
    <div className="page" data-view="project">
      <PageHeader eyebrow="Project Intelligence / Source-only record" title={project.canonical_name} subtitle={`${project.city}, ${project.region}${project.external_id ? ` · ${project.external_id}` : ""}`} />
      <section className="score-band four">
        <DecisionCard label="Assessment coverage" value={titleCase(project.assessment_coverage)} action="REVIEW" note="No complete qualification-2.0 assessment exists" icon={FileSearch} />
        <DecisionCard label="Commercial Fit" value="Not assessed" note="No band or score inferred from a company-history record" icon={Target} />
        <DecisionCard label="Data Confidence" value="Not assessed" note="Coverage is not a confidence rating" icon={ShieldCheck} />
        <DecisionCard label="Product applicability" value="Not assessed" note="No direct lighting or power need confirmed" icon={Zap} />
      </section>
      <section className="two-column-grid">
        <article className="panel"><SectionHead title="Canonical project facts" icon={Building2} /><div className="detail-list"><div><span>Stage</span><b>{titleCase(project.stage)}</b></div><div><span>Reported value</span><b>{money(project.reported_value)}</b></div><div><span>Source sections</span><b>{project.source_sections.map(titleCase).join(" · ")}</b></div><div><span>Source occurrences</span><b>{project.source_occurrence_count}</b></div><div><span>Available source fields</span><b>{project.available_source_field_count}</b></div></div></article>
        <article className="panel"><SectionHead title="Account relationships" icon={Network} />{project.relationships.map((relationship) => <div className="list-row" key={`${relationship.organization_id}-${relationship.role}`}><span className="row-icon"><Building2 size={16} /></span><div><b>{relationship.organization}</b><small>{titleCase(relationship.role)}</small></div><Pill>{relationship.verification_state}</Pill></div>)}</article>
        <article className="panel span-2"><SectionHead title="Source semantics and freshness" icon={Clock3} /><div className="detail-list"><div><span>Report type</span><b>{project.source_report_types.map(titleCase).join(" / ")}</b></div><div><span>Bidding role</span><b>{project.source_roles.map(titleCase).join(" / ") || "Not listed"}</b></div><div><span>Bid date</span><b>{dateStamp(project.source_bid_date)}</b></div><div><span>Freshness</span><b>{titleCase(project.source_freshness_band)}</b></div><div><span>Source contact listed</span><b>{project.source_contact_available ? "Yes — not verified authority" : "No"}</b></div></div></article>
        <article className="panel span-2"><SectionHead title="Required next evidence" icon={FileSearch} /><Empty title="Full commercial assessment unavailable" detail="A detailed project record is required before full commercial qualification. Then confirm trusted timing, contractor relationship, contactability, and direct lighting or power requirements." /></article>
      </section>
      <p className="assessment-disclaimer">This is a canonical source record, not a success probability, forecast, verified demand signal, or completed qualification.</p>
    </div>
  );
}

function UnavailableProjectLayer({ project, navigate }: { project: PortfolioProject; navigate: (view: ViewKey) => void }) {
  return <div className="page"><PageHeader eyebrow="Project coverage" title={project.canonical_name} subtitle="This selected project has source coverage but no complete commercial assessment." /><section className="panel unavailable-layer"><FileSearch size={28} /><h2>Project-specific detail is not yet available</h2><p>Stafford evidence, contacts, product applicability, CRM readiness, and analyst conclusions are never reused for another project. Complete this project’s evidence and qualification workflow before these views can render.</p><div><button className="button primary" onClick={() => navigate("project")}>View available project facts</button><button className="button ghost" onClick={() => navigate("portfolio")}>Return to portfolio</button></div></section></div>;
}

function AccountSourceSnapshot({ g }: { g: GeneralizationData }) {
  const sections = g.account.source_section_counts;
  return <section className="panel"><SectionHead title="Authoritative company-source snapshot" icon={Database} aside={`Company ID ${g.account.constructconnect_company_id || "unavailable"}`} /><div className="source-coverage-band"><div><span>Planning Projects</span><b>{sections.PLANNING || 0}</b><small>company-report rows</small></div><div><span>Bidding Projects</span><b>{sections.BIDDING || 0}</b><small>not the bidding-role count</small></div><div><span>Post Bid Projects</span><b>{sections.POST_BID || 0}</b><small>company-report rows</small></div><div><span>Bidding Role Projects</span><b>{sections.BIDDING_ROLE || 0}</b><small>role association, not bidding stage</small></div></div><p className="assessment-disclaimer"><b>Bidding Projects = 0</b> is not the same measure as <b>Bidding Role Projects = {sections.BIDDING_ROLE || 0}</b>. Historical, current, and undated rows are mixed in the company report; source rows are not automatically independent opportunities.</p></section>;
}

function AccountDistributionPanels({ g }: { g: GeneralizationData }) {
  return <><article className="panel"><SectionHead title="Activity and freshness" icon={Clock3} /><div className="detail-list">{g.account.activity_bands.map((item) => <div key={item.band}><span>{titleCase(item.band)}</span><b>{item.source_row_count} rows / {item.unique_project_count} projects</b></div>)}</div></article><article className="panel"><SectionHead title="Project-type distribution" icon={BarChart3} /><div className="detail-list">{Object.entries(g.account.project_type_counts).slice(0, 7).map(([label, value]) => <div key={label}><span>{titleCase(label)}</span><b>{value}</b></div>)}</div></article><article className="panel"><SectionHead title="Geography distribution" icon={MapPin} /><div className="detail-list">{Object.entries(g.account.geography_counts).slice(0, 7).map(([label, value]) => <div key={label}><span>{label}</span><b>{value}</b></div>)}</div></article><article className="panel"><SectionHead title="Account decision state" icon={ShieldCheck} /><div className="detail-list"><div><span>Strategic signal</span><b>{titleCase(g.account.strategic_signal_band)}</b></div><div><span>Entity resolution</span><b>{titleCase(g.account.entity_resolution_state)}</b></div><div><span>Recommendation</span><b>{titleCase(g.account.account_recommendation)}</b></div><div><span>Inactive contacts</span><b>{g.account.inactive_source_contacts}</b></div></div></article></>;
}

function AccountIntelligence({ d, g, setView }: { d: DashboardData; g: GeneralizationData; setView: (view: ViewKey) => void }) {
  const contacts = d.organizationContacts?.items || [];
  const generic = contacts.filter((contact: any) =>
    contact.contact_points.some((point: any) => point.is_generic),
  ).length;
  const group = d.projectOrganizations.project_group;
  return (
    <div className="page" data-view="account">
      <PageHeader
        eyebrow="Account Intelligence"
        title={d.organization?.canonical_name || "EE Reed Construction"}
        subtitle="Canonical account intelligence without silently merging uncertain identities."
        d={d}
      />
      <section className="score-band four">
        <Metric
          label="Source project rows"
          value={g.account.source_project_rows}
          note={`${g.account.unique_projects} canonical projects`}
          icon={Database}
        />
        <Metric
          label="Source contacts"
          value={g.account.source_contact_rows}
          note={`${g.account.canonical_source_contacts} canonical identities`}
          icon={UsersRound}
        />
        <Metric
          label="Generic-inbox records"
          value={g.account.generic_inbox_records}
          note="Require review"
          icon={MessageSquareText}
          kind="warn"
        />
        <Metric
          label="Known domains"
          value={g.account.known_domain_count}
          note="Relationship state preserved"
          icon={Network}
        />
      </section>
      <AccountSourceSnapshot g={g} />
      <section className="three-column-grid">
        <article className="panel">
          <SectionHead title="What stands out" icon={Lightbulb} />
          <div className="finding-list">
            <div>
              <UsersRound />
              <span>
                <b>Duplicate and malformed contacts</b>
                <small>Names and generic inboxes remain reviewable.</small>
              </span>
            </div>
            <div>
              <Database />
              <span>
                <b>Mixed historical and current data</b>
                <small>
                  Old relationships do not become present authority.
                </small>
              </span>
            </div>
            <div>
              <Network />
              <span>
                <b>Multiple domains in use</b>
                <small>Each relationship retains its evidence state.</small>
              </span>
            </div>
            <div>
              <Building2 />
              <span>
                <b>Recurring project activity</b>
                <small>Commercial relevance, not decision authority.</small>
              </span>
            </div>
          </div>
        </article>
        <article className="panel">
          <SectionHead title="Contact quality findings" icon={ShieldCheck} />
          {(d.organization?.domains || []).map((item: any) => (
            <div className="list-row" key={item.domain}>
              <span className="row-icon">
                <Network size={16} />
              </span>
              <div>
                <b>{item.domain}</b>
                <small>Account-domain relationship</small>
              </div>
              <Pill>{item.relationship_state}</Pill>
            </div>
          ))}
          <div className="list-row">
            <span className="row-icon">
              <MessageSquareText size={16} />
            </span>
            <div>
              <b>{generic} generic inbox records</b>
              <small>Never promoted as individual authority</small>
            </div>
            <Pill>{generic ? "REVIEW" : "VERIFIED"}</Pill>
          </div>
        </article>
        <article className="panel portfolio">
          <SectionHead title="Project portfolio snapshot" icon={Building2} />
          {(d.organizationProjects?.items || [])
            .slice(0, 8)
            .map((project: any) => (
              <div className="table-row" key={project.project_id}>
                <span className="row-icon">
                  <Building2 size={16} />
                </span>
                <div>
                  <b>{project.canonical_name}</b>
                  <small>{project.stage || "Stage unknown"}</small>
                </div>
                <Pill>{project.verification_state}</Pill>
              </div>
            ))}
          <button className="text-button" onClick={() => setView("portfolio")}>View all {g.account.unique_projects} projects <ArrowRight size={15} /></button>
        </article>
        <article className="panel span-2">
          <SectionHead
            title="Stafford project and phase clustering"
            icon={GitBranch}
          />
          {group ? (
            <div className="phase-map">
              <div>
                <Building2 />
                <b>{group.canonical_name}</b>
              </div>
              {group.projects.map((project: any) => (
                <article key={project.id}>
                  <span />
                  <div>
                    <b>{project.canonical_name}</b>
                    <small>
                      {project.stage} · reported {money(project.reported_value)}
                    </small>
                  </div>
                  <Pill>{project.verification_state || "SUPPORTED"}</Pill>
                </article>
              ))}
            </div>
          ) : (
            <Empty
              title="Project group unresolved"
              detail="No supported campus grouping is available."
            />
          )}
        </article>
        <article className="panel">
          <SectionHead title="Next account actions" icon={Target} />
          <ul className="check-list">
            <li>Standardize duplicate names without destructive merges.</li>
            <li>Replace generic inboxes with verified individual contacts.</li>
            <li>Confirm active roles for Stafford project phases.</li>
            <li>
              Keep historical relationships separate from current authority.
            </li>
          </ul>
          <button className="text-button" onClick={() => setView("source")}>Inspect all {g.account.source_contact_rows} source contacts <ArrowRight size={15} /></button>
        </article>
        <article className="panel span-2">
          <SectionHead title="Authoritative source coverage" icon={Database} aside={`Report date ${dateStamp(g.account.report_date)}`} />
          <div className="source-coverage-band">
            {(["PLANNING", "PRE_BID", "POST_BID", "BIDDING_ROLE"] as const).map((key) => <div key={key}><span>{titleCase(key)}</span><b>{g.account.source_section_counts[key] || 0}</b><small>source rows</small></div>)}
          </div>
          <p className="assessment-disclaimer">{g.account.source_company_last_update_note}</p>
        </article>
        <AccountDistributionPanels g={g} />
      </section>
    </div>
  );
}

function ContactResolution({ d, g, setView }: { d: DashboardData; g: GeneralizationData; setView: (view: ViewKey) => void }) {
  const [apolloPreview, setApolloPreview] = useState<"search" | "enrichment" | null>(null);
  return (
    <div className="page" data-view="contacts">
      <PageHeader
        eyebrow="Contact Resolution"
        title="Stafford / EE Reed"
        subtitle="Investigation priority is not authority. Each verification dimension remains independent."
        d={d}
      />
      <section className="verification-ladder">
        <div>
          <b>Our verification ladder</b>
          <p>Four criteria determine whether a person can progress.</p>
        </div>
        {[
          [CircleCheck, "Employment", "Current organization"],
          [CircleCheck, "Project association", "Specific project"],
          [CircleCheck, "Role relevance", "Commercial influence"],
          [LockKeyhole, "Rental authority", "Approval authority"],
        ].map(([Icon, label, copy]) => (
          <div key={String(label)}>
            <Icon size={22} />
            <span>
              <b>{String(label)}</b>
              <small>{String(copy)}</small>
            </span>
          </div>
        ))}
      </section>
      <section className="panel contact-actions">
        <SectionHead title="Contact investigation actions" icon={Workflow} aside="Preview paths execute no external request" />
        <div className="button-row"><button className="button primary" onClick={() => setApolloPreview("search")} disabled={!d.apollo.eligible}><Search size={16} /> Preview Apollo Search</button><button className="button secondary" onClick={() => setApolloPreview("enrichment")} disabled={!d.apollo.enrichment}><UserRound size={16} /> Preview Enrichment</button><button className="button secondary" onClick={() => setView("crm")}><PackageCheck size={16} /> Preview CRM Person</button></div>
        <p className="assessment-disclaimer">Apollo is an evidence source, not an authority source. Search or enrichment cannot independently establish Stafford association, rental responsibility, or purchasing authority.</p>
      </section>
      <section className="panel candidate-table">
        <SectionHead
          title={`Stafford investigation candidates (${d.candidates.count})`}
          icon={UsersRound}
        />
        <p className="table-intro">This ranked research set is distinct from the {g.sourceContacts.source_row_count}-row source contact directory. Employment, project association, role relevance, and rental authority remain independent.</p>
        <div className="table-scroll">
          <div className="table-head contact-grid">
            <span>Candidate</span>
            <span>Employment</span>
            <span>Project</span>
            <span>Role</span>
            <span>Authority</span>
            <span>Investigation priority</span>
          </div>
          {d.candidates.items.map((person) => (
            <article className="contact-grid" key={person.candidate_id}>
              <div className="person-cell">
                <span className="avatar">
                  {String(person.display_name)
                    .split(" ")
                    .map((part: string) => part[0])
                    .slice(0, 2)
                    .join("")}
                </span>
                <span>
                  <b>{person.display_name}</b>
                  <small>{titleCase(person.target_persona)}</small>
                  <small>Origin: {(person.evidence_origins || ["PROJECT_SPECIFIC_PUBLIC_RESEARCH"]).map(titleCase).join(" · ")}</small>
                  <small>
                    Evidence snapshot: {dateStamp(person.verification?.assessed_at)}
                  </small>
                </span>
              </div>
              <Pill>{person.verification?.employment || "UNKNOWN"}</Pill>
              <Pill>
                {person.verification?.project_association || "UNKNOWN"}
              </Pill>
              <Pill>{person.verification?.role_relevance || "UNKNOWN"}</Pill>
              <Pill>{person.verification?.rental_authority || "UNKNOWN"}</Pill>
              <span className="fit-cell">
                <b>{score(person.candidate_score)}</b>
                <small>{scoreBand(person.candidate_score)} priority</small>
              </span>
            </article>
          ))}
        </div>
      </section>
      <section className="contact-bottom">
        <article className="panel best-candidate">
          <SectionHead title="Best current candidate" icon={Sparkles} />
          {d.candidates.items[0] ? (
            <>
              <div className="person-feature">
                <span className="avatar large">
                  {String(d.candidates.items[0].display_name)
                    .split(" ")
                    .map((part: string) => part[0])
                    .slice(0, 2)
                    .join("")}
                </span>
                <div>
                  <h2>{d.candidates.items[0].display_name}</h2>
                  <p>{rationale(d.candidates.items[0].rationale)}</p>
                </div>
                <span className="candidate-priority">
                  <b>{score(d.candidates.items[0].candidate_score)}</b>
                  <small>Investigation priority</small>
                </span>
              </div>
              <Empty
                title="Rental authority is UNKNOWN / unverified"
                detail="Do not treat the top-ranked investigation candidate as a final decision-maker."
              />
            </>
          ) : (
            <Empty
              title="No candidate available"
              detail="The backend returned no ranked contact candidates."
            />
          )}
        </article>
        <article className="panel">
          <SectionHead
            title="First-call verification questions"
            aside={d.actions.first_call_kit.version}
            icon={MessageSquareText}
          />
          <ol className="numbered-list">
            {d.actions.first_call_kit.questions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        </article>
        <article className="panel">
          <SectionHead title="How we know" icon={Database} />
          <div className="source-list">
            <span>
              <Database />
              ConstructConnect <small>Project and company source data</small>
            </span>
            <span>
              <Building2 />
              Company evidence <small>Roles, domains, and recurrence</small>
            </span>
            <span>
              <FileSearch />
              Public research
              <small>
                Snapshot-dated evidence; revalidate before treating it as current
              </small>
            </span>
            <span>
              <ShieldCheck />
              Trust engine <small>Unknowns remain unknown</small>
            </span>
          </div>
          <button className="text-button" onClick={() => setView("source")}>View all source contacts <ArrowRight size={15} /></button>
        </article>
        <article className="panel span-3 contact-funnel-panel">
          <SectionHead title="Two-stream contact evidence" icon={GitBranch} aside="Reconciled as evidence; never presented as a directory filtering funnel" />
          <div className="evidence-streams compact">
            <article><p className="eyebrow">Source 1 · ConstructConnect directory</p><h2>{g.sourceContacts.funnel.source_directory_rows} occurrences · {g.sourceContacts.funnel.canonical_source_identities} identities</h2><p>Company-history contact data with duplicates, generic contact points, inactive state, and domain ambiguity preserved.</p></article>
            <span className="stream-join"><ArrowRight /><b>Identity / evidence reconciliation</b></span>
            <article><p className="eyebrow">Source 2 · Stafford research</p><h2>{g.sourceContacts.funnel.project_research_candidates} project-specific candidates</h2><p>Doug is the highest investigation priority; rental/equipment authority remains UNKNOWN.</p></article>
          </div>
        </article>
      </section>
      {apolloPreview && <ApolloPreviewPanel d={d} mode={apolloPreview} close={() => setApolloPreview(null)} />}
    </div>
  );
}

function EvidenceTrust({
  d,
  open,
}: {
  d: DashboardData;
  open: (item: Evidence) => void;
}) {
  const confidenceState = titleCase(d.assessment.assessment.confidence_state);
  return (
    <div className="page" data-view="evidence">
      <PageHeader
        eyebrow="Evidence & Trust"
        title={d.project.canonical_name}
        subtitle="Every important conclusion is inspectable through the demo-safe API."
        d={d}
      />
      <section className="evidence-layout">
        <article className="panel evidence-table">
          <SectionHead
            title={`Evidence & observations (${d.evidence.length})`}
            icon={FileSearch}
          />
          <div className="table-scroll">
            <div className="table-head evidence-grid">
              <span>Observation</span>
              <span>Classification</span>
              <span>Confidence</span>
              <span>Treatment</span>
              <span />
            </div>
            {d.evidence.map((item) => (
              <button
                className="evidence-grid"
                key={item.evidence_id}
                onClick={() => open(item)}
              >
                <div>
                  <b>{titleCase(item.field_name)}</b>
                  <small>
                    {item.section_name || "Source"} · page{" "}
                    {item.page_number ?? "?"}
                  </small>
                </div>
                <Pill>{item.classification}</Pill>
                <Pill>{item.confidence_state}</Pill>
                <span>{titleCase(item.scoring_treatment)}</span>
                <ChevronRight size={15} />
              </button>
            ))}
          </div>
        </article>
        <aside className="evidence-aside">
          <article className="panel">
            <SectionHead
              title={`Trust warnings (${d.quality.length})`}
              icon={TriangleAlert}
            />
            {d.quality.map((item) => (
              <div className="trust-warning" key={item.id}>
                <TriangleAlert size={18} />
                <div>
                  <b>{item.title}</b>
                  <p>
                    Severity: {titleCase(item.severity)} · Decision impact:{" "}
                    {titleCase(item.decision_impact || "Not specified")}
                  </p>
                  <small>
                    {item.blocks_progression
                      ? "Blocks progression"
                      : "Does not independently block progression"}
                  </small>
                </div>
              </div>
            ))}
          </article>
          <article className="panel coverage">
            <SectionHead
              title="Evidence quality / completeness"
              icon={Database}
            />
            <div className="coverage-number">
              <b>{confidenceState}</b>
              <span>Current Data Confidence band</span>
            </div>
            <p>
              Independent evidence state; not a probability or Commercial Fit
              score.
            </p>
            <small>
              The internal deterministic score remains available in the
              assessment API for ordering and audit.
            </small>
          </article>
        </aside>
      </section>
    </div>
  );
}

function ProductFit({ d }: { d: DashboardData }) {
  const openQuestions: string[] = Array.from(
    new Set<string>(
      d.assessment.product_fits.flatMap((fit: any): string[] =>
        stringList(fit.missing_evidence),
      ),
    ),
  );
  return (
    <div className="page" data-view="product">
      <PageHeader
        eyebrow="Product Fit"
        title={d.project.canonical_name}
        subtitle="Project characteristics indicate possible relevance; actual product need is not yet confirmed."
        d={d}
      />
      <div className="assessment-disclaimer prominent">
        Deterministic decision support only. Applicability states are not
        verified demand, product specifications, forecasts, or success
        probabilities.
      </div>
      <section className="product-cards">
        {d.assessment.product_fits.map((fit: any) => {
          const questions = stringList(fit.missing_evidence);
          const supportingSignals = stringList(
            fit.matched_signals || fit.supporting_evidence,
          );
          return (
            <article className="panel" key={fit.product_code}>
              <div className="product-heading">
                <span className="feature-icon">
                  <Zap />
                </span>
                <div>
                  <h2>{fit.product_code}</h2>
                  {fit.product_name && fit.product_name !== fit.product_code && (
                    <small className="product-name">{fit.product_name}</small>
                  )}
                  <Pill>{fit.applicability_status}</Pill>
                </div>
                <div className="product-relevance">
                  <strong>
                    {relevanceIndex(fit.characteristic_relevance_score)}
                    <small>/100</small>
                  </strong>
                  <span>Characteristic relevance</span>
                  <em>{relevanceBand(fit.characteristic_relevance_score)}</em>
                </div>
              </div>
              <p>{fit.explanation}</p>
              <small className="relevance-note">
                Deterministic project-characteristic score; not validated
                product fit, demand, forecast, or probability. Applicability
                remains a separate evidence gate.
              </small>
              <div className="context-evidence">
                <b>Project context counted once</b>
                {supportingSignals.length ? (
                  <div>
                    {supportingSignals.map((item) => (
                      <span key={item}>{titleCase(item)}</span>
                    ))}
                  </div>
                ) : (
                  <small>No decision-eligible context signal was counted.</small>
                )}
              </div>
              <div className="question-box">
                <b>Evidence required before fit can be supported</b>
                {questions.length ? (
                  <ul>
                    {questions.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <span>No additional evidence request returned.</span>
                )}
              </div>
            </article>
          );
        })}
      </section>
      <section className="product-grid">
        <article className="panel">
          <SectionHead
            title="Project-characteristic signals"
            icon={GitBranch}
          />
          {d.signals.slice(0, 7).map((item: any) => (
            <div className="signal-matrix" key={item.id}>
              <div>
                <b>{titleCase(item.key)}</b>
                <small>{item.explanation || item.value}</small>
              </div>
              <Pill>{item.classification}</Pill>
            </div>
          ))}
        </article>
        <article className="panel">
          <SectionHead title="What we still need to verify" icon={CircleHelp} />
          {openQuestions.slice(0, 8).map((item) => (
            <div className="question-row" key={item}>
              <CircleHelp size={17} />
              <span>{item}</span>
              <ChevronRight size={15} />
            </div>
          ))}
        </article>
        <article className="panel">
          <SectionHead title="Applicability status" icon={BarChart3} />
          {d.assessment.product_fits.map((fit: any) => (
            <div
              className="comparison-row applicability-row"
              key={fit.product_code}
            >
              <b>{fit.product_code}</b>
              <span>
                Direct need unconfirmed
                <strong>
                  {relevanceIndex(fit.characteristic_relevance_score)}/100 · {relevanceBand(fit.characteristic_relevance_score)}
                </strong>
              </span>
              <Pill>{fit.applicability_status}</Pill>
            </div>
          ))}
        </article>
      </section>
    </div>
  );
}

function ExceptionQueue({ d }: { d: DashboardData }) {
  const [filter, setFilter] = useState("ALL");
  const warnings =
    filter === "ALL"
      ? d.quality
      : d.quality.filter((item) => item.severity.toUpperCase() === filter);
  return (
    <div className="page" data-view="exceptions">
      <PageHeader
        eyebrow="Pipeline Failure & Recovery"
        title="Exception Queue"
        subtitle="Workflow exceptions and evidence-quality warnings are separate operational concepts."
        d={d}
      />
      <section className="score-band four">
        <Metric
          label="Open workflow exceptions"
          value={d.exceptions.count}
          note="Pipeline work records only"
          icon={TriangleAlert}
          kind={d.exceptions.count ? "bad" : "good"}
        />
        <Metric
          label="Quality warnings requiring review"
          value={
            d.quality.filter((item) => item.review_status === "NEEDS_REVIEW")
              .length
          }
          note="Evidence findings, not exceptions"
          icon={Flag}
          kind="warn"
        />
        <Metric
          label="Progression-blocking quality warnings"
          value={d.quality.filter((item) => item.blocks_progression).length}
          icon={LockKeyhole}
          kind="bad"
        />
        <Metric
          label="Resolved today"
          value="N/A"
          note="Resolution history not connected"
          icon={CircleCheck}
          kind="warn"
        />
      </section>
      <section className="panel exception-panel">
        <SectionHead
          title="Workflow exceptions"
          aside={`${d.exceptions.count} current`}
          icon={TriangleAlert}
        />
        {d.exceptions.items.length ? (
          <div className="table-scroll">
            <div className="table-head exception-grid">
              <span>Priority</span>
              <span>Exception</span>
              <span>Reason</span>
              <span>Status</span>
              <span>Next action</span>
            </div>
            {d.exceptions.items.map((item) => (
              <article className="exception-grid" key={item.id}>
                <Pill>{item.priority}</Pill>
                <div>
                  <b>{item.summary}</b>
                  <small>Workflow exception</small>
                </div>
                <span>{item.detail || "No additional detail recorded"}</span>
                <Pill>{item.status}</Pill>
                <span>Follow the recorded resolution action</span>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            title="No open workflow exceptions"
            detail="Quality warnings may still require review below; zero exceptions does not mean the evidence is issue-free."
          />
        )}
      </section>
      <section className="panel exception-panel quality-review-panel">
        <SectionHead
          title="Quality review items"
          aside={`${d.quality.length} current`}
          icon={Flag}
        />
        <div className="filter-bar" aria-label="Quality warning filters">
          {["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"].map((value) => (
            <button
              key={value}
              className={filter === value ? "active" : ""}
              onClick={() => setFilter(value)}
            >
              {titleCase(value)}{" "}
              <span>
                {value === "ALL"
                  ? d.quality.length
                  : d.quality.filter(
                      (item) => item.severity.toUpperCase() === value,
                    ).length}
              </span>
            </button>
          ))}
        </div>
        {warnings.length ? (
          <div className="table-scroll">
            <div className="table-head exception-grid">
              <span>Severity</span>
              <span>Warning</span>
              <span>Decision impact</span>
              <span>Review status</span>
              <span>Next action</span>
            </div>
            {warnings.map((item) => (
              <article className="exception-grid" key={item.id}>
                <Pill>{item.severity}</Pill>
                <div>
                  <b>{item.title}</b>
                  <small>
                    {item.blocks_progression
                      ? "Progression blocker"
                      : "Evidence review"}
                  </small>
                </div>
                <span>
                  {titleCase(item.decision_impact || "Not specified")}:{" "}
                  {item.detail}
                </span>
                <Pill>{item.review_status}</Pill>
                <span>{item.recommended_action}</span>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            title="No quality warnings match this filter"
            detail="Choose another severity filter to continue reviewing evidence findings."
          />
        )}
      </section>
    </div>
  );
}

function crmRequestIdentity(request: CRMRequest) {
  return (
    request.body.name ||
    request.body.title ||
    "Identity not present in this safe preview"
  );
}

function CrmPreview({
  d,
  setView,
  retry,
  retrying,
}: {
  d: DashboardData;
  setView: (view: ViewKey) => void;
  retry: (key: OptionalDependencyKey) => void;
  retrying: OptionalDependencyKey | null;
}) {
  const [syncPreviewOpen, setSyncPreviewOpen] = useState(false);
  if (!d.crm)
    return (
      <div className="page" data-view="crm">
        <PageHeader
          eyebrow="CRM Preview · read-only"
          title="CRM preview unavailable"
          subtitle="Core project intelligence remains available while this optional preview is retried."
          d={d}
        />
        <DegradedPanel
          failure={failureFor(d, "crm_preview", "CRM preview")}
          retry={retry}
          retrying={retrying === "crm_preview"}
        />
      </div>
    );
  return (
    <div className="page" data-view="crm">
      <PageHeader
        eyebrow="CRM Preview · read-only"
        title="CRM Lead record ready · Deal blocked"
        subtitle="Lead-record readiness is not outreach authority or Deal readiness. No data is written to Pipedrive in this preview."
        d={d}
        actions={<div className="button-row"><button className="button primary" onClick={() => setSyncPreviewOpen(true)}><Eye size={16} /> Preview Pipedrive Sync</button><button className="button secondary" disabled title="Blocked: rental authority, site need, rental provider, and fleet buyer remain unresolved"><LockKeyhole size={16} /> Create Deal</button></div>}
      />
      <div className="dry-run-banner">
        <Info size={18} />
        <span>
          <b>DRY RUN PREVIEW</b> — current API state only; external write
          authority remains server-side.
        </span>
        <Pill>{d.crm.pipedrive.mode || "PREVIEW"}</Pill>
      </div>
      <section className="crm-layout">
        <article className="panel readiness">
          <SectionHead title="CRM readiness" icon={PackageCheck} />
          {[
            ["Project qualified", true],
            ["CRM Lead record ready", d.readiness.lead_ready],
            ["Deal ready", d.readiness.deal_ready],
            ["Evidence retained", true],
          ].map(([label, ready]) => (
            <div key={String(label)} className={ready ? "pass" : "blocked"}>
              {ready ? <CircleCheck /> : <TriangleAlert />}
              <div>
                <b>{String(label)}</b>
                <small>
                  {ready
                    ? "Deterministic record gate passed; no outreach sent"
                    : "Commercial validation still required"}
                </small>
              </div>
            </div>
          ))}
          <div className="readiness-outcome">
            <span>Permitted CRM promotion</span>
            <Pill>{d.readiness.permitted_promotion}</Pill>
          </div>
        </article>
        <article className="panel crm-requests">
          <SectionHead title="Pipedrive request preview" icon={Database} />
          <div className="request-grid">
            {d.crm.pipedrive.requests.map((request) => (
              <article key={request.canonical_key || request.label}>
                <div>
                  <Pill>{request.status}</Pill>
                  <span>{titleCase(request.object_type)}</span>
                </div>
                <h3>{request.label}</h3>
                <b>{crmRequestIdentity(request)}</b>
                <p>
                  {request.blocked_reason ||
                    "Validated preview; no live write executed."}
                </p>
                <details>
                  <summary>Inspect request contract and demo-safe body</summary>
                  <dl>
                    <div>
                      <dt>Canonical key</dt>
                      <dd>{request.canonical_key || "Not applicable"}</dd>
                    </div>
                    <div>
                      <dt>Request</dt>
                      <dd>
                        {request.method} {request.path}
                      </dd>
                    </div>
                    <div>
                      <dt>Dependencies</dt>
                      <dd>
                        {request.dependencies.length
                          ? request.dependencies.join(", ")
                          : "None"}
                      </dd>
                    </div>
                  </dl>
                  <pre>{JSON.stringify(request.body, null, 2)}</pre>
                  <small>
                    Canonical keys make an authorized retry idempotent; this
                    preview performs no retry or write.
                  </small>
                </details>
              </article>
            ))}
          </div>
        </article>
        <aside className="crm-aside">
          <article className="panel blocker-panel">
            <SectionHead
              title="Why Deal creation is blocked"
              icon={LockKeyhole}
            />
            {d.readiness.deal_blockers.map((item) => (
              <div className="blocker" key={item}>
                <TriangleAlert size={16} />
                <b>{titleCase(item)}</b>
              </div>
            ))}
            <button
              className="button secondary"
              onClick={() => setView("contacts")}
            >
              Open Contact Resolution
            </button>
          </article>
          <article className="panel">
            <SectionHead title="Duplicate prevention" icon={ShieldCheck} />
            <div className="success-callout">
              <CircleCheck />
              <span>No live duplicates can be created in dry-run mode.</span>
            </div>
            <div className="safety">
              <div>
                <span>External writes</span>
                <b>{String(d.crm.external_writes_executed)}</b>
              </div>
              <div>
                <span>Mode</span>
                <Pill>{d.crm.pipedrive.mode || "PREVIEW"}</Pill>
              </div>
            </div>
          </article>
        </aside>
      </section>
      {syncPreviewOpen && <div className="drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setSyncPreviewOpen(false); }}><aside className="drawer" role="dialog" aria-modal="true" aria-label="Pipedrive sync preview"><button className="icon-button drawer-close" onClick={() => setSyncPreviewOpen(false)} aria-label="Close Pipedrive preview"><X /></button><p className="eyebrow">Pipedrive sync preview</p><h2>Demo mode · validated preview</h2><div className="dry-run-banner"><Info size={17} /><span><b>EXTERNAL WRITES: {d.crm.external_writes_executed}</b> · execution remains disabled</span><Pill>DRY_RUN</Pill></div><dl className="detail-grid"><div><dt>Project</dt><dd>{d.project.canonical_name}</dd></div><div><dt>Organization</dt><dd>{d.organization?.canonical_name || "Unresolved"}</dd></div><div><dt>Permitted promotion</dt><dd>{titleCase(d.readiness.permitted_promotion)}</dd></div><div><dt>Deal</dt><dd>BLOCKED</dd></div></dl><h3>Dependency-ordered requests</h3><div className="preview-request-list">{d.crm.pipedrive.requests.map((request, index) => <article key={request.canonical_key || request.label}><span>{index + 1}</span><div><b>{titleCase(request.object_type)} · {request.label}</b><small>{request.method} {request.path}</small><small>Canonical key: {request.canonical_key || "Not applicable"}</small></div><Pill>{request.status}</Pill></article>)}</div><h3>Deal blockers</h3><ul className="blocked-list">{d.readiness.deal_blockers.map((item) => <li key={item}>{titleCase(item)}</li>)}</ul><p className="assessment-disclaimer">The source-reported project value is excluded from Deal value. This preview creates, updates, or resolves nothing.</p></aside></div>}
    </div>
  );
}

function CommercialMotion({
  d,
  setView,
}: {
  d: DashboardData;
  setView: (view: ViewKey) => void;
}) {
  return (
    <div className="page" data-view="commercial">
      <PageHeader
        eyebrow="Commercial Motion"
        title="Stafford opportunity"
        subtitle="Contractor demand and rental-house supply are linked, but they remain separate motions."
        d={d}
      />
      <section className="motion-paths">
        {d.motions.items.map((motion) => {
          const contractor = motion.motion_type === "CONTRACTOR";
          return (
            <article className="panel" key={motion.id}>
              <SectionHead
                title={
                  contractor
                    ? "Contractor demand motion"
                    : "Rental house / fleet motion"
                }
                icon={contractor ? Building2 : Handshake}
              />
              <div className="motion-flow neutral-map">
                {motion.dependency_map.map((step, index) => (
                  <div key={step.source}>
                    <span className={tone(step.state)}>{index + 1}</span>
                    <b>{step.label}</b>
                    <Pill>{step.state}</Pill>
                    {index < motion.dependency_map.length - 1 && <ArrowRight />}
                  </div>
                ))}
              </div>
              <div className="motion-status">
                <Pill>{motion.status}</Pill>
                <Pill>{motion.confidence_state}</Pill>
                <p>{motion.summary}</p>
              </div>
            </article>
          );
        })}
      </section>
      <section className="commercial-grid">
        <article className="panel">
          <SectionHead title="Current motion state" icon={Gauge} />
          {d.motions.items.map((motion) => (
            <div className="motion-meter" key={motion.id}>
              <div>
                <b>{titleCase(motion.motion_type)} motion</b>
                <Pill>{motion.status}</Pill>
              </div>
              <small>{motion.demand_display}</small>
            </div>
          ))}
        </article>
        <article className="panel">
          <SectionHead title="Decision support" icon={Lightbulb} />
          <ul className="check-list">
            <li>EE Reed is the supported general contractor relationship.</li>
            <li>
              Current project characteristics support contractor-first
              investigation.
            </li>
            <li>
              Rental partner, authority, and current product need remain
              unresolved.
            </li>
            <li>Deal progression cannot outrun verified dependencies.</li>
          </ul>
        </article>
        <article className="panel">
          <SectionHead title="Next commercial actions" icon={Target} />
          {d.actions.items.slice(0, 6).map((item, index) => (
            <div className="ranked-action compact" key={item.id}>
              <span>{index + 1}</span>
              <div>
                <b>{titleCase(item.action_type)}</b>
                <p>{item.reason}</p>
              </div>
              <Pill>{item.status}</Pill>
            </div>
          ))}
        </article>
        <article className="panel span-2">
          <SectionHead
            title="Why contractor-side validation comes first"
            icon={CircleCheck}
          />
          <div className="proof-grid">
            <span>
              <Check />
              Supported GC relationship
            </span>
            <span>
              <Check />
              Active project evidence
            </span>
            <span>
              <Check />
              Project-characteristic relevance signals
            </span>
            <span>
              <Check />
              Dependency-aware actions
            </span>
            <span>
              <TriangleAlert />
              Rental authority unresolved
            </span>
            <span>
              <TriangleAlert />
              Current lighting/power need unresolved
            </span>
          </div>
        </article>
        <article className="panel">
          <SectionHead
            title="Canonical first-call kit"
            aside={d.actions.first_call_kit.version}
            icon={MessageSquareText}
          />
          <ol className="numbered-list">
            {d.actions.first_call_kit.questions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        </article>
        <article className="panel">
          <SectionHead title="Commercial handoff" icon={Handshake} />
          <button className="handoff-link" onClick={() => setView("crm")}>
            <PackageCheck />
            CRM Preview <ArrowRight />
          </button>
          <button className="handoff-link" onClick={() => setView("monday")}>
            <CalendarDays />
            Monday Brief <ArrowRight />
          </button>
        </article>
      </section>
    </div>
  );
}

function OpenAIStatus({ d }: { d: DashboardData }) {
  const state = d.systemReadiness?.integrations?.openai;
  const label = !d.systemReadiness
    ? "Readiness unavailable"
    : !state?.enabled
      ? "OpenAI disabled"
      : state.credentials_present
        ? "OpenAI enabled"
        : "OpenAI unavailable";
  return <Pill>{label}</Pill>;
}

function Analyst({
  d,
  retry,
  retrying,
}: {
  d: DashboardData;
  retry: (key: OptionalDependencyKey) => void;
  retrying: OptionalDependencyKey | null;
}) {
  const questions = [
    "Why pursue Stafford?",
    "What data should I not trust?",
    "What would change the recommendation?",
    "Who should we investigate first?",
    "What is blocking Pipedrive?",
    "Which product appears strongest?",
    "What should I ask on the first call?",
  ];
  const [question, setQuestion] = useState(questions[0]);
  const [response, setResponse] = useState<AnalystResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState("FAST");
  const [conversation, setConversation] = useState<any[]>([]);
  const answer = response?.answer as any;
  const readinessFailure = d.optionalFailures.analyst_readiness;
  async function submit(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    try {
      const next = await askAnalyst(d.project.id, question, mode, conversation);
      setResponse(next);
      if (
        next.answer &&
        ["SUCCEEDED", "PARTIAL_VALIDATED"].includes(String(next.status))
      )
        setConversation((rows) =>
          [
            ...rows,
            {
              question,
              answer: next.answer!.direct_conclusion,
              claim_ids:
                next.answer!.claims?.map((claim) => claim.claim_id) || [],
            },
          ].slice(-4),
        );
    } catch (error) {
      setResponse({
        status: "ERROR",
        fallback_reason:
          error instanceof Error ? error.message : "Request failed",
        external_request_executed: false,
      });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page" data-view="analyst">
      <PageHeader
        eyebrow="Commercial Analyst"
        title="Evidence-grounded answers"
        subtitle="Read-only analysis preserves unknowns and cannot mutate deterministic truth."
        d={d}
      />
      <div className="analyst-status">
        <OpenAIStatus d={d} />
        <Pill>Grounded mode on</Pill>
        <Pill>Read-only</Pill>
        <Pill>Demo mode</Pill>
      </div>
      {readinessFailure && (
        <DegradedPanel
          failure={readinessFailure}
          retry={retry}
          retrying={retrying === "analyst_readiness"}
        />
      )}
      <section className="analyst-layout">
        <article className="panel analyst-conversation">
          <SectionHead title="Analyst conversation" icon={MessageSquareText} />
          <form onSubmit={submit}>
            <label htmlFor="analyst-question">Ask about Stafford</label>
            <div className="analyst-controls">
              <div className="ask">
                <input
                  id="analyst-question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  disabled={busy}
                />
                <button
                  className="button primary"
                  disabled={busy || question.trim().length < 3}
                >
                  {busy ? <RefreshCw className="spin" /> : <Sparkles />}
                  {busy ? "Analyzing…" : "Ask"}
                </button>
              </div>
              <div className="mode-switch" aria-label="Analysis mode">
                {[
                  ["FAST", "Terra · fast"],
                  ["STANDARD", "Sol · standard"],
                  ["DEEP", "Sol · deep"],
                ].map(([key, label]) => (
                  <button
                    type="button"
                    className={mode === key ? "active" : ""}
                    onClick={() => setMode(key)}
                    key={key}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </form>
          {response ? (
            <div className="answer" aria-live="polite">
              <div className="answer-status">
                <Pill>{response.status}</Pill>
                <span>
                  {response.external_request_executed
                    ? "OpenAI request executed"
                    : response.cache_hit
                      ? "Validated answer cache"
                      : "Deterministic fallback"}
                </span>
                {response.model_id && <span>{response.model_id}</span>}
                {response.grounding?.status && (
                  <Pill>{response.grounding.status} grounding</Pill>
                )}
              </div>
              {answer ? (
                <div className="analyst-result">
                  <h3>{answer.direct_conclusion || "Analyst answer"}</h3>
                  <p className="analyst-answer-copy">
                    {typeof answer === "string" ? answer : answer.answer}
                  </p>
                  {Array.isArray(answer.claims) && answer.claims.length > 0 && (
                    <section className="analyst-claims">
                      <h4>Validated claims and rationale</h4>
                      {answer.claims.map((claim: any) => (
                        <details key={claim.claim_id}>
                          <summary>
                            <Pill>{claim.classification}</Pill>
                            <span>{claim.claim_text}</span>
                          </summary>
                          <p>{claim.rationale}</p>
                          <small>
                            {claim.evidence_ids?.length || 0} cited evidence
                            record{claim.evidence_ids?.length === 1 ? "" : "s"}:{" "}
                            {claim.evidence_ids?.join(", ")}
                          </small>
                        </details>
                      ))}
                    </section>
                  )}
                  {Array.isArray(answer.decision_changing_unknowns) &&
                    answer.decision_changing_unknowns.length > 0 && (
                      <section className="analyst-unknowns">
                        <h4>Decision-changing unknowns</h4>
                        <ul>
                          {answer.decision_changing_unknowns.map(
                            (item: string) => (
                              <li key={item}>{item}</li>
                            ),
                          )}
                        </ul>
                      </section>
                    )}
                  <div className="answer-foot">
                    <span>
                      {response.tool_rounds || 0} read-only tool round(s) ·{" "}
                      {response.latency_ms || 0} ms
                    </span>
                    <span>
                      Estimated request cost $
                      {response.estimated_cost_usd || "0"}
                    </span>
                  </div>
                </div>
              ) : (
                <div className="fallback-answer">
                  <h3>Deterministic system remains available.</h3>
                  <p>
                    {response.fallback_reason ||
                      "The optional model is unavailable; core intelligence remains operational."}
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="answer placeholder">
              <Sparkles size={28} />
              <h3>Try a CEO-style challenge.</h3>
              <p>
                The analyst uses a compact current-state packet and only
                displays validated claims. Follow-up context stays sanitized in
                this browser session.
              </p>
            </div>
          )}
        </article>
        <aside className="analyst-aside">
          <article className="panel">
            <SectionHead title="Suggested questions" icon={CircleHelp} />
            {questions.map((item) => (
              <button
                className={question === item ? "active" : ""}
                key={item}
                onClick={() => setQuestion(item)}
              >
                <Target size={15} />
                <span>{item}</span>
                <ChevronRight size={15} />
              </button>
            ))}
          </article>
          <article className="panel guardrails">
            <SectionHead title="Analyst guardrails" icon={ShieldCheck} />
            <span>
              <LockKeyhole />
              No external writes
            </span>
            <span>
              <FileSearch />
              Validated evidence required
            </span>
            <span>
              <CircleHelp />
              Unknowns preserved
            </span>
            <span>
              <PackageCheck />
              CRM gates stay deterministic
            </span>
          </article>
        </aside>
      </section>
    </div>
  );
}

function MondayBrief({
  d,
  setView,
  retry,
  retrying,
}: {
  d: DashboardData;
  setView: (view: ViewKey) => void;
  retry: (key: OptionalDependencyKey) => void;
  retrying: OptionalDependencyKey | null;
}) {
  const monday = d.monday;
  if (!monday)
    return (
      <div className="page" data-view="monday">
        <PageHeader
          eyebrow="Executive operating rhythm"
          title="Monday Morning Brief"
          subtitle="Core project intelligence remains available while this optional brief is retried."
          d={d}
        />
        <DegradedPanel
          failure={failureFor(d, "monday_brief", "Monday Morning Brief")}
          retry={retry}
          retrying={retrying === "monday_brief"}
        />
      </div>
    );
  const pipeline = Object.entries(monday.pipeline);
  const a = d.assessment.assessment;
  return (
    <div className="page" data-view="monday">
      <PageHeader
        eyebrow="Executive operating rhythm"
        title="Monday Morning Brief"
        subtitle="A truthful weekly view of pipeline, opportunity, and attention required."
        d={d}
      />
      <section className="headline-kpi">
        <span className="kpi-icon">
          <BarChart3 />
        </span>
        <div>
          <p className="eyebrow">Headline KPI</p>
          <h2>{monday.primary_kpi.name}</h2>
        </div>
        <strong>{monday.primary_kpi.display}</strong>
        <p>{monday.primary_kpi.interpretation}</p>
        <Pill>
          {monday.primary_kpi.status === "AVAILABLE"
            ? "Available"
            : "Not connected"}
        </Pill>
      </section>
      <section className="pipeline-band">
        {pipeline.map(([key, value], index) => (
          <div key={key}>
            <span className="pipeline-icon">
              {index === pipeline.length - 1 ? (
                <CalendarDays />
              ) : index < 2 ? (
                <Database />
              ) : (
                <UsersRound />
              )}
            </span>
            <span>
              <b>{metricLabel(monday.metric_definitions, key)}</b>
              <strong>{String(value)}</strong>
            </span>
            {index < pipeline.length - 1 && <ChevronRight />}
          </div>
        ))}
      </section>
      <p className="pipeline-semantics">{monday.pipeline_semantics}</p>
      <section className="monday-grid">
        <article className="panel top-opportunity">
          <SectionHead title="Top opportunity" icon={Building2} />
          <h2>
            {monday.top_opportunity?.name || "No qualified opportunity"}
          </h2>
          {monday.top_opportunity ? (
            <>
              <div className="context-line">
                <MapPin size={14} />
                {d.project.city}, {d.project.region}
                <span>•</span>
                {titleCase(d.project.stage)}
              </div>
              <div className="twoscores">
                <div>
                  <span>Commercial fit</span>
                  <b>{a.overall_band}</b>
                </div>
                <div>
                  <span>Data confidence</span>
                  <b>{titleCase(a.confidence_state)}</b>
                </div>
              </div>
              <Pill>{a.operational_action}</Pill>
              <p className="assessment-disclaimer">
                Deterministic decision support; not a probability or validated
                demand.
              </p>
              <button
                className="text-button"
                onClick={() => setView("project")}
              >
                View full intelligence <ArrowRight size={15} />
              </button>
            </>
          ) : (
            <Empty
              title="No opportunity returned"
              detail="The backend has no current top opportunity."
            />
          )}
        </article>
        <article className="panel attention">
          <SectionHead title="Attention required" icon={TriangleAlert} />
          {monday.attention_required.length
            ? monday.attention_required.map((item) => (
                <div className="attention-row" key={item.id}>
                  <span className="alert-icon">
                    <TriangleAlert size={16} />
                  </span>
                  <div>
                    <b>{item.summary}</b>
                    <small>{item.recommended_action}</small>
                  </div>
                  <Pill>{item.status}</Pill>
                  <span>P{item.priority}</span>
                </div>
              ))
            : d.quality.map((item) => (
                <div className="attention-row" key={item.id}>
                  <span className="alert-icon">
                    <TriangleAlert size={16} />
                  </span>
                  <div>
                    <b>{item.title}</b>
                    <small>{item.recommended_action}</small>
                  </div>
                  <Pill>{item.review_status}</Pill>
                  <span>{titleCase(item.severity)}</span>
                </div>
              ))}
          <button className="text-button" onClick={() => setView("exceptions")}>
            View exception queue <ArrowRight size={15} />
          </button>
        </article>
        <article className="panel weekly">
          <SectionHead title="Current demo snapshot" icon={BarChart3} />
          {pipeline.map(([key, value]) => (
            <div className="weekly-row" key={key}>
              <span className="row-icon">
                <CircleCheck size={16} />
              </span>
              <b>{metricLabel(monday.metric_definitions, key)}</b>
              <strong>{String(value)}</strong>
            </div>
          ))}
          <p className="note">{monday.pipeline_semantics}</p>
        </article>
      </section>
    </div>
  );
}

function First14Days() {
  const phases = [
    [
      "Days 1–2",
      "Validate the commercial workflow with people",
      "Inspect ConstructConnect and Apollo/Pipedrive fields, observe copy/paste, speak with users, identify who owns rental decisions, validate the contractor/rental-house path, and agree the KPI feedback loop.",
      "Validated current-state map",
      "Unconfirmed human assumptions",
    ],
    [
      "Days 3–4",
      "Define canonical project, company, and contact identity",
      "Lock keys, precedence, and non-destructive resolution rules.",
      "Field mapping matrix",
      "Inconsistent definitions",
    ],
    [
      "Days 5–6",
      "Build the Stafford and EE Reed golden path",
      "Validate qualification, evidence, and employer questions.",
      "Golden path",
      "Overfitting rules",
    ],
    [
      "Days 7–8",
      "Layer in contact resolution and verification",
      "Separate employment, project, role, and authority state.",
      "Verification checklist",
      "Incomplete sources",
    ],
    [
      "Days 9–10",
      "Add CRM preview and duplicate protection",
      "Exercise Lead/Deal gates and idempotent dry runs.",
      "CRM preview",
      "Data hygiene",
    ],
    [
      "Days 11–12",
      "Stand up reporting and exception rhythm",
      "Make quality warnings and ownership visible.",
      "Monday brief",
      "Manual-step creep",
    ],
    [
      "Days 13–14",
      "Validate, document, and prepare handoff",
      "Run the complete release matrix and preserve evidence.",
      "Reproducible handoff",
      "Scope creep",
    ],
  ];
  return (
    <div className="page" data-view="roadmap">
      <PageHeader
        eyebrow="First 14 Days"
        title="No-help, existing-tools plan"
        subtitle="Connect qualification, contact resolution, CRM readiness, and review cadence without inventing new production capability."
      />
      <div className="objective-banner">
        <Target />
        <span>
          <b>Objective:</b> fix the handoffs first, preserve truth boundaries,
          and use existing approved tools.
        </span>
      </div>
      <section className="roadmap-layout">
        <article className="panel roadmap-table">
          <div className="roadmap-head">
            <span>Two-week roadmap</span>
            <span>Deliverable</span>
            <span>Risk to manage</span>
            <span>Expected output</span>
          </div>
          {phases.map(([days, title, detail, output, risk], index) => (
            <div className="roadmap-row" key={days}>
              <span className="roadmap-step">{index + 1}</span>
              <div>
                <small>{days}</small>
                <b>{title}</b>
                <p>{detail}</p>
              </div>
              <span>
                <CircleCheck />
                {output}
              </span>
              <span>
                <TriangleAlert />
                {risk}
              </span>
              <span>
                <PackageCheck />
                {output}
              </span>
            </div>
          ))}
        </article>
        <aside>
          <article className="panel">
            <SectionHead title="What this plan uses" icon={PackageCheck} />
            <div className="tool-list">
              <span>
                <Database />
                ConstructConnect <small>Project and source records</small>
              </span>
              <span>
                <UsersRound />
                Contact research <small>Evidence-gated investigation</small>
              </span>
              <span>
                <PackageCheck />
                Pipedrive preview <small>Readiness and duplicate safety</small>
              </span>
              <span>
                <BarChart3 />
                Reporting <small>Truthful operating rhythm</small>
              </span>
            </div>
          </article>
          <article className="panel not-doing">
            <SectionHead title="What it does not do" icon={TriangleAlert} />
            <ul>
              <li>No fabricated telemetry or outcomes</li>
              <li>No automatic consequential outreach</li>
              <li>No blind CRM synchronization</li>
              <li>No authority claims without evidence</li>
              <li>No hidden dependency on chat history</li>
            </ul>
          </article>
        </aside>
      </section>
      <section className="success-band">
        <b>Success by day 14</b>
        {[
          "Stafford answer reproducible",
          "EE Reed risks visible",
          "First-call kit usable",
          "Lead preview ready",
          "Weekly KPI defined",
          "Exception rhythm established",
        ].map((item) => (
          <span key={item}>
            <CircleCheck />
            {item}
          </span>
        ))}
      </section>
    </div>
  );
}

function Sidebar({
  view,
  navigate,
  startGuide,
  open,
  close,
}: {
  view: ViewKey;
  navigate: (view: ViewKey) => void;
  startGuide: () => void;
  open: boolean;
  close: () => void;
}) {
  return (
    <>
      <aside
        className={`sidebar ${open ? "open" : ""}`}
        aria-label="Primary navigation"
      >
        <div className="sidebar-top">
          <Logo />
          <button
            className="icon-button sidebar-close"
            onClick={close}
            aria-label="Close navigation"
          >
            <X />
          </button>
        </div>
        <button
          className={`guide-button ${view === "guided" ? "active" : ""}`}
          onClick={() => navigate("guided")}
          aria-label="Guided CEO Review"
        >
          <Sparkles size={20} />
          <span>
            <b>Guided CEO Review</b>
            <small>Six-question walkthrough</small>
          </span>
        </button>
        {(["Data", "Decide", "Resolve", "Act", "Explain"] as const).map((group) => (
          <nav key={group} aria-label={group}>
            <span className="nav-group">{group}</span>
            {nav
              .filter((item) => item.group === group)
              .map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    title={item.label}
                    aria-label={item.label}
                    aria-current={view === item.key ? "page" : undefined}
                    className={view === item.key ? "active" : ""}
                    key={item.key}
                    onClick={() => navigate(item.key)}
                  >
                    <Icon size={19} />
                    <span>{item.label}</span>
                    {item.key === "exceptions" && <i>!</i>}
                  </button>
                );
              })}
          </nav>
        ))}
        <footer>
          <div>
            <Database size={18} />
            <span>
              <small>Source posture</small>
              <b>DEMO SAFE</b>
            </span>
          </div>
          <p>No raw PDFs or external writes. Private paths stay hidden.</p>
          <button onClick={startGuide}>
            Start guided review <ArrowRight size={14} />
          </button>
        </footer>
      </aside>
      {open && (
        <button
          className="sidebar-scrim"
          onClick={close}
          aria-label="Close navigation overlay"
        />
      )}
    </>
  );
}

function UtilityBar({
  view,
  navigate,
  openNav,
}: {
  view: ViewKey;
  navigate: (view: ViewKey) => void;
  openNav: () => void;
}) {
  const [query, setQuery] = useState("");
  const matches = useMemo(
    () =>
      query.trim()
        ? nav.filter((item) =>
            item.label.toLowerCase().includes(query.trim().toLowerCase()),
          )
        : [],
    [query],
  );
  return (
    <header className="utility-bar">
      <button
        className="mobile-menu icon-button"
        onClick={openNav}
        aria-label="Open navigation"
      >
        <Menu />
      </button>
      <div className="mobile-logo">
        <Logo />
      </div>
      <div className="search-box">
        <Search size={18} />
        <label className="sr-only" htmlFor="global-search">
          Search application views
        </label>
        <input
          id="global-search"
          placeholder="Search application views…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && matches[0]) {
              navigate(matches[0].key);
              setQuery("");
            }
          }}
        />
        {query && (
          <div className="search-results">
            {matches.length ? (
              matches.map((item) => (
                <button
                  key={item.key}
                  onClick={() => {
                    navigate(item.key);
                    setQuery("");
                  }}
                >
                  {item.label}
                  <ArrowRight size={14} />
                </button>
              ))
            ) : (
              <span>No matching application view</span>
            )}
          </div>
        )}
      </div>
      <div className="utility-actions">
        <Pill>Demo mode</Pill>
        <button
          className="icon-button"
          aria-label="Notifications unavailable"
          title="No live notification service"
          disabled
        >
          <Bell size={19} />
        </button>
        <button
          className="icon-button"
          aria-label="Open Guided CEO Review help"
          title="Open Guided CEO Review"
          onClick={() => navigate("guided")}
        >
          <CircleHelp size={19} />
        </button>
        <div className="account-button" aria-label="Demo account identity">
          <span>OG</span>
          <b>Off Grid</b>
        </div>
      </div>
      <span className="sr-only" aria-live="polite">
        Current view: {view}
      </span>
    </header>
  );
}

function GuidedBar({
  index,
  move,
  exit,
}: {
  index: number;
  move: (delta: number) => void;
  exit: () => void;
}) {
  const step = guided[index];
  return (
    <aside className="guided-bar" aria-label="Guided CEO Review progress">
      <div>
        <span>{step.q}</span>
        <b>{step.title}</b>
        <p>{step.focus}</p>
        <div className="guide-progress">
          {guided.map((_, itemIndex) => (
            <i className={itemIndex <= index ? "on" : ""} key={itemIndex} />
          ))}
        </div>
      </div>
      <div>
        <button className="button ghost" onClick={exit}>
          Exit
        </button>
        <button
          className="button ghost"
          disabled={index === 0}
          onClick={() => move(-1)}
        >
          Back
        </button>
        {index < guided.length - 1 ? (
          <button className="button primary" onClick={() => move(1)}>
            Next <ArrowRight size={16} />
          </button>
        ) : (
          <button className="button primary" onClick={exit}>
            Complete review <Check size={16} />
          </button>
        )}
      </div>
    </aside>
  );
}

function parseView(): ViewKey {
  const key = window.location.hash.replace(/^#\/?/, "") as ViewKey;
  return key === "guided" || nav.some((item) => item.key === key)
    ? key
    : "command";
}

function Frame({
  d,
  g,
  retry,
  retrying,
}: {
  d: DashboardData;
  g: GeneralizationData;
  retry: (key: OptionalDependencyKey) => void;
  retrying: OptionalDependencyKey | null;
}) {
  const [view, setView] = useState<ViewKey>(parseView);
  const featuredProject = g.portfolio.items.find((project) => project.featured_case) || g.portfolio.items[0];
  const [selectedProjectId, setSelectedProjectId] = useState(featuredProject?.id || d.project.id);
  const selectedProject = g.portfolio.items.find((project) => project.id === selectedProjectId) || featuredProject;
  const selectedIsFeatured = Boolean(selectedProject?.featured_case || selectedProject?.id === d.project.id);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const [guideIndex, setGuideIndex] = useState(0);
  const [navOpen, setNavOpen] = useState(false);
  useEffect(() => {
    const handler = () => setView(parseView());
    window.addEventListener("hashchange", handler);
    return () => window.removeEventListener("hashchange", handler);
  }, []);
  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 821px)");
    const closeOnDesktop = (event: MediaQueryListEvent) => {
      if (event.matches) setNavOpen(false);
    };
    if (desktop.matches) setNavOpen(false);
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);
  useEffect(() => {
    if (!navOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setNavOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      document.body.style.overflow = "";
    };
  }, [navOpen]);
  useEffect(() => {
    window.scrollTo({ top: 0 });
    document.title = `${view === "guided" ? "Guided CEO Review" : nav.find((item) => item.key === view)?.label || "Off Grid"} · Off Grid`;
  }, [view]);
  function navigate(next: ViewKey) {
    setView(next);
    setNavOpen(false);
    setEvidence(null);
    window.history.replaceState(null, "", `#/${next}`);
  }
  function startGuide() {
    if (featuredProject) setSelectedProjectId(featuredProject.id);
    setGuideIndex(0);
    setGuideOpen(true);
    navigate(guided[0].view);
  }
  function moveGuide(delta: number) {
    const next = Math.max(0, Math.min(guided.length - 1, guideIndex + delta));
    setGuideIndex(next);
    navigate(guided[next].view);
  }
  let body: ReactNode;
  switch (view) {
    case "portfolio":
      body = <ProjectPortfolio g={g} selectedProjectId={selectedProjectId} openProject={(project) => { setSelectedProjectId(project.id); navigate("project"); }} />;
      break;
    case "source":
      body = <SourceExplorer g={g} />;
      break;
    case "guided":
      body = <GuidedReview d={d} start={startGuide} setView={navigate} />;
      break;
    case "command":
      body = <CommandCenter d={d} setView={navigate} retry={retry} retrying={retrying} />;
      break;
    case "project":
      body = selectedIsFeatured || !selectedProject ? <ProjectIntelligence d={d} open={setEvidence} setView={navigate} /> : <SourceOnlyProject project={selectedProject} />;
      break;
    case "account":
      body = <AccountIntelligence d={d} g={g} setView={navigate} />;
      break;
    case "contacts":
      body = selectedIsFeatured || !selectedProject ? <ContactResolution d={d} g={g} setView={navigate} /> : <UnavailableProjectLayer project={selectedProject} navigate={navigate} />;
      break;
    case "evidence":
      body = selectedIsFeatured || !selectedProject ? <EvidenceTrust d={d} open={setEvidence} /> : <UnavailableProjectLayer project={selectedProject} navigate={navigate} />;
      break;
    case "product":
      body = selectedIsFeatured || !selectedProject ? <ProductFit d={d} /> : <UnavailableProjectLayer project={selectedProject} navigate={navigate} />;
      break;
    case "exceptions":
      body = <ExceptionQueue d={d} />;
      break;
    case "crm":
      body = selectedIsFeatured || !selectedProject ? <CrmPreview d={d} setView={navigate} retry={retry} retrying={retrying} /> : <UnavailableProjectLayer project={selectedProject} navigate={navigate} />;
      break;
    case "commercial":
      body = selectedIsFeatured || !selectedProject ? <CommercialMotion d={d} setView={navigate} /> : <UnavailableProjectLayer project={selectedProject} navigate={navigate} />;
      break;
    case "analyst":
      body = selectedIsFeatured || !selectedProject ? <Analyst d={d} retry={retry} retrying={retrying} /> : <UnavailableProjectLayer project={selectedProject} navigate={navigate} />;
      break;
    case "monday":
      body = <MondayBrief d={d} setView={navigate} retry={retry} retrying={retrying} />;
      break;
    default:
      body = <First14Days />;
  }
  return (
    <div className="app-shell">
      <Sidebar
        view={view}
        navigate={navigate}
        startGuide={startGuide}
        open={navOpen}
        close={() => setNavOpen(false)}
      />
      <div className="workspace">
        <UtilityBar
          view={view}
          navigate={navigate}
          openNav={() => setNavOpen(true)}
        />
        <main className="content" id="main-content">
          {body}
        </main>
      </div>
      {guideOpen && (
        <GuidedBar
          index={guideIndex}
          move={moveGuide}
          exit={() => setGuideOpen(false)}
        />
      )}{" "}
      {evidence && (
        <EvidenceDrawer item={evidence} close={() => setEvidence(null)} />
      )}
    </div>
  );
}

export function App() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [generalization, setGeneralization] = useState<GeneralizationData | null>(null);
  const [error, setError] = useState<{
    status: number | null;
    requestId: string | null;
  } | null>(null);
  const [retrying, setRetrying] = useState<OptionalDependencyKey | null>(null);
  useEffect(() => {
    let live = true;
    loadInitialApplication()
      .then(({ dashboard, generalization: generalized }) => {
        if (!live) return;
        setData(dashboard);
        setGeneralization(generalized);
      })
      .catch((reason) => {
        if (!live) return;
        const safe =
          reason instanceof ApiRequestError ? reason : new ApiRequestError(null);
        setError({ status: safe.status, requestId: safe.requestId });
      });
    return () => {
      live = false;
    };
  }, []);

  async function retry(key: OptionalDependencyKey) {
    if (!data || retrying) return;
    setRetrying(key);
    try {
      setData(await retryOptionalDependency(data, key));
    } finally {
      setRetrying(null);
    }
  }

  if (error) {
    return (
      <main className="boot-state">
        <div className="boot-logo">
          <Logo />
        </div>
        <span className="boot-icon bad">
          <TriangleAlert />
        </span>
        <p className="eyebrow">Backend unavailable</p>
        <h1>The application will not invent replacement data.</h1>
        <p>Core project intelligence could not be loaded. Retry when the service is available.</p>
        {error.requestId && <small>Request ID: {error.requestId}</small>}
        <button
          className="button primary"
          onClick={() => window.location.reload()}
        >
          <RefreshCw />
          Try again
        </button>
      </main>
    );
  }
  if (!data || !generalization)
    return (
      <main className="boot-state">
        <div className="boot-logo">
          <Logo />
        </div>
        <span className="spinner" />
        <p className="eyebrow">Loading trusted commercial state</p>
        <h1>Stafford → evidence → action</h1>
        <p>Fetching the current API instead of hard-coding a dashboard.</p>
      </main>
    );
  return <Frame d={data} g={generalization} retry={retry} retrying={retrying} />;
}
