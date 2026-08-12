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
import { type FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { askAnalyst, loadDashboard } from "./api";
import { money, score, titleCase } from "./format";
import type { AnalystResponse, DashboardData, Evidence } from "./types";

type ViewKey =
  | "guided"
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

type NavItem = { key: ViewKey; label: string; group: "Decide" | "Resolve" | "Act" | "Explain"; icon: LucideIcon };

const nav: NavItem[] = [
  { key: "command", label: "Command Center", group: "Decide", icon: LayoutDashboard },
  { key: "project", label: "Project Intelligence", group: "Decide", icon: BarChart3 },
  { key: "account", label: "Account Intelligence", group: "Resolve", icon: Building2 },
  { key: "contacts", label: "Contact Resolution", group: "Resolve", icon: UsersRound },
  { key: "evidence", label: "Evidence & Trust", group: "Resolve", icon: ShieldCheck },
  { key: "product", label: "Product Fit", group: "Resolve", icon: Box },
  { key: "exceptions", label: "Exception Queue", group: "Act", icon: TriangleAlert },
  { key: "crm", label: "CRM Preview", group: "Act", icon: PackageCheck },
  { key: "commercial", label: "Commercial Motion", group: "Act", icon: Workflow },
  { key: "analyst", label: "Commercial Analyst", group: "Explain", icon: MessageSquareText },
  { key: "monday", label: "Monday Morning Brief", group: "Explain", icon: CalendarDays },
  { key: "roadmap", label: "First 14 Days", group: "Explain", icon: Flag },
];

const guided = [
  { q: "Question 1", title: "Is Stafford worth pursuing?", view: "project" as ViewKey, focus: "Validate commercial fit, source confidence, timing, and product relevance.", icon: Target },
  { q: "Question 2", title: "Who should we contact?", view: "contacts" as ViewKey, focus: "Investigate people while keeping rental authority explicitly unverified.", icon: UsersRound },
  { q: "Question 3", title: "What stands out in EE Reed?", view: "account" as ViewKey, focus: "Review recurrence, entity quality, domains, duplicates, and generic inboxes.", icon: Building2 },
  { q: "Question 4", title: "Where does the pipeline break?", view: "exceptions" as ViewKey, focus: "Surface source-quality risks and dependency-blocked progression.", icon: TriangleAlert },
  { q: "Question 5", title: "What matters Monday morning?", view: "monday" as ViewKey, focus: "Lead with the intended KPI while clearly preserving the current N/A state.", icon: BarChart3 },
  { q: "Question 6", title: "What happens in the first two weeks?", view: "roadmap" as ViewKey, focus: "Follow a practical sequence using Off Grid's existing operating stack.", icon: CalendarDays },
];

function tone(value: unknown) {
  const text = String(value ?? "UNKNOWN").toLowerCase();
  if (/verified|pursue|ready|supported|accept|excellent|good/.test(text) && !/unverified|unknown|not|blocked/.test(text)) return "good";
  if (/blocked|critical|failed|conflicted|error/.test(text)) return "bad";
  if (/unknown|verify|review|medium|inferred|preview|low|warning|partial/.test(text)) return "warn";
  return "neutral";
}

function scoreBand(value: unknown) {
  const n = Number(value) || 0;
  if (n >= 80) return "Strong";
  if (n >= 60) return "Moderate";
  return "Needs review";
}

function Pill({ children }: { children: unknown }) {
  return <span className={`pill ${tone(children)}`}>{titleCase(children)}</span>;
}

function Progress({ value, toneClass = "good" }: { value: unknown; toneClass?: "good" | "warn" | "bad" }) {
  const n = Math.max(0, Math.min(100, Number(value) || 0));
  return <span className="progress" aria-label={`${n} percent`}><i className={toneClass} style={{ width: `${n}%` }} /></span>;
}

function Logo() {
  return <div className="logo" aria-label="Off Grid Commercial Intelligence"><span className="logo-mark"><i /></span><span className="logo-copy"><b>OFF GRID</b><small>Commercial Intelligence</small></span></div>;
}

function PageHeader({ eyebrow, title, subtitle, d, actions }: { eyebrow: string; title: string; subtitle?: string; d?: DashboardData; actions?: ReactNode }) {
  return <header className="page-header">
    <div className="page-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>
    {d && <div className="project-facts" aria-label="Project context">
      <span><MapPin size={14} />{d.project.city}, {d.project.region}</span>
      <span><b>ID</b>{d.project.external_id}</span>
      <span><b>Stage</b>{titleCase(d.project.stage)}</span>
      <Pill>{d.assessment.assessment.overall_band} · {d.assessment.assessment.operational_action}</Pill>
    </div>}
    {actions && <div className="page-actions">{actions}</div>}
  </header>;
}

function SectionHead({ eyebrow, title, aside, icon: Icon }: { eyebrow?: string; title: string; aside?: string; icon?: LucideIcon }) {
  return <header className="section-head"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{Icon && <Icon size={18} />}{title}</h2></div>{aside && <p className="aside">{aside}</p>}</header>;
}

function Metric({ label, value, note, icon: Icon, kind = "good" }: { label: string; value: unknown; note?: string; icon?: LucideIcon; kind?: "good" | "warn" | "bad" }) {
  return <article className={`metric ${kind}`}><div className="metric-icon">{Icon && <Icon size={20} />}</div><div><span>{label}</span><strong>{String(value)}</strong>{note && <small>{note}</small>}</div></article>;
}

function DecisionCard({ label, value, note, icon: Icon, action }: { label: string; value: unknown; note: string; icon?: LucideIcon; action?: unknown }) {
  return <article className="score-card decision-card"><div className="score-top"><span className="score-icon warn">{Icon && <Icon size={23}/>}</span><div><span>{label}</span><strong>{String(value)}</strong></div>{action !== undefined && action !== null && <Pill>{action}</Pill>}</div><small>{note}</small></article>;
}

function Empty({ title, detail, kind = "warn" }: { title: string; detail: string; kind?: "warn" | "bad" }) {
  const Icon = kind === "bad" ? TriangleAlert : Info;
  return <div className={`empty-state ${kind}`}><Icon size={20}/><div><b>{title}</b><p>{detail}</p></div></div>;
}

function evidenceFor(d: DashboardData, key: string) {
  return d.evidence.find((item) => item.field_name === key) || d.evidence.find((item) => item.field_name.includes(key));
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
  return value.split(/\r?\n|\s+·\s+/).map((item) => item.trim()).filter(Boolean);
}

function EvidenceDrawer({ item, close }: { item: Evidence; close: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);
  return <div className="drawer-backdrop" role="presentation" onMouseDown={close}>
    <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="evidence-title" onMouseDown={(event) => event.stopPropagation()}>
      <button ref={closeRef} className="icon-button drawer-close" onClick={close} aria-label="Close evidence inspector"><X size={19}/></button>
      <p className="eyebrow">Evidence Inspector</p><h2 id="evidence-title">{titleCase(item.field_name)}</h2>
      <div className="pill-row"><Pill>{item.classification}</Pill><Pill>{item.confidence_state}</Pill><Pill>{item.scoring_treatment}</Pill></div>
      <dl className="detail-grid"><div><dt>Evidence ID</dt><dd>{item.evidence_id}</dd></div><div><dt>Page</dt><dd>{item.page_number ?? "Unknown"}</dd></div><div><dt>Section</dt><dd>{item.section_name ?? "Unknown"}</dd></div><div><dt>Validation</dt><dd>{titleCase(item.validation_state)}</dd></div></dl>
      <span className="label">Demo-safe source excerpt</span><blockquote>{item.excerpt || "No excerpt available."}</blockquote>
      <div className="privacy-note"><LockKeyhole size={16}/><span>Raw private documents and server paths are never exposed here.</span></div>
    </aside>
  </div>;
}

function GuidedReview({ d, start, setView }: { d: DashboardData; start: () => void; setView: (view: ViewKey) => void }) {
  const assessment = d.assessment.assessment;
  const warnings = d.quality.slice(0, 3);
  return <div className="page guided-page" data-view="guided">
    <section className="guided-hero">
      <div className="guided-copy"><p className="eyebrow">Guided CEO Review</p><h1>Make smarter go/no-go decisions. Faster.</h1><p>Walk through six employer questions and see the evidence-backed workflow built from the current Stafford and EE Reed records.</p><button className="button primary large" onClick={start}><ArrowRight size={21}/>Start guided review <small>3–5 minute walkthrough</small></button></div>
      <article className="opportunity-card"><div className="location"><MapPin size={15}/>{d.project.city}, {d.project.region}</div><h2>{d.project.canonical_name}</h2><div className="recommendation"><span>Deterministic recommendation</span><strong>{assessment.overall_band} · {assessment.operational_action}</strong></div><div className="score-triplet"><div><Target/><span>Commercial Fit</span><b>{assessment.overall_band}</b></div><div><ShieldCheck/><span>Data Confidence</span><b>{titleCase(assessment.confidence_state)}</b></div><div><Eye/><span>Evidence Records</span><b>{d.evidence.length}</b></div></div><p className="assessment-disclaimer">Decision support only—not a success probability, forecast, or verified demand.</p><div className="warning-list"><b>{warnings.length} trust warnings</b>{warnings.map((warning: any) => <button key={warning.id} onClick={() => setView("evidence")}><TriangleAlert size={14}/><span>{warning.title}</span><ChevronRight size={14}/></button>)}</div></article>
    </section>
    <section className="guided-questions" aria-label="Guided review questions">{guided.map((step, index) => { const Icon = step.icon; return <button key={step.q} onClick={() => setView(step.view)}><span className="step-number">{index + 1}</span><Icon size={22}/><b>{step.title}</b><p>{step.focus}</p><span className="start-link">Start <ArrowRight size={15}/></span></button>; })}</section>
    <section className="shortcut-grid">{[
      [BarChart3, "Project Intelligence", "Inspect qualification, trust, and sensitivity.", "project"],
      [UsersRound, "Contact Resolution", "Review evidence-supported investigation priorities.", "contacts"],
      [PackageCheck, "CRM Preview", "See why Lead and Deal gates remain separate.", "crm"],
      [MessageSquareText, "Commercial Analyst", "Ask grounded questions without enabling writes.", "analyst"],
    ].map(([Icon, label, copy, key]) => <button key={String(key)} onClick={() => setView(key as ViewKey)}><Icon size={24}/><div><b>{String(label)}</b><p>{String(copy)}</p></div><ArrowRight size={17}/></button>)}</section>
  </div>;
}

function CommandCenter({ d, setView }: { d: DashboardData; setView: (view: ViewKey) => void }) {
  const a = d.assessment.assessment;
  const action = d.actions.items.find((item: any) => item.status === "OPEN") || d.actions.items[0];
  return <div className="page" data-view="command">
    <PageHeader eyebrow="Executive overview" title="Command Center" subtitle="A decision-first view of the current commercial intelligence engine." d={d}/>
    <section className="command-grid">
      <article className="panel command-opportunity"><div className="opportunity-title"><span className="feature-icon"><Building2/></span><div><h2>{d.project.canonical_name}</h2><div className="context-line"><MapPin size={14}/>{d.project.city}, {d.project.region}<span>•</span>{titleCase(d.project.stage)}</div></div><Pill>{a.overall_band} · {a.operational_action}</Pill></div><div className="command-score-row"><DecisionCard label="Commercial Fit" value={a.overall_band} action={a.operational_action} note="Deterministic ordering band; not a probability" icon={Target}/><DecisionCard label="Data Confidence" value={titleCase(a.confidence_state)} note="Independent evidence reliability and completeness" icon={ShieldCheck}/><div className="reasons"><b>Key reasons</b>{d.assessment.dimensions.slice(0, 4).map((item: any) => <span key={item.key}><CircleCheck size={15}/>{item.label}: {titleCase(item.band)}</span>)}</div></div></article>
      <article className="panel trust-panel"><SectionHead title="What we don't trust" icon={ShieldCheck}/>{d.quality.slice(0, 3).map((item: any) => <button key={item.id} onClick={() => setView("evidence")}><span className="alert-icon"><TriangleAlert size={18}/></span><div><b>{item.title}</b><p>{item.decision_impact || item.detail}</p></div><ChevronRight size={16}/></button>)}</article>
      <article className="panel funnel"><SectionHead title="System pipeline" icon={BarChart3}/><div className="funnel-bars">{Object.entries(d.monday.pipeline).map(([key, value], index) => <div key={key} style={{ width: `${100 - index * 11}%` }}><b>{String(value)}</b><span>{titleCase(key)}</span></div>)}</div><p className="note">Operational diagnostics only; no production outcome is fabricated.</p></article>
      <article className="panel account-snapshot"><SectionHead title={`${d.organization?.canonical_name || "EE Reed"} intelligence`} icon={Building2}/>{(d.organization?.domains || []).slice(0, 3).map((item: any) => <div className="list-row" key={item.domain}><div><b>{item.domain}</b><small>Domain relationship</small></div><Pill>{item.relationship_state}</Pill></div>)}<button className="text-button" onClick={() => setView("account")}>View account profile <ArrowRight size={15}/></button></article>
      <article className="panel next-action"><SectionHead title="Next best action" icon={Target}/>{action ? <div className="ranked-action"><span>1</span><div><b>{titleCase(action.action_type)}</b><p>{action.reason}</p><small>Priority {action.priority} · progress only when prerequisites clear</small></div></div> : <Empty title="No action generated" detail="The backend did not return a current action."/>}<button className="text-button" onClick={() => setView("commercial")}>View commercial motion <ArrowRight size={15}/></button></article>
    </section>
  </div>;
}

function ProjectIntelligence({ d, open }: { d: DashboardData; open: (item: Evidence) => void }) {
  const a = d.assessment.assessment;
  const counterfactual = d.sensitivity.counterfactuals.find((item: any) => item.key === "without_reported_value") || d.sensitivity.counterfactuals[0] || {};
  const reportedValue = evidenceFor(d, "reported_value") || evidenceFor(d, "project_value");
  return <div className="page" data-view="project">
    <PageHeader eyebrow="Project Intelligence" title={d.project.canonical_name} d={d}/>
    <section className="score-band"><DecisionCard label="Commercial Fit" value={a.overall_band} action={a.operational_action} note="qualification-2.0 deterministic band" icon={Target}/><DecisionCard label="Data Confidence" value={titleCase(a.confidence_state)} note="Independent evidence state" icon={ShieldCheck}/>{d.assessment.product_fits.map((fit: any) => <DecisionCard key={fit.product_code} label={`${fit.product_code} applicability`} value={titleCase(fit.applicability_status)} note="Possible relevance only; direct need unconfirmed" icon={Zap}/>)}</section>
    <section className="project-grid">
      <article className="panel signals-panel"><SectionHead title="Project signals" icon={Gauge}/>{d.signals.slice(0, 7).map((item: any) => <div className="list-row" key={item.id}><span className="row-icon"><Zap size={16}/></span><div><b>{titleCase(item.key)}</b><small>{item.explanation || item.value}</small></div><Pill>{item.classification}</Pill></div>)}</article>
      <article className="panel evidence-summary"><SectionHead title="Evidence & trust" icon={ShieldCheck}/>{d.evidence.slice(0, 6).map((item) => <button className="table-row evidence-row" key={item.evidence_id} onClick={() => open(item)}><div><b>{titleCase(item.field_name)}</b><small>{item.section_name || "Source"}</small></div><Pill>{item.classification}</Pill><Pill>{item.confidence_state}</Pill><ChevronRight size={15}/></button>)}</article>
      <article className="panel contact-summary"><SectionHead title="Contact resolution" icon={UsersRound}/>{d.candidates.items.slice(0, 4).map((person: any) => <div className="table-row contact-row" key={person.candidate_id}><span className="avatar">{String(person.display_name).split(" ").map((part: string) => part[0]).slice(0, 2).join("")}</span><div><b>{person.display_name}</b><small>{titleCase(person.target_persona)}</small></div><Pill>{person.verification?.rental_authority || "UNKNOWN"}</Pill><b>{score(person.candidate_score)}</b></div>)}</article>
      <article className="panel action-summary"><SectionHead title="Next best action" icon={Target}/>{d.actions.items.slice(0, 4).map((item: any, index: number) => <div className="ranked-action compact" key={item.id}><span>{index + 1}</span><div><b>{titleCase(item.action_type)}</b><p>{item.reason}</p></div><Pill>{item.status}</Pill></div>)}</article>
      <article className="panel first-call"><SectionHead title="First-call kit" icon={MessageSquareText}/><ol><li>Who owns temporary lighting and portable power decisions?</li><li>Which rental provider and branch currently serves the site?</li><li>What site need and timing can be independently verified?</li><li>Who else must validate a demo or commercial next step?</li></ol></article>
      <article className="panel challenge"><SectionHead title="Counterfactual sensitivity" icon={RefreshCw} aside="Deterministic qualification-2.0"/><div className="comparison"><div><span>Baseline</span><b>{d.sensitivity.baseline.overall_band}</b><Pill>{d.sensitivity.baseline.operational_action}</Pill></div><ArrowRight/><div><span>{counterfactual.label || "Reported value removed"}</span><b>{counterfactual.band || "Unknown"}</b><Pill>{counterfactual.action || "UNKNOWN"}</Pill></div></div><p className="assessment-disclaimer">Reported value contributes zero qualification points and cannot control disposition.</p><button className="text-button" onClick={() => reportedValue && open(reportedValue)}>Inspect source-reported {money(d.project.reported_value)} value <ArrowRight size={15}/></button></article>
    </section>
  </div>;
}

function AccountIntelligence({ d }: { d: DashboardData }) {
  const contacts = d.organizationContacts?.items || [];
  const generic = contacts.filter((contact: any) => contact.contact_points.some((point: any) => point.is_generic)).length;
  const inactive = contacts.filter((contact: any) => String(contact.status).toLowerCase() === "inactive").length;
  const group = d.projectOrganizations.project_group;
  return <div className="page" data-view="account">
    <PageHeader eyebrow="Account Intelligence" title={d.organization?.canonical_name || "EE Reed Construction"} subtitle="Canonical account intelligence without silently merging uncertain identities." d={d}/>
    <section className="score-band four"><Metric label="Demo-safe contacts" value={contacts.length} note="Current API" icon={UsersRound}/><Metric label="Generic-inbox records" value={generic} note="Require review" icon={MessageSquareText} kind="warn"/><Metric label="Inactive contacts" value={inactive} note="Historical only" icon={UserRound} kind="warn"/><Metric label="Known domains" value={d.organization?.domains?.length || 0} note="Relationship state preserved" icon={Network}/></section>
    <section className="three-column-grid"><article className="panel"><SectionHead title="What stands out" icon={Lightbulb}/><div className="finding-list"><div><UsersRound/><span><b>Duplicate and malformed contacts</b><small>Names and generic inboxes remain reviewable.</small></span></div><div><Database/><span><b>Mixed historical and current data</b><small>Old relationships do not become present authority.</small></span></div><div><Network/><span><b>Multiple domains in use</b><small>Each relationship retains its evidence state.</small></span></div><div><Building2/><span><b>Recurring project activity</b><small>Commercial relevance, not decision authority.</small></span></div></div></article>
      <article className="panel"><SectionHead title="Contact quality findings" icon={ShieldCheck}/>{(d.organization?.domains || []).map((item: any) => <div className="list-row" key={item.domain}><span className="row-icon"><Network size={16}/></span><div><b>{item.domain}</b><small>Account-domain relationship</small></div><Pill>{item.relationship_state}</Pill></div>)}<div className="list-row"><span className="row-icon"><MessageSquareText size={16}/></span><div><b>{generic} generic inbox records</b><small>Never promoted as individual authority</small></div><Pill>{generic ? "REVIEW" : "VERIFIED"}</Pill></div></article>
      <article className="panel portfolio"><SectionHead title="Project portfolio snapshot" icon={Building2}/>{(d.organizationProjects?.items || []).slice(0, 8).map((project: any) => <div className="table-row" key={project.project_id}><span className="row-icon"><Building2 size={16}/></span><div><b>{project.canonical_name}</b><small>{project.stage || "Stage unknown"}</small></div><Pill>{project.verification_state}</Pill></div>)}</article>
      <article className="panel span-2"><SectionHead title="Stafford project and phase clustering" icon={GitBranch}/>{group ? <div className="phase-map"><div><Building2/><b>{group.canonical_name}</b></div>{group.projects.map((project: any) => <article key={project.id}><span/><div><b>{project.canonical_name}</b><small>{project.stage} · reported {money(project.reported_value)}</small></div><Pill>{project.verification_state || "SUPPORTED"}</Pill></article>)}</div> : <Empty title="Project group unresolved" detail="No supported campus grouping is available."/>}</article>
      <article className="panel"><SectionHead title="Next account actions" icon={Target}/><ul className="check-list"><li>Standardize duplicate names without destructive merges.</li><li>Replace generic inboxes with verified individual contacts.</li><li>Confirm active roles for Stafford project phases.</li><li>Keep historical relationships separate from current authority.</li></ul></article>
    </section>
  </div>;
}

function ContactResolution({ d }: { d: DashboardData }) {
  return <div className="page" data-view="contacts">
    <PageHeader eyebrow="Contact Resolution" title="Stafford / EE Reed" subtitle="Investigation priority is not authority. Each verification dimension remains independent." d={d}/>
    <section className="verification-ladder"><div><b>Our verification ladder</b><p>Four criteria determine whether a person can progress.</p></div>{[[CircleCheck,"Employment","Current organization"],[CircleCheck,"Project association","Specific project"],[CircleCheck,"Role relevance","Commercial influence"],[LockKeyhole,"Rental authority","Approval authority"]].map(([Icon,label,copy]) => <div key={String(label)}><Icon size={22}/><span><b>{String(label)}</b><small>{String(copy)}</small></span></div>)}</section>
    <section className="panel candidate-table"><SectionHead title={`Candidate contacts (${d.candidates.count})`} icon={UsersRound}/><div className="table-scroll"><div className="table-head contact-grid"><span>Candidate</span><span>Employment</span><span>Project</span><span>Role</span><span>Authority</span><span>Fit</span></div>{d.candidates.items.map((person: any) => <article className="contact-grid" key={person.candidate_id}><div className="person-cell"><span className="avatar">{String(person.display_name).split(" ").map((part: string) => part[0]).slice(0,2).join("")}</span><span><b>{person.display_name}</b><small>{titleCase(person.target_persona)}</small></span></div><Pill>{person.verification?.employment || "UNKNOWN"}</Pill><Pill>{person.verification?.project_association || "UNKNOWN"}</Pill><Pill>{person.verification?.role_relevance || "UNKNOWN"}</Pill><Pill>{person.verification?.rental_authority || "UNKNOWN"}</Pill><span className="fit-cell"><b>{score(person.candidate_score)}</b><small>{scoreBand(person.candidate_score)}</small></span></article>)}</div></section>
    <section className="contact-bottom"><article className="panel best-candidate"><SectionHead title="Best current candidate" icon={Sparkles}/>{d.candidates.items[0] ? <><div className="person-feature"><span className="avatar large">{String(d.candidates.items[0].display_name).split(" ").map((part: string) => part[0]).slice(0,2).join("")}</span><div><h2>{d.candidates.items[0].display_name}</h2><p>{rationale(d.candidates.items[0].rationale)}</p></div><b>{score(d.candidates.items[0].candidate_score)}</b></div><Empty title="Rental authority is UNKNOWN / unverified" detail="Do not treat the top-ranked investigation candidate as a final decision-maker."/></> : <Empty title="No candidate available" detail="The backend returned no ranked contact candidates."/>}</article><article className="panel"><SectionHead title="First-call verification questions" icon={MessageSquareText}/><ol className="numbered-list"><li>Can you confirm your current role and Stafford responsibilities?</li><li>Are you involved in equipment, procurement, or rental decisions?</li><li>What is the process for evaluating rental partners?</li><li>Who else should be involved in a demo decision?</li><li>What is the safest follow-up channel?</li></ol></article><article className="panel"><SectionHead title="How we know" icon={Database}/><div className="source-list"><span><Database/>ConstructConnect <small>Project and company source data</small></span><span><Building2/>Company evidence <small>Roles, domains, and recurrence</small></span><span><FileSearch/>Public research <small>Only when current evidence exists</small></span><span><ShieldCheck/>Trust engine <small>Unknowns remain unknown</small></span></div></article></section>
  </div>;
}

function EvidenceTrust({ d, open }: { d: DashboardData; open: (item: Evidence) => void }) {
  const confidence = d.assessment.assessment.data_confidence_score;
  return <div className="page" data-view="evidence"><PageHeader eyebrow="Evidence & Trust" title={d.project.canonical_name} subtitle="Every important conclusion is inspectable through the demo-safe API." d={d}/><section className="evidence-layout"><article className="panel evidence-table"><SectionHead title={`Evidence & observations (${d.evidence.length})`} icon={FileSearch}/><div className="table-scroll"><div className="table-head evidence-grid"><span>Observation</span><span>Classification</span><span>Confidence</span><span>Treatment</span><span/></div>{d.evidence.map((item) => <button className="evidence-grid" key={item.evidence_id} onClick={() => open(item)}><div><b>{titleCase(item.field_name)}</b><small>{item.section_name || "Source"} · page {item.page_number ?? "?"}</small></div><Pill>{item.classification}</Pill><Pill>{item.confidence_state}</Pill><span>{titleCase(item.scoring_treatment)}</span><ChevronRight size={15}/></button>)}</div></article><aside className="evidence-aside"><article className="panel"><SectionHead title="Trust warnings" icon={TriangleAlert}/>{d.quality.map((item: any) => <div className="trust-warning" key={item.id}><TriangleAlert size={18}/><div><b>{item.title}</b><p>{item.decision_impact || item.detail}</p></div></div>)}</article><article className="panel coverage"><SectionHead title="Evidence coverage" icon={Database}/><div className="coverage-number"><b>{score(confidence)}%</b><span>Current data confidence</span></div><Progress value={confidence}/><p>Confidence describes the present source state; it is not the same as commercial fit.</p></article></aside></section></div>;
}

function ProductFit({ d }: { d: DashboardData }) {
  const openQuestions: string[] = Array.from(new Set<string>(d.assessment.product_fits.flatMap((fit: any): string[] => stringList(fit.missing_evidence))));
  return <div className="page" data-view="product"><PageHeader eyebrow="Product Fit" title={d.project.canonical_name} subtitle="Project characteristics indicate possible relevance; actual product need is not yet confirmed." d={d}/><div className="assessment-disclaimer prominent">Deterministic decision support only. Applicability states are not verified demand, product specifications, forecasts, or success probabilities.</div><section className="product-cards">{d.assessment.product_fits.map((fit: any) => { const questions = stringList(fit.missing_evidence); return <article className="panel" key={fit.product_code}><div className="product-heading"><span className="feature-icon"><Zap/></span><div><h2>{fit.product_code}</h2><Pill>{fit.applicability_status}</Pill></div></div><p>{fit.explanation}</p><div className="question-box"><b>Evidence required before fit can be supported</b>{questions.length ? <ul>{questions.map((item) => <li key={item}>{item}</li>)}</ul> : <span>No additional evidence request returned.</span>}</div></article>; })}</section><section className="product-grid"><article className="panel"><SectionHead title="Project-characteristic signals" icon={GitBranch}/>{d.signals.slice(0, 7).map((item: any) => <div className="signal-matrix" key={item.id}><div><b>{titleCase(item.key)}</b><small>{item.explanation || item.value}</small></div><Pill>{item.classification}</Pill></div>)}</article><article className="panel"><SectionHead title="What we still need to verify" icon={CircleHelp}/>{openQuestions.slice(0, 8).map((item) => <div className="question-row" key={item}><CircleHelp size={17}/><span>{item}</span><ChevronRight size={15}/></div>)}</article><article className="panel"><SectionHead title="Applicability status" icon={BarChart3}/>{d.assessment.product_fits.map((fit: any) => <div className="comparison-row applicability-row" key={fit.product_code}><b>{fit.product_code}</b><span>Direct lighting/power requirement missing</span><Pill>{fit.applicability_status}</Pill></div>)}</article></section></div>;
}

function ExceptionQueue({ d }: { d: DashboardData }) {
  const allItems = d.exceptions.count ? d.exceptions.items : d.quality.map((item: any) => ({ ...item, summary: item.title, detail: item.detail, status: item.state, priority: item.severity }));
  const [filter, setFilter] = useState("ALL");
  const visible = filter === "ALL" ? allItems : allItems.filter((item: any) => String(item.priority || item.severity).toUpperCase() === filter);
  return <div className="page" data-view="exceptions"><PageHeader eyebrow="Pipeline Failure & Recovery" title="Exception Queue" subtitle="Quality warnings remain visible even when they do not create a workflow exception." d={d}/><section className="score-band four"><Metric label="Open exceptions" value={d.exceptions.count} icon={TriangleAlert} kind={d.exceptions.count ? "bad" : "good"}/><Metric label="Quality warnings" value={d.quality.length} icon={Flag} kind="warn"/><Metric label="Progression blockers" value={d.quality.filter((item: any) => item.blocks_progression).length} icon={LockKeyhole} kind="bad"/><Metric label="Resolved today" value="N/A" note="Outcome history not connected" icon={CircleCheck} kind="warn"/></section><section className="panel exception-panel"><div className="filter-bar" aria-label="Exception filters">{["ALL","HIGH","MEDIUM","LOW"].map((value) => <button key={value} className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>{titleCase(value)} <span>{value === "ALL" ? allItems.length : allItems.filter((item: any) => String(item.priority || item.severity).toUpperCase() === value).length}</span></button>)}</div>{visible.length ? <div className="table-scroll"><div className="table-head exception-grid"><span>Severity</span><span>Item</span><span>Reason</span><span>Status</span><span>Next action</span></div>{visible.map((item: any, index: number) => <article className="exception-grid" key={item.id || `${item.summary}-${index}`}><Pill>{item.priority || item.severity}</Pill><div><b>{item.summary}</b><small>{d.project.canonical_name}</small></div><span>{item.detail || item.decision_impact}</span><Pill>{item.status}</Pill><span>{item.blocks_progression ? "Resolve before progression" : "Verify and monitor"}</span></article>)}</div> : <Empty title="No items match this filter" detail="Choose another severity filter to continue reviewing the queue."/>}</section></div>;
}

function CrmPreview({ d, setView }: { d: DashboardData; setView: (view: ViewKey) => void }) {
  return <div className="page" data-view="crm"><PageHeader eyebrow="CRM Preview · read-only" title="Lead-ready does not mean Deal-ready" subtitle="No data is written to Pipedrive in this preview." d={d}/><div className="dry-run-banner"><Info size={18}/><span><b>DRY RUN PREVIEW</b> — current API state only; external write authority remains server-side.</span><Pill>{d.crm.pipedrive.mode || "PREVIEW"}</Pill></div><section className="crm-layout"><article className="panel readiness"><SectionHead title="CRM readiness" icon={PackageCheck}/>{[["Project qualified",true],["Lead readiness",d.readiness.lead_ready],["Deal readiness",d.readiness.deal_ready],["Evidence retained",true]].map(([label,ready]) => <div key={String(label)} className={ready ? "pass" : "blocked"}>{ready ? <CircleCheck/> : <TriangleAlert/>}<div><b>{String(label)}</b><small>{ready ? "Deterministic gate passed" : "Human validation still required"}</small></div></div>)}<div className="readiness-outcome"><span>Recommended promotion</span><Pill>{d.readiness.recommended_promotion}</Pill></div></article><article className="panel crm-requests"><SectionHead title="Pipedrive request preview" icon={Database}/><div className="request-grid">{d.crm.pipedrive.requests.map((request: any) => <article key={request.idempotency_key}><div><Pill>{request.status}</Pill><span>{titleCase(request.object_type)}</span></div><h3>{titleCase(request.action)}</h3><p>{request.blocked_reason || "Validated preview; no live write executed."}</p><details><summary>Inspect demo-safe payload</summary><pre>{JSON.stringify(request.payload, null, 2)}</pre></details></article>)}</div></article><aside className="crm-aside"><article className="panel blocker-panel"><SectionHead title="Why Deal creation is blocked" icon={LockKeyhole}/>{(d.readiness.deal_blockers || []).map((item: string) => <div className="blocker" key={item}><TriangleAlert size={16}/><b>{titleCase(item)}</b></div>)}<button className="button secondary" onClick={() => setView("contacts")}>Open Contact Resolution</button></article><article className="panel"><SectionHead title="Duplicate prevention" icon={ShieldCheck}/><div className="success-callout"><CircleCheck/><span>No live duplicates can be created in dry-run mode.</span></div><div className="safety"><div><span>External writes</span><b>{String(d.crm.external_writes_executed)}</b></div><div><span>Mode</span><Pill>{d.crm.pipedrive.mode || "PREVIEW"}</Pill></div></div></article></aside></section></div>;
}

function CommercialMotion({ d, setView }: { d: DashboardData; setView: (view: ViewKey) => void }) {
  return <div className="page" data-view="commercial"><PageHeader eyebrow="Commercial Motion" title="Stafford opportunity" subtitle="Contractor demand and rental-house supply are linked, but they remain separate motions." d={d}/><section className="motion-paths">{d.motions.items.map((motion: any) => { const contractor = motion.motion_type === "CONTRACTOR"; const steps = contractor ? ["Stafford", "EE Reed", "Project leadership", "Verified need", "Demo request"] : ["Contractor demand", "Rental partner", "Branch / fleet", "Fleet opportunity", "Channel sale"]; return <article className="panel" key={motion.id}><SectionHead title={contractor ? "Contractor demand motion" : "Rental house / fleet motion"} icon={contractor ? Building2 : Handshake}/><div className="motion-flow">{steps.map((step, index) => <div key={step}><span className={index < (contractor ? 3 : 1) ? "complete" : "pending"}>{index < (contractor ? 3 : 1) ? <Check/> : <span>{index + 1}</span>}</span><b>{step}</b>{index < steps.length - 1 && <ArrowRight/>}</div>)}</div><div className="motion-status"><Pill>{motion.status}</Pill><Pill>{motion.confidence_state}</Pill><p>{motion.summary}</p></div></article>; })}</section><section className="commercial-grid"><article className="panel"><SectionHead title="Current motion state" icon={Gauge}/>{d.motions.items.map((motion: any) => <div className="motion-meter" key={motion.id}><div><b>{titleCase(motion.motion_type)} motion</b><Pill>{motion.status}</Pill></div><Progress value={motion.motion_type === "CONTRACTOR" ? 64 : 24} toneClass={motion.motion_type === "CONTRACTOR" ? "good" : "warn"}/><small>{motion.demand_strength || "Demand strength unknown"}</small></div>)}</article><article className="panel"><SectionHead title="Decision support" icon={Lightbulb}/><ul className="check-list"><li>EE Reed is the supported general contractor relationship.</li><li>Current project signals support contractor-first investigation.</li><li>Rental partner and authority remain unresolved.</li><li>Deal progression cannot outrun verified dependencies.</li></ul></article><article className="panel"><SectionHead title="Next commercial actions" icon={Target}/>{d.actions.items.slice(0, 6).map((item: any, index: number) => <div className="ranked-action compact" key={item.id}><span>{index + 1}</span><div><b>{titleCase(item.action_type)}</b><p>{item.reason}</p></div><Pill>{item.status}</Pill></div>)}</article><article className="panel span-2"><SectionHead title="Proof for contractor-first demand" icon={CircleCheck}/><div className="proof-grid"><span><Check/>Supported GC relationship</span><span><Check/>Active project evidence</span><span><Check/>Product-fit signals</span><span><Check/>Dependency-aware actions</span><span><TriangleAlert/>Rental authority unresolved</span><span><TriangleAlert/>Site supplier unresolved</span></div></article><article className="panel"><SectionHead title="Commercial handoff" icon={Handshake}/><button className="handoff-link" onClick={() => setView("crm")}><PackageCheck/>CRM Preview <ArrowRight/></button><button className="handoff-link" onClick={() => setView("monday")}><CalendarDays/>Monday Brief <ArrowRight/></button></article></section></div>;
}

function OpenAIStatus({ d }: { d: DashboardData }) {
  const state = d.systemReadiness?.integrations?.openai;
  const label = !state?.enabled ? "OpenAI disabled" : state.credentials_present ? "OpenAI enabled" : "OpenAI unavailable";
  return <Pill>{label}</Pill>;
}

function Analyst({ d }: { d: DashboardData }) {
  const questions = ["Why pursue Stafford?", "What data should I not trust?", "What would change the recommendation?", "Who should we investigate first?", "What is blocking Pipedrive?", "Which product appears strongest?", "What should I ask on the first call?"];
  const [question, setQuestion] = useState(questions[0]);
  const [response, setResponse] = useState<AnalystResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState("FAST");
  const [conversation, setConversation] = useState<any[]>([]);
  const answer = response?.answer as any;
  async function submit(event?: FormEvent) {
    event?.preventDefault(); setBusy(true);
    try { const next = await askAnalyst(d.project.id, question, mode, conversation); setResponse(next); if (next.answer && ["SUCCEEDED", "PARTIAL_VALIDATED"].includes(String(next.status))) setConversation((rows) => [...rows, { question, answer: next.answer.direct_conclusion, claim_ids: next.answer.claims?.map((claim: any) => claim.claim_id) || [] }].slice(-4)); }
    catch (error) { setResponse({ status: "ERROR", fallback_reason: error instanceof Error ? error.message : "Request failed", external_request_executed: false }); }
    finally { setBusy(false); }
  }
  return <div className="page" data-view="analyst"><PageHeader eyebrow="Commercial Analyst" title="Evidence-grounded answers" subtitle="Read-only analysis preserves unknowns and cannot mutate deterministic truth." d={d}/><div className="analyst-status"><OpenAIStatus d={d}/><Pill>Grounded mode on</Pill><Pill>Read-only</Pill><Pill>Demo mode</Pill></div><section className="analyst-layout"><article className="panel analyst-conversation"><SectionHead title="Analyst conversation" icon={MessageSquareText}/><form onSubmit={submit}><label htmlFor="analyst-question">Ask about Stafford</label><div className="analyst-controls"><div className="ask"><input id="analyst-question" value={question} onChange={(event) => setQuestion(event.target.value)} disabled={busy}/><button className="button primary" disabled={busy || question.trim().length < 3}>{busy ? <RefreshCw className="spin"/> : <Sparkles/>}{busy ? "Analyzing…" : "Ask"}</button></div><div className="mode-switch" aria-label="Analysis mode">{[["FAST","Terra · fast"],["STANDARD","Sol · standard"],["DEEP","Sol · deep"]].map(([key,label]) => <button type="button" className={mode === key ? "active" : ""} onClick={() => setMode(key)} key={key}>{label}</button>)}</div></div></form>{response ? <div className="answer" aria-live="polite"><div className="answer-status"><Pill>{response.status}</Pill><span>{response.external_request_executed ? "OpenAI request executed" : response.cache_hit ? "Validated answer cache" : "Deterministic fallback"}</span>{response.model_id && <span>{response.model_id}</span>}{response.grounding?.status && <Pill>{response.grounding.status} grounding</Pill>}</div>{answer ? <div className="analyst-result"><h3>{answer.direct_conclusion || "Analyst answer"}</h3><p className="analyst-answer-copy">{typeof answer === "string" ? answer : answer.answer}</p>{Array.isArray(answer.claims) && answer.claims.length > 0 && <section className="analyst-claims"><h4>Validated claims and rationale</h4>{answer.claims.map((claim: any) => <details key={claim.claim_id}><summary><Pill>{claim.classification}</Pill><span>{claim.claim_text}</span></summary><p>{claim.rationale}</p><small>{claim.evidence_ids?.length || 0} cited evidence record{claim.evidence_ids?.length === 1 ? "" : "s"}: {claim.evidence_ids?.join(", ")}</small></details>)}</section>}{Array.isArray(answer.decision_changing_unknowns) && answer.decision_changing_unknowns.length > 0 && <section className="analyst-unknowns"><h4>Decision-changing unknowns</h4><ul>{answer.decision_changing_unknowns.map((item: string) => <li key={item}>{item}</li>)}</ul></section>}<div className="answer-foot"><span>{response.tool_rounds || 0} read-only tool round(s) · {response.latency_ms || 0} ms</span><span>Estimated request cost ${response.estimated_cost_usd || "0"}</span></div></div> : <div className="fallback-answer"><h3>Deterministic system remains available.</h3><p>{response.fallback_reason || "The optional model is unavailable; core intelligence remains operational."}</p></div>}</div> : <div className="answer placeholder"><Sparkles size={28}/><h3>Try a CEO-style challenge.</h3><p>The analyst uses a compact current-state packet and only displays validated claims. Follow-up context stays sanitized in this browser session.</p></div>}</article><aside className="analyst-aside"><article className="panel"><SectionHead title="Suggested questions" icon={CircleHelp}/>{questions.map((item) => <button className={question === item ? "active" : ""} key={item} onClick={() => setQuestion(item)}><Target size={15}/><span>{item}</span><ChevronRight size={15}/></button>)}</article><article className="panel guardrails"><SectionHead title="Analyst guardrails" icon={ShieldCheck}/><span><LockKeyhole/>No external writes</span><span><FileSearch/>Validated evidence required</span><span><CircleHelp/>Unknowns preserved</span><span><PackageCheck/>CRM gates stay deterministic</span></article></aside></section></div>;
}

function MondayBrief({ d, setView }: { d: DashboardData; setView: (view: ViewKey) => void }) {
  const pipeline = Object.entries(d.monday.pipeline);
  const a = d.assessment.assessment;
  return <div className="page" data-view="monday"><PageHeader eyebrow="Executive operating rhythm" title="Monday Morning Brief" subtitle="A truthful weekly view of pipeline, opportunity, and attention required." d={d}/><section className="headline-kpi"><span className="kpi-icon"><BarChart3/></span><div><p className="eyebrow">Headline KPI</p><h2>System-sourced demos booked — rolling 30 days</h2></div><strong>{d.monday.primary_kpi.display}</strong><p>Production outcome history is not connected in this environment.</p><Pill>Intended KPI</Pill></section><section className="pipeline-band">{pipeline.map(([key, value], index) => <div key={key}><span className="pipeline-icon">{index === pipeline.length - 1 ? <CalendarDays/> : index < 2 ? <Database/> : <UsersRound/>}</span><span><b>{titleCase(key)}</b><strong>{String(value)}</strong></span>{index < pipeline.length - 1 && <ChevronRight/>}</div>)}</section><section className="monday-grid"><article className="panel top-opportunity"><SectionHead title="Top opportunity" icon={Building2}/><h2>{d.monday.top_opportunity?.name || "No qualified opportunity"}</h2>{d.monday.top_opportunity ? <><div className="context-line"><MapPin size={14}/>{d.project.city}, {d.project.region}<span>•</span>{titleCase(d.project.stage)}</div><div className="twoscores"><div><span>Commercial fit</span><b>{a.overall_band}</b></div><div><span>Data confidence</span><b>{titleCase(a.confidence_state)}</b></div></div><Pill>{a.operational_action}</Pill><p className="assessment-disclaimer">Deterministic decision support; not a probability or validated demand.</p><button className="text-button" onClick={() => setView("project")}>View full intelligence <ArrowRight size={15}/></button></> : <Empty title="No opportunity returned" detail="The backend has no current top opportunity."/>}</article><article className="panel attention"><SectionHead title="Attention required" icon={TriangleAlert}/>{d.monday.attention_required.length ? d.monday.attention_required.map((item: any) => <div className="attention-row" key={item.id}><span className="alert-icon"><TriangleAlert size={16}/></span><div><b>{item.summary}</b><small>{item.detail || "Validation work required"}</small></div><Pill>{item.status}</Pill><span>P{item.priority}</span></div>) : d.quality.slice(0, 5).map((item: any) => <div className="attention-row" key={item.id}><span className="alert-icon"><TriangleAlert size={16}/></span><div><b>{item.title}</b><small>{item.decision_impact || item.detail}</small></div><Pill>{item.severity}</Pill><span>Verify</span></div>)}<button className="text-button" onClick={() => setView("exceptions")}>View exception queue <ArrowRight size={15}/></button></article><article className="panel weekly"><SectionHead title="This week in the pipeline" icon={BarChart3}/>{pipeline.map(([key, value]) => <div className="weekly-row" key={key}><span className="row-icon"><CircleCheck size={16}/></span><b>{titleCase(key)}</b><strong>{String(value)}</strong></div>)}<p className="note">These are current system diagnostics, not claimed production conversions.</p></article></section></div>;
}

function First14Days() {
  const phases = [
    ["Days 1–2", "Audit the current workflow and fields", "Map the end-to-end process, owners, and field inventory.", "Current-state map", "Missing dependencies"],
    ["Days 3–4", "Define canonical project, company, and contact identity", "Lock keys, precedence, and non-destructive resolution rules.", "Field mapping matrix", "Inconsistent definitions"],
    ["Days 5–6", "Build the Stafford and EE Reed golden path", "Validate qualification, evidence, and employer questions.", "Golden path", "Overfitting rules"],
    ["Days 7–8", "Layer in contact resolution and verification", "Separate employment, project, role, and authority state.", "Verification checklist", "Incomplete sources"],
    ["Days 9–10", "Add CRM preview and duplicate protection", "Exercise Lead/Deal gates and idempotent dry runs.", "CRM preview", "Data hygiene"],
    ["Days 11–12", "Stand up reporting and exception rhythm", "Make quality warnings and ownership visible.", "Monday brief", "Manual-step creep"],
    ["Days 13–14", "Validate, document, and prepare handoff", "Run the complete release matrix and preserve evidence.", "Reproducible handoff", "Scope creep"],
  ];
  return <div className="page" data-view="roadmap"><PageHeader eyebrow="First 14 Days" title="No-help, existing-tools plan" subtitle="Connect qualification, contact resolution, CRM readiness, and review cadence without inventing new production capability."/><div className="objective-banner"><Target/><span><b>Objective:</b> fix the handoffs first, preserve truth boundaries, and use existing approved tools.</span></div><section className="roadmap-layout"><article className="panel roadmap-table"><div className="roadmap-head"><span>Two-week roadmap</span><span>Deliverable</span><span>Risk to manage</span><span>Expected output</span></div>{phases.map(([days, title, detail, output, risk], index) => <div className="roadmap-row" key={days}><span className="roadmap-step">{index + 1}</span><div><small>{days}</small><b>{title}</b><p>{detail}</p></div><span><CircleCheck/>{output}</span><span><TriangleAlert/>{risk}</span><span><PackageCheck/>{output}</span></div>)}</article><aside><article className="panel"><SectionHead title="What this plan uses" icon={PackageCheck}/><div className="tool-list"><span><Database/>ConstructConnect <small>Project and source records</small></span><span><UsersRound/>Contact research <small>Evidence-gated investigation</small></span><span><PackageCheck/>Pipedrive preview <small>Readiness and duplicate safety</small></span><span><BarChart3/>Reporting <small>Truthful operating rhythm</small></span></div></article><article className="panel not-doing"><SectionHead title="What it does not do" icon={TriangleAlert}/><ul><li>No fabricated telemetry or outcomes</li><li>No automatic consequential outreach</li><li>No blind CRM synchronization</li><li>No authority claims without evidence</li><li>No hidden dependency on chat history</li></ul></article></aside></section><section className="success-band"><b>Success by day 14</b>{["Stafford answer reproducible","EE Reed risks visible","First-call kit usable","Lead preview ready","Weekly KPI defined","Exception rhythm established"].map((item) => <span key={item}><CircleCheck/>{item}</span>)}</section></div>;
}

function Sidebar({ view, navigate, startGuide, open, close }: { view: ViewKey; navigate: (view: ViewKey) => void; startGuide: () => void; open: boolean; close: () => void }) {
  return <><aside className={`sidebar ${open ? "open" : ""}`} aria-label="Primary navigation"><div className="sidebar-top"><Logo/><button className="icon-button sidebar-close" onClick={close} aria-label="Close navigation"><X/></button></div><button className={`guide-button ${view === "guided" ? "active" : ""}`} onClick={() => navigate("guided")}><Sparkles size={20}/><span><b>Guided CEO Review</b><small>Six-question walkthrough</small></span></button>{(["Decide","Resolve","Act","Explain"] as const).map((group) => <nav key={group} aria-label={group}><span className="nav-group">{group}</span>{nav.filter((item) => item.group === group).map((item) => { const Icon = item.icon; return <button title={item.label} aria-current={view === item.key ? "page" : undefined} className={view === item.key ? "active" : ""} key={item.key} onClick={() => navigate(item.key)}><Icon size={19}/><span>{item.label}</span>{item.key === "exceptions" && <i>!</i>}</button>; })}</nav>)}<footer><div><Database size={18}/><span><small>Source posture</small><b>DEMO SAFE</b></span></div><p>No raw PDFs or external writes. Private paths stay hidden.</p><button onClick={startGuide}>Start guided review <ArrowRight size={14}/></button></footer></aside>{open && <button className="sidebar-scrim" onClick={close} aria-label="Close navigation overlay"/>}</>;
}

function UtilityBar({ view, navigate, openNav }: { view: ViewKey; navigate: (view: ViewKey) => void; openNav: () => void }) {
  const [query, setQuery] = useState("");
  const matches = useMemo(() => query.trim() ? nav.filter((item) => item.label.toLowerCase().includes(query.trim().toLowerCase())) : [], [query]);
  return <header className="utility-bar"><button className="mobile-menu icon-button" onClick={openNav} aria-label="Open navigation"><Menu/></button><div className="mobile-logo"><Logo/></div><div className="search-box"><Search size={18}/><label className="sr-only" htmlFor="global-search">Search application views</label><input id="global-search" placeholder="Search projects, accounts, contacts…" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && matches[0]) { navigate(matches[0].key); setQuery(""); } }}/>{query && <div className="search-results">{matches.length ? matches.map((item) => <button key={item.key} onClick={() => { navigate(item.key); setQuery(""); }}>{item.label}<ArrowRight size={14}/></button>) : <span>No matching application view</span>}</div>}</div><div className="utility-actions"><Pill>Demo mode</Pill><button className="icon-button" aria-label="Notifications" title="No live notification service"><Bell size={19}/><i/></button><button className="icon-button" aria-label="Help" title="Guided review"><CircleHelp size={19}/></button><button className="account-button" aria-label="Demo account menu"><span>OG</span><b>Off Grid</b></button></div><span className="sr-only" aria-live="polite">Current view: {view}</span></header>;
}

