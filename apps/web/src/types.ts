export type ApiRecord = Record<string, any>;
export type Evidence = {
  evidence_id: string; field_name: string; classification: string; page_number: number | null;
  section_name: string | null; excerpt: string | null; confidence_state: string;
  validation_state: string; scoring_treatment: string; decision_eligible: boolean;
};
export type DashboardData = {
  project: ApiRecord; assessment: ApiRecord; signals: ApiRecord[]; evidence: Evidence[]; quality: ApiRecord[];
  projectOrganizations: ApiRecord; organization: ApiRecord | null; organizationProjects: ApiRecord | null;
  organizationContacts: ApiRecord | null; candidates: ApiRecord; actions: ApiRecord; motions: ApiRecord;
  crm: ApiRecord; readiness: ApiRecord; metrics: ApiRecord; monday: ApiRecord; exceptions: ApiRecord; sensitivity: ApiRecord;
};
export type AnalystResponse = ApiRecord;
