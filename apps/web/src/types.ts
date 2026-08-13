export type ApiRecord = Record<string, unknown>;
export type JsonBody = Record<string, string | number | boolean | null>;

export type Project = {
  id: string; external_id: string; canonical_name: string; stage: string; category?: string | null;
  city: string; region: string; reported_value?: string | number | null;
};
export type Assessment = {
  overall_band: string; operational_action: string; confidence_state: string;
  data_confidence_score: string | number; commercial_fit_score?: string | number;
};
export type AssessmentDimension = { key: string; label: string; band: string };
export type ProductFit = {
  product_code: string; applicability_status: string; explanation: string;
  missing_evidence: string | string[] | null;
};
export type AssessmentResponse = {
  assessment: Assessment; dimensions: AssessmentDimension[]; product_fits: ProductFit[];
};
export type ProjectSignal = {
  id: string; key: string; value?: string | number | null; explanation?: string | null;
  classification: string;
};
export type Evidence = {
  evidence_id: string; field_name: string; classification: string; page_number: number | null;
  section_name: string | null; excerpt: string | null; confidence_state: string;
  validation_state: string; scoring_treatment: string; decision_eligible: boolean;
};
export type QualityWarning = {
  id: string; title: string; detail?: string | null; decision_impact?: string | null;
  rule_code: string; severity: string; state: string; review_status: string;
  blocks_progression: boolean; recommended_action: string;
};
export type ProjectOrganization = { organization_id: string; role: string };
export type RelatedProject = {
  id?: string; project_id: string; canonical_name: string; stage?: string | null;
  reported_value?: string | number | null; verification_state?: string | null;
};
export type ProjectGroup = { canonical_name: string; projects: RelatedProject[] };
export type ProjectOrganizationsResponse = {
  items: ProjectOrganization[]; project_group?: ProjectGroup | null;
};
export type Organization = {
  canonical_name: string;
  domains?: Array<{ domain: string; relationship_state: string }>;
};
export type OrganizationProjectsResponse = { items: RelatedProject[] };
export type OrganizationContact = {
  status?: string | null;
  contact_points: Array<{ is_generic: boolean }>;
};
export type OrganizationContactsResponse = { items: OrganizationContact[] };
export type ContactCandidate = {
  candidate_id: string; display_name: string; target_persona: string;
  candidate_score: string | number; rationale?: string | null;
  verification?: {
    employment?: string; project_association?: string; role_relevance?: string;
    rental_authority?: string;
  } | null;
};
export type ContactCandidatesResponse = { count: number; items: ContactCandidate[] };
export type CommercialAction = {
  id: string; commercial_motion_id?: string | null; dependency_action_id?: string | null;
  dependency_action_type?: string | null; action_type: string; status: string; priority: number;
  owner?: string | null; reason: string; due_at?: string | null; completed_at?: string | null;
};
export type FirstCallKit = {
  version: string; target_candidate_id?: string | null; target_person_name: string;
  target_status: string; objective: string; questions: string[]; after_call_capture: string[];
  safeguards: string[];
};
export type ActionsResponse = {
  project_id: string; ordering: "DEPENDENCY_EXECUTION_ASC";
  items: CommercialAction[]; first_call_kit: FirstCallKit;
};
export type CommercialMotion = {
  id: string; motion_type: "CONTRACTOR" | "RENTAL_HOUSE"; organization_id?: string | null;
  status: string; demand_strength?: string | null; confidence_state: string;
  demand_display: string; owner?: string | null; summary: string;
  dependency_map: Array<{ label: string; state: string; source: string }>;
};
export type CommercialMotionsResponse = { project_id: string; items: CommercialMotion[] };
export type CRMReadiness = {
  version: string; project_id: string; project_external_id: string;
  commercial_fit: string | number; data_confidence: string | number;
  lead_ready: boolean; deal_ready: boolean; permitted_promotion: string;
  checks: Array<{ key: string; passed: boolean; applies_to: string[]; rationale: string }>;
  lead_blockers: string[]; deal_blockers: string[];
};
export type CRMRequestBody = JsonBody & {
  name?: string; title?: string; org_id?: string; organization_id?: string; person_id?: string;
};
export type CRMRequest = {
  object_type: "ORGANIZATION" | "PERSON" | "LEAD" | "DEAL" | null;
  label: string; method: string; path: string; body: CRMRequestBody;
  query: JsonBody; dependencies: string[]; status: string; blocked_reason: string | null;
  canonical_key: string | null;
};
export type CRMPreview = {
  readiness: CRMReadiness;
  pipedrive: { version: string; mode: string; lead_ready: boolean; deal_ready: boolean; requests: CRMRequest[]; external_writes_executed: number; notes: string[] };
  sheets: ApiRecord; forms: ApiRecord; trello: ApiRecord; external_writes_executed: number;
};
export type SystemReadiness = {
  integrations?: { openai?: { enabled: boolean; credentials_present: boolean; reason?: string | null } };
};
export type MetricDefinition = {
  key: string; label: string; definition: string; interpretation: string;
};
export type Metrics = {
  generated_at: string;
  primary_kpi: { key: string; name: string; display: string; status: string; definition: string; interpretation: string };
  diagnostics: Record<string, number>;
  definitions: Record<string, MetricDefinition>;
};
export type MondayBrief = {
  primary_kpi: Metrics["primary_kpi"]; pipeline: Record<string, number>;
  metric_definitions: Record<string, MetricDefinition>; pipeline_semantics: string;
  top_opportunity?: { name: string } | null;
  attention_required: Array<{ id: string; item_type: "WORKFLOW_EXCEPTION"; summary: string; detail?: string | null; status: string; priority: number; recommended_action: string }>;
};
export type WorkflowException = {
  id: string; summary: string; detail?: string | null; decision_impact?: string | null;
  status: string; priority: string | number; severity?: string; blocks_progression?: boolean;
};
export type ExceptionsResponse = { count: number; items: WorkflowException[] };
export type SensitivityResponse = {
  baseline: { overall_band: string; operational_action: string };
  counterfactuals: Array<{ key: string; label?: string; band?: string; action?: string }>;
};
export type DashboardData = {
  project: Project; assessment: AssessmentResponse; signals: ProjectSignal[]; evidence: Evidence[];
  quality: QualityWarning[]; projectOrganizations: ProjectOrganizationsResponse;
  organization: Organization | null; organizationProjects: OrganizationProjectsResponse | null;
  organizationContacts: OrganizationContactsResponse | null; candidates: ContactCandidatesResponse;
  actions: ActionsResponse; motions: CommercialMotionsResponse; crm: CRMPreview; readiness: CRMReadiness;
  systemReadiness: SystemReadiness; metrics: Metrics; monday: MondayBrief;
  exceptions: ExceptionsResponse; sensitivity: SensitivityResponse;
};
export type AnalystClaim = {
  claim_id: string; classification: string; claim_text: string; rationale: string;
  evidence_ids?: string[];
};
export type AnalystAnswer = {
  direct_conclusion: string; answer: string; claims?: AnalystClaim[];
  decision_changing_unknowns?: string[];
};
export type AnalystResponse = {
  status: string; answer?: AnalystAnswer | null; external_request_executed: boolean;
  cache_hit?: boolean; model_id?: string | null; grounding?: { status: string } | null;
  tool_rounds?: number; latency_ms?: number; estimated_cost_usd?: string | number;
  fallback_reason?: string | null;
};
