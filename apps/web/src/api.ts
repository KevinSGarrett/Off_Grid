import type {
  ActionsResponse, AnalystResponse, ApiRecord, AssessmentResponse, CommercialMotionsResponse,
  ContactCandidatesResponse, CRMPreview, CRMReadiness, DashboardData, Evidence, ExceptionsResponse,
  Metrics, MondayBrief, OptionalDependencyFailure, OptionalDependencyKey, Organization,
  OrganizationContactsResponse, OrganizationProjectsResponse, Project, ProjectOrganizationsResponse,
  ProjectSignal, QualityWarning, SensitivityResponse, SystemReadiness, GeneralizationData,
  PortfolioResponse, AccountIntelligence, SourceContactsResponse,
  ApolloPreview, BatchTriageResponse,
} from "./types";

const ROOT = "/api/v1";

export const CORE_BOOT_ENDPOINTS = [
  "projects", "assessment", "signals", "evidence", "quality", "project_organizations",
  "contact_candidates", "actions", "commercial_motions", "crm_readiness", "exceptions",
  "sensitivity", "organization_context",
] as const;

export const OPTIONAL_BOOT_ENDPOINTS: Record<OptionalDependencyKey, string> = {
  analyst_readiness: "/readiness",
  metrics: "/metrics",
  crm_preview: "/projects/{project_id}/crm-preview",
  monday_brief: "/monday-brief",
};

const OPTIONAL_LABELS: Record<OptionalDependencyKey, string> = {
  analyst_readiness: "Analyst readiness",
  metrics: "System diagnostics",
  crm_preview: "CRM preview",
  monday_brief: "Monday Morning Brief",
};

function safeRequestId(value: string | null | undefined): string | null {
  if (!value) return null;
  return /^[A-Za-z0-9._:-]{1,80}$/.test(value) ? value : null;
}

export class ApiRequestError extends Error {
  readonly status: number | null;
  readonly requestId: string | null;

  constructor(status: number | null, requestId: string | null = null) {
    super(status === 401 ? "Authentication required." : "The requested service is unavailable.");
    this.name = "ApiRequestError";
    this.status = status;
    this.requestId = safeRequestId(requestId);
  }
}

export type ApiGetter = <T>(path: string, init?: RequestInit) => Promise<T>;