function GuidedBar({ index, move, exit }: { index: number; move: (delta: number) => void; exit: () => void }) {
  const step = guided[index];
  return <aside className="guided-bar" aria-label="Guided CEO Review progress"><div><span>{step.q}</span><b>{step.title}</b><p>{step.focus}</p><div className="guide-progress">{guided.map((_, itemIndex) => <i className={itemIndex <= index ? "on" : ""} key={itemIndex}/>)}</div></div><div><button className="button ghost" onClick={exit}>Exit</button><button className="button ghost" disabled={index === 0} onClick={() => move(-1)}>Back</button>{index < guided.length - 1 ? <button className="button primary" onClick={() => move(1)}>Next <ArrowRight size={16}/></button> : <button className="button primary" onClick={exit}>Complete review <Check size={16}/></button>}</div></aside>;
}

function parseView(): ViewKey {
  const key = window.location.hash.replace(/^#\/?/, "") as ViewKey;
  return key === "guided" || nav.some((item) => item.key === key) ? key : "command";
}

function Frame({ d }: { d: DashboardData }) {
  const [view, setView] = useState<ViewKey>(parseView);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const [guideIndex, setGuideIndex] = useState(0);
  const [navOpen, setNavOpen] = useState(false);
  useEffect(() => { const handler = () => setView(parseView()); window.addEventListener("hashchange", handler); return () => window.removeEventListener("hashchange", handler); }, []);
  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 821px)");
    const closeOnDesktop = (event: MediaQueryListEvent) => { if (event.matches) setNavOpen(false); };
    if (desktop.matches) setNavOpen(false);
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);
  useEffect(() => {
    if (!navOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setNavOpen(false); };
    document.addEventListener("keydown", closeOnEscape);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", closeOnEscape); document.body.style.overflow = ""; };
  }, [navOpen]);
  useEffect(() => { window.scrollTo({ top: 0 }); document.title = `${view === "guided" ? "Guided CEO Review" : nav.find((item) => item.key === view)?.label || "Off Grid"} · Off Grid`; }, [view]);
  function navigate(next: ViewKey) { setView(next); setNavOpen(false); setEvidence(null); window.history.replaceState(null, "", `#/${next}`); }
  function startGuide() { setGuideIndex(0); setGuideOpen(true); navigate(guided[0].view); }
  function moveGuide(delta: number) { const next = Math.max(0, Math.min(guided.length - 1, guideIndex + delta)); setGuideIndex(next); navigate(guided[next].view); }
  let body: ReactNode;
  switch (view) {
    case "guided": body = <GuidedReview d={d} start={startGuide} setView={navigate}/>; break;
    case "command": body = <CommandCenter d={d} setView={navigate}/>; break;
    case "project": body = <ProjectIntelligence d={d} open={setEvidence}/>; break;
    case "account": body = <AccountIntelligence d={d}/>; break;
    case "contacts": body = <ContactResolution d={d}/>; break;
    case "evidence": body = <EvidenceTrust d={d} open={setEvidence}/>; break;
    case "product": body = <ProductFit d={d}/>; break;
    case "exceptions": body = <ExceptionQueue d={d}/>; break;
    case "crm": body = <CrmPreview d={d} setView={navigate}/>; break;
    case "commercial": body = <CommercialMotion d={d} setView={navigate}/>; break;
    case "analyst": body = <Analyst d={d}/>; break;
    case "monday": body = <MondayBrief d={d} setView={navigate}/>; break;
    default: body = <First14Days/>;
  }
  return <div className="app-shell"><Sidebar view={view} navigate={navigate} startGuide={startGuide} open={navOpen} close={() => setNavOpen(false)}/><div className="workspace"><UtilityBar view={view} navigate={navigate} openNav={() => setNavOpen(true)}/><main className="content" id="main-content">{body}</main></div>{guideOpen && <GuidedBar index={guideIndex} move={moveGuide} exit={() => setGuideOpen(false)}/>} {evidence && <EvidenceDrawer item={evidence} close={() => setEvidence(null)}/>}</div>;
}

export function App() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { let live = true; loadDashboard().then((value) => live && setData(value)).catch((reason) => live && setError(reason instanceof Error ? reason.message : "Load failed")); return () => { live = false; }; }, []);
  if (error) {
    const unauthorized = /^401\b/.test(error);
    return <main className="boot-state"><div className="boot-logo"><Logo/></div><span className={`boot-icon ${unauthorized ? "warn" : "bad"}`}>{unauthorized ? <LockKeyhole/> : <TriangleAlert/>}</span><p className="eyebrow">{unauthorized ? "Authentication required" : "Backend unavailable"}</p><h1>{unauthorized ? "Sign in to open the protected demo." : "The application will not invent replacement data."}</h1><p>{unauthorized ? "Use the authorized Off Grid demo credentials in your browser, then reload." : error}</p><button className="button primary" onClick={() => window.location.reload()}><RefreshCw/>Try again</button></main>;
  }
  if (!data) return <main className="boot-state"><div className="boot-logo"><Logo/></div><span className="spinner"/><p className="eyebrow">Loading trusted commercial state</p><h1>Stafford → evidence → action</h1><p>Fetching the current API instead of hard-coding a dashboard.</p></main>;
  return <Frame d={data}/>;
}
