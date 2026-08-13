import type {
  ActionsResponse, AnalystResponse, ApiRecord, AssessmentResponse, CommercialMotionsResponse,
  ContactCandidatesResponse, CRMPreview, CRMReadiness, DashboardData, Evidence, ExceptionsResponse,
  Metrics, MondayBrief, Organization, OrganizationContactsResponse, OrganizationProjectsResponse,
  Project, ProjectOrganizationsResponse, ProjectSignal, QualityWarning, SensitivityResponse,
  SystemReadiness,
} from "./types";
const ROOT = "/api/v1";
async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${ROOT}${path}`, { headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }, ...init });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`);
  return response.json() as Promise<T>;
}
export async function loadDashboard(): Promise<DashboardData> {
  const projects = await get<{ items: Project[] }>("/projects?limit=500");
  const project = projects.items.find((row) => row.external_id === "1007341663");
  if (!project) throw new Error("Stafford golden-path project is not loaded in the backend.");
  const id = project.id;
  const [assessment, signals, evidence, quality, projectOrganizations, candidates, actions, motions, crm, readiness, systemReadiness, metrics, monday, exceptions, sensitivity] = await Promise.all([
    get<AssessmentResponse>(`/projects/${id}/assessment`), get<{ items: ProjectSignal[] }>(`/projects/${id}/signals`), get<{ items: Evidence[] }>(`/projects/${id}/evidence`),
    get<{ items: QualityWarning[] }>(`/projects/${id}/quality`), get<ProjectOrganizationsResponse>(`/projects/${id}/organizations`), get<ContactCandidatesResponse>(`/projects/${id}/contact-candidates`),
    get<ActionsResponse>(`/projects/${id}/actions`), get<CommercialMotionsResponse>(`/projects/${id}/commercial-motions`), get<CRMPreview>(`/projects/${id}/crm-preview`),
    get<CRMReadiness>(`/projects/${id}/crm-readiness`), get<SystemReadiness>("/readiness"), get<Metrics>("/metrics"), get<MondayBrief>("/monday-brief"),
    get<ExceptionsResponse>(`/exceptions?project_id=${id}`), get<SensitivityResponse>(`/projects/${id}/sensitivity`, { method: "POST", body: "{}" }),
  ]);
  const gc = projectOrganizations.items.find((row: any) => /general contractor/i.test(row.role));
  let organization = null, organizationProjects = null, organizationContacts = null;
  if (gc) [organization, organizationProjects, organizationContacts] = await Promise.all([
    get<Organization>(`/organizations/${gc.organization_id}`), get<OrganizationProjectsResponse>(`/organizations/${gc.organization_id}/projects`), get<OrganizationContactsResponse>(`/organizations/${gc.organization_id}/contacts`),
  ]);
  return { project, assessment, signals: signals.items, evidence: evidence.items, quality: quality.items, projectOrganizations, organization, organizationProjects, organizationContacts, candidates, actions, motions, crm, readiness, systemReadiness, metrics, monday, exceptions, sensitivity };
}
export function askAnalyst(projectId: string, question: string, mode = "FAST", conversationContext: ApiRecord[] = []): Promise<AnalystResponse> {
  return get<AnalystResponse>("/analyst/query", { method: "POST", body: JSON.stringify({ project_id: projectId, question, mode, conversation_context: conversationContext }) });
}
