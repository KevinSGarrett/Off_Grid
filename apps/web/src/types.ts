export type ApiRecord = Record<string, unknown>;
export type JsonBody = Record<string, string | number | boolean | null>;

export type Project = {
  id: string; external_id: string; canonical_name: string; stage: string; category?: string | null;
  city: string; region: string; reported_value?: string | number | null; start_date?: string | null;
  completion_date?: string | null; country_code?: string | null; phase_label?: string | null;
};
export type PortfolioRelationship = {
  organization_id: string; organization: string; role: string; verification_state: string;
};
export type PortfolioProject = Project & {
  featured_case: boolean; source_sections: string[]; source_occurrence_count: number;
  source_roles: string[]; relationships: PortfolioRelationship[]; source_bid_date?: string | null;
  source_contact_available: boolean; source_freshness_at?: string | null; source_freshness_band: string;
  assessment_coverage: "FULL" | "PARTIAL" | "SOURCE_ONLY" | "INSUFFICIENT";
  coverage_explanation: string; commercial_fit_score: string | number | null;
  commercial_band: string | null; data_confidence_score: string | number | null;
  data_confidence: string | null; operational_action: string | null;
  quality_warning_count: number; quality_state: string; available_source_field_count: number;
  source_report_types: string[]; source_document_count: number; coverage_reason_codes: string[];
  project_group?: { id: string; canonical_name: string; group_type: string } | null;
};
export type PortfolioResponse = {
  summary: {
    source_documents: number; detailed_project_documents: number; company_documents: number;
    detailed_project_records: number; source_project_rows: number; canonical_projects: number;
    company_history_projects: number; source_only_projects: number; projects_assessed: number;
    projects_partially_assessable: number; projects_with_insufficient_evidence: number;
    project_quality_warnings: number;
    coverage_counts: Record<string, number>;
  };
  items: PortfolioProject[]; count: number;
  semantics: { source_rows: string; assessment_coverage: string; scores: string };
};
export type AccountIntelligence = {
  organization_id: string; canonical_name: string; constructconnect_company_id: string | null;
  source_project_rows: number; source_section_counts: Record<string, number>;
  unique_projects: number; source_contact_rows: number; canonical_source_contacts: number;
  generic_inbox_records: number; inactive_source_contacts: number; known_domain_count: number;
  report_date: string | null; source_company_last_update: string | null;
  source_company_last_update_note: string; quality_flag_counts: Record<string, number>;
  activity_bands: Array<{ band: string; source_row_count: number; unique_project_count: number }>;
  project_type_counts: Record<string, number>; geography_counts: Record<string, number>;
  unique_project_geographies: number;
  domain_states: Record<string, string>; strategic_signal_band: string;
  entity_resolution_state: string; account_recommendation: string; caveats: string[];
};
export type BatchTriageResponse = {
  total_records: number; full_eligible: number; partial: number; source_only: number;
  insufficient: number; assessed: number; review_required: number;
  external_writes_executed: number; semantics: string;
  ranked_assessments: Array<{ project_id: string; commercial_fit_score: string; commercial_band: string; operational_action: string }>;
};
export type SourceContact = {
  person_id: string; display_name: string; source_status: string; employment_state: string;
  source_occurrence_count: number; aliases: string[];
  contact_points: Array<{ type: string; value: string; verification_state: string; is_generic: boolean; is_primary: boolean }>;
  domains: string[]; generic_inbox: boolean; identity_quality: string;
  quality_findings: Array<{ rule_code: string; severity: string; state: string; title: string }>;
  project_association_count: number; selected_project_association: string; rank_eligible: boolean;
  rank_eligibility_reason: string; investigation_status: string;
};
export type SourceContactsResponse = {
  organization_id: string; items: SourceContact[]; count: number; source_row_count: number;
  demo_mode: boolean;
  funnel: {
    source_directory_rows: number; canonical_source_identities: number;
    source_people_with_any_project_association: number; project_research_candidates: number;
    current_top_investigation_candidates: number; authority_verified: number;
    top_candidate: string | null; sets_are_distinct: boolean;
  };
  semantics: { directory: string; candidates: string };
};
export type GeneralizationData = {
  portfolio: PortfolioResponse; account: AccountIntelligence; sourceContacts: SourceContactsResponse;
  triage: BatchTriageResponse;
};
export type Assessment = {
  overall_band: string; operational_action: string; confidence_state: string;
  data_confidence_score: string | number; commercial_fit_score?: string | number;
};
export type AssessmentDimension = { key: string; label: string; band: string };
export type ProductFit = {
  product_code: string; applicability_status: string; explanation: string;
  characteristic_relevance_score: string | number;
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
  evidence_origins?: string[];
  verification?: {
    employment?: string; project_association?: string; role_relevance?: string;
    rental_authority?: string; assessed_at?: string;
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
export type ApolloRequestPreview = {
  mode: string; method: string; endpoint: string; params: ApiRecord;
  credit_consuming: boolean; external_request_executed: boolean; note: string;
};
export type ApolloPreview = {
  project_id: string; eligible: boolean; reason?: string; project?: string;
  organization?: string; organization_role?: string; supported_domains?: string[];
  target_personas?: string[]; location_filters?: string[]; purpose?: string;
  search?: ApolloRequestPreview;
  enrichment?: {
    candidate_id: string; person_id: string; display_name: string; target_persona: string;
    request: ApolloRequestPreview; before: Record<string, string>; constraints: string[];
  } | null;
  external_requests_executed: number;
};
export type SystemReadiness = {
  demo_mode?: boolean; external_writes_allowed?: boolean | string;
  integrations?: Record<string, {
    status?: string; mode?: string; enabled?: boolean; implemented?: boolean;
    live_capable?: boolean; credentials_present?: boolean; connection_checked?: boolean;
    external_writes_enabled?: boolean; search_available?: boolean; enrichment_gated?: boolean;
    reason?: string | null;
  }>;
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
export type OptionalDependencyKey = "analyst_readiness" | "metrics" | "crm_preview" | "monday_brief";
export type OptionalDependencyFailure = {
  key: OptionalDependencyKey; label: string; status: number | null;
  request_id: string | null; message: string;
};
export type DashboardData = {
  project: Project; assessment: AssessmentResponse; signals: ProjectSignal[]; evidence: Evidence[];
  quality: QualityWarning[]; projectOrganizations: ProjectOrganizationsResponse;
  organization: Organization | null; organizationProjects: OrganizationProjectsResponse | null;
  organizationContacts: OrganizationContactsResponse | null; candidates: ContactCandidatesResponse;
  actions: ActionsResponse; motions: CommercialMotionsResponse; apollo: ApolloPreview; crm: CRMPreview | null; readiness: CRMReadiness;
  systemReadiness: SystemReadiness | null; metrics: Metrics | null; monday: MondayBrief | null;
  exceptions: ExceptionsResponse; sensitivity: SensitivityResponse;
  optionalFailures: Partial<Record<OptionalDependencyKey, OptionalDependencyFailure>>;
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
