import type { AnalystResponse, DashboardData } from "./types";
const ROOT = "/api/v1";
async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${ROOT}${path}`, { headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }, ...init });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`);
  return response.json() as Promise<T>;
}
export async function loadDashboard(): Promise<DashboardData> {
  const projects = await get<any>("/projects?limit=500");
  const project = projects.items.find((row: any) => row.external_id === "1007341663");
  if (!project) throw new Error("Stafford golden-path project is not loaded in the backend.");
  const id = project.id;
  const [assessment, signals, evidence, quality, projectOrganizations, candidates, actions, motions, crm, readiness, metrics, monday, exceptions, sensitivity] = await Promise.all([
    get<any>(`/projects/${id}/assessment`), get<any>(`/projects/${id}/signals`), get<any>(`/projects/${id}/evidence`),
    get<any>(`/projects/${id}/quality`), get<any>(`/projects/${id}/organizations`), get<any>(`/projects/${id}/contact-candidates`),
    get<any>(`/projects/${id}/actions`), get<any>(`/projects/${id}/commercial-motions`), get<any>(`/projects/${id}/crm-preview`),
    get<any>(`/projects/${id}/crm-readiness`), get<any>("/metrics"), get<any>("/monday-brief"),
    get<any>(`/exceptions?project_id=${id}`), get<any>(`/projects/${id}/sensitivity`, { method: "POST", body: "{}" }),
  ]);
  const gc = projectOrganizations.items.find((row: any) => /general contractor/i.test(row.role));
  let organization = null, organizationProjects = null, organizationContacts = null;
  if (gc) [organization, organizationProjects, organizationContacts] = await Promise.all([
    get<any>(`/organizations/${gc.organization_id}`), get<any>(`/organizations/${gc.organization_id}/projects`), get<any>(`/organizations/${gc.organization_id}/contacts`),
  ]);
  return { project, assessment, signals: signals.items, evidence: evidence.items, quality: quality.items, projectOrganizations, organization, organizationProjects, organizationContacts, candidates, actions, motions, crm, readiness, metrics, monday, exceptions, sensitivity };
}
export function askAnalyst(projectId: string, question: string): Promise<AnalystResponse> {
  return get<AnalystResponse>("/analyst/query", { method: "POST", body: JSON.stringify({ project_id: projectId, question }) });
}