export const get: ApiGetter = async <T>(path: string, init?: RequestInit): Promise<T> => {
  let response: Response;
  try {
    response = await fetch(`${ROOT}${path}`, {
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
  } catch {
    throw new ApiRequestError(null);
  }
  if (!response.ok) {
    throw new ApiRequestError(response.status, response.headers.get("x-request-id"));
  }
  return response.json() as Promise<T>;
};

function optionalFailure(key: OptionalDependencyKey, reason: unknown): OptionalDependencyFailure {
  const error = reason instanceof ApiRequestError ? reason : new ApiRequestError(null);
  return {
    key,
    label: OPTIONAL_LABELS[key],
    status: error.status,
    request_id: error.requestId,
    message: `${OPTIONAL_LABELS[key]} is temporarily unavailable. Core intelligence remains available.`,
  };
}

async function optional<T>(
  key: OptionalDependencyKey,
  request: () => Promise<T>,
): Promise<{ value: T | null; failure: OptionalDependencyFailure | null }> {
  try {
    return { value: await request(), failure: null };
  } catch (reason) {
    return { value: null, failure: optionalFailure(key, reason) };
  }
}

export async function loadDashboardWith(
  client: ApiGetter,
  selectedProjectId: string,
): Promise<DashboardData> {
  const projects = await client<{ items: Project[] }>("/projects?limit=500");
  const project = projects.items.find((row) => row.id === selectedProjectId);
  if (!project) throw new ApiRequestError(404);
  const id = project.id;

  const [
    assessment, signals, evidence, quality, projectOrganizations, candidates, actions, motions, apollo,
    readiness, exceptions, sensitivity,
  ] = await Promise.all([
    client<AssessmentResponse>(`/projects/${id}/assessment`),
    client<{ items: ProjectSignal[] }>(`/projects/${id}/signals`),
    client<{ items: Evidence[] }>(`/projects/${id}/evidence`),
    client<{ items: QualityWarning[] }>(`/projects/${id}/quality`),
    client<ProjectOrganizationsResponse>(`/projects/${id}/organizations`),
    client<ContactCandidatesResponse>(`/projects/${id}/contact-candidates`),
    client<ActionsResponse>(`/projects/${id}/actions`),
    client<CommercialMotionsResponse>(`/projects/${id}/commercial-motions`),
    client<ApolloPreview>(`/projects/${id}/apollo-preview`),
    client<CRMReadiness>(`/projects/${id}/crm-readiness`),
    client<ExceptionsResponse>(`/exceptions?project_id=${id}`),
    client<SensitivityResponse>(`/projects/${id}/sensitivity`, { method: "POST", body: "{}" }),
  ]);

  const [systemReadinessResult, metricsResult, crmResult, mondayResult] = await Promise.all([
    optional("analyst_readiness", () => client<SystemReadiness>("/readiness")),
    optional("metrics", () => client<Metrics>("/metrics")),
    optional("crm_preview", () => client<CRMPreview>(`/projects/${id}/crm-preview`)),
    optional("monday_brief", () => client<MondayBrief>("/monday-brief")),
  ]);

  const gc = projectOrganizations.items.find((row) => /general contractor/i.test(row.role));
  let organization = null;
  let organizationProjects = null;
  let organizationContacts = null;
  if (gc) {
    [organization, organizationProjects, organizationContacts] = await Promise.all([
      client<Organization>(`/organizations/${gc.organization_id}`),
      client<OrganizationProjectsResponse>(`/organizations/${gc.organization_id}/projects`),
      client<OrganizationContactsResponse>(`/organizations/${gc.organization_id}/contacts`),
    ]);
  }

  const failures = [
    systemReadinessResult.failure, metricsResult.failure, crmResult.failure, mondayResult.failure,
  ].filter((failure): failure is OptionalDependencyFailure => failure !== null);

  return {
    project,
    assessment,
    signals: signals.items,
    evidence: evidence.items,
    quality: quality.items,
    projectOrganizations,
    organization,
    organizationProjects,
    organizationContacts,
    candidates,
    actions,
    motions,
    apollo,
    crm: crmResult.value,
    readiness,
    systemReadiness: systemReadinessResult.value,
    metrics: metricsResult.value,
    monday: mondayResult.value,
    exceptions,
    sensitivity,
    optionalFailures: Object.fromEntries(failures.map((failure) => [failure.key, failure])),
  };
}

export function loadDashboard(selectedProjectId: string): Promise<DashboardData> {
  return loadDashboardWith(get, selectedProjectId);
}

export async function loadInitialApplication(): Promise<{ dashboard: DashboardData; generalization: GeneralizationData }> {
  const generalization = await loadGeneralization();
  const featured = generalization.portfolio.items.find((row) => row.featured_case);
  if (!featured) throw new ApiRequestError(404);
  return { dashboard: await loadDashboard(featured.id), generalization };
}

export async function loadGeneralizationWith(client: ApiGetter): Promise<GeneralizationData> {
  const portfolio = await client<PortfolioResponse>("/portfolio/projects");
  const featured = portfolio.items.find((row) => row.featured_case);
  if (!featured) throw new ApiRequestError(404);
  const gc = featured.relationships.find((row) => /general contractor/i.test(row.role));
  if (!gc) throw new ApiRequestError(404);
  const [account, sourceContacts, triage] = await Promise.all([
    client<AccountIntelligence>(`/organizations/${gc.organization_id}/intelligence`),
    client<SourceContactsResponse>(`/organizations/${gc.organization_id}/source-contacts?comparison_project_id=${featured.id}`),
    client<BatchTriageResponse>("/portfolio/triage", {
      method: "POST",
      body: JSON.stringify({ project_ids: portfolio.items.map((row) => row.id) }),
    }),
  ]);
  return { portfolio, account, sourceContacts, triage };
}

export function loadGeneralization(): Promise<GeneralizationData> {
  return loadGeneralizationWith(get);
}

export async function retryOptionalDependencyWith(
  data: DashboardData,
  key: OptionalDependencyKey,
  client: ApiGetter,
): Promise<DashboardData> {
  const id = data.project.id;
  const requests: Record<OptionalDependencyKey, () => Promise<unknown>> = {
    analyst_readiness: () => client<SystemReadiness>("/readiness"),
    metrics: () => client<Metrics>("/metrics"),
    crm_preview: () => client<CRMPreview>(`/projects/${id}/crm-preview`),
    monday_brief: () => client<MondayBrief>("/monday-brief"),
  };
  const result = await optional(key, requests[key]);
  const nextFailures = { ...data.optionalFailures };
  if (result.failure) nextFailures[key] = result.failure;
  else delete nextFailures[key];
  const update =
    key === "analyst_readiness" ? { systemReadiness: result.value as SystemReadiness | null }
      : key === "metrics" ? { metrics: result.value as Metrics | null }
        : key === "crm_preview" ? { crm: result.value as CRMPreview | null }
          : { monday: result.value as MondayBrief | null };
  return { ...data, ...update, optionalFailures: nextFailures };
}

export function retryOptionalDependency(
  data: DashboardData,
  key: OptionalDependencyKey,
): Promise<DashboardData> {
  return retryOptionalDependencyWith(data, key, get);
}

export async function askAnalyst(
  projectId: string,
  question: string,
  mode = "FAST",
  conversationContext: ApiRecord[] = [],
): Promise<AnalystResponse> {
  let response: Response;
  try {
    response = await fetch(`${ROOT}/analyst/query/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId, question, mode, conversation_context: conversationContext }),
    });
  } catch {
    throw new ApiRequestError(null);
  }
  if (!response.ok || !response.body) {
    throw new ApiRequestError(response.status, response.headers.get("x-request-id"));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let validated: AnalystResponse | null = null;
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const event of events) {
      const type = event.split("\n").find((line) => line.startsWith("event:"))?.slice(6).trim();
      const data = event.split("\n").find((line) => line.startsWith("data:"))?.slice(5).trim();
      if (type === "validated" && data) validated = JSON.parse(data) as AnalystResponse;
    }
    if (done) break;
  }
  if (!validated) throw new ApiRequestError(502);
  return validated;
}
