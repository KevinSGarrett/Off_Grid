import { describe, expect, it } from "vitest";

import {
  ApiRequestError,
  type ApiGetter,
  loadDashboardWith,
  loadGeneralizationWith,
  retryOptionalDependencyWith,
} from "./api";
import type { OptionalDependencyKey } from "./types";

const PROJECT_ID = "project-1";

function payload(path: string): unknown {
  const values: Record<string, unknown> = {
    "/projects?limit=500": {
      items: [{ id: PROJECT_ID, external_id: "1007341663", canonical_name: "Demo project" }],
    },
    [`/projects/${PROJECT_ID}/assessment`]: { assessment: { disposition: "VERIFY" }, factors: [], dimensions: [], product_fits: [] },
    [`/projects/${PROJECT_ID}/signals`]: { items: [] },
    [`/projects/${PROJECT_ID}/evidence`]: { items: [] },
    [`/projects/${PROJECT_ID}/quality`]: { items: [] },
    [`/projects/${PROJECT_ID}/organizations`]: { items: [] },
    [`/projects/${PROJECT_ID}/contact-candidates`]: { items: [] },
    [`/projects/${PROJECT_ID}/actions`]: { items: [], ordering: "DEPENDENCY_EXECUTION_ASC", first_call_kit: {} },
    [`/projects/${PROJECT_ID}/commercial-motions`]: { project_id: PROJECT_ID, items: [] },
    [`/projects/${PROJECT_ID}/apollo-preview`]: {
      project_id: PROJECT_ID, eligible: true, organization: "EE Reed Construction",
      search: { mode: "PREVIEW", method: "POST", endpoint: "https://api.apollo.io/api/v1/mixed_people/api_search", params: {}, credit_consuming: false, external_request_executed: false, note: "Preview" },
      enrichment: null, external_requests_executed: 0,
    },
    [`/projects/${PROJECT_ID}/crm-readiness`]: { lead_ready: true, deal_ready: false, deal_blockers: [] },
    [`/exceptions?project_id=${PROJECT_ID}`]: { count: 0, items: [] },
    [`/projects/${PROJECT_ID}/sensitivity`]: { baseline: { overall_band: "Promising candidate", operational_action: "VERIFY" }, counterfactuals: [] },
    "/readiness": { integrations: { openai: { enabled: true, credentials_present: true } } },
    "/metrics": { generated_at: "2026-08-12T00:00:00Z", primary_kpi: { display: "N/A" }, diagnostics: {}, definitions: {} },
    [`/projects/${PROJECT_ID}/crm-preview`]: { pipedrive: { mode: "dry_run", requests: [] }, external_writes_executed: 0 },
    "/monday-brief": { primary_kpi: { display: "N/A" }, pipeline: {}, metric_definitions: {}, pipeline_semantics: "Demo snapshot", attention_required: [] },
  };
  if (!(path in values)) throw new Error(`Unexpected test path: ${path}`);
  return values[path];
}

function mockGetter(failingPath?: string): ApiGetter {
  return async <T>(path: string): Promise<T> => {
    if (path === failingPath) throw new ApiRequestError(503, "req-safe-503");
    return payload(path) as T;
  };
}

describe("dashboard boot dependency isolation", () => {
  it("loads generalized data and invokes zero-write triage with explicit project ids", async () => {
    const calls: Array<{ path: string; init?: RequestInit }> = [];
    const getter: ApiGetter = async <T>(path: string, init?: RequestInit): Promise<T> => {
      calls.push({ path, init });
      if (path === "/portfolio/projects") return {
        items: [{ id: PROJECT_ID, featured_case: true, relationships: [{ organization_id: "org-1", role: "GENERAL CONTRACTOR" }] }],
        summary: {}, semantics: {}, count: 1,
      } as T;
      if (path === "/organizations/org-1/intelligence") return { canonical_name: "EE Reed" } as T;
      if (path === `/organizations/org-1/source-contacts?comparison_project_id=${PROJECT_ID}`) return { items: [], count: 0 } as T;
      if (path === "/portfolio/triage") return { total_records: 1, full_eligible: 1, source_only: 0, external_writes_executed: 0 } as T;
      throw new Error(`Unexpected test path: ${path}`);
    };

    const result = await loadGeneralizationWith(getter);

    expect(result.triage.external_writes_executed).toBe(0);
    expect(calls.find((call) => call.path === "/portfolio/triage")?.init).toMatchObject({ method: "POST" });
    expect(calls.find((call) => call.path === "/portfolio/triage")?.init?.body).toBe(JSON.stringify({ project_ids: [PROJECT_ID] }));
  });

  it.each([
    ["analyst_readiness", "/readiness", "systemReadiness"],
    ["metrics", "/metrics", "metrics"],
    ["crm_preview", `/projects/${PROJECT_ID}/crm-preview`, "crm"],
    ["monday_brief", "/monday-brief", "monday"],
  ] as const)("isolates %s failure without rejecting core boot", async (key, path, field) => {
    const result = await loadDashboardWith(mockGetter(path), PROJECT_ID);

    expect(result.project.id).toBe(PROJECT_ID);
    expect(result[field]).toBeNull();
    expect(result.optionalFailures[key]).toMatchObject({
      key,
      status: 503,
      request_id: "req-safe-503",
    });
  });

  it("retries only the failed optional dependency and clears its failure", async () => {
    const failed = await loadDashboardWith(mockGetter("/metrics"), PROJECT_ID);
    const recovered = await retryOptionalDependencyWith(failed, "metrics", mockGetter());

    expect(recovered.metrics).not.toBeNull();
    expect(recovered.optionalFailures.metrics).toBeUndefined();
    expect(recovered.project).toBe(failed.project);
  });

  it("keeps a failed retry isolated", async () => {
    const initial = await loadDashboardWith(mockGetter("/metrics"), PROJECT_ID);
    const retried = await retryOptionalDependencyWith(initial, "metrics", mockGetter("/metrics"));

    expect(retried.metrics).toBeNull();
    expect(retried.optionalFailures.metrics?.message).toContain("Core intelligence remains available");
  });

  it("fails core boot with a safe request identifier", async () => {
    await expect(loadDashboardWith(mockGetter("/projects?limit=500"), PROJECT_ID)).rejects.toMatchObject({
      name: "ApiRequestError",
      status: 503,
      requestId: "req-safe-503",
      message: "The requested service is unavailable.",
    });
  });

  it("rejects unsafe request identifiers instead of reflecting them", () => {
    const error = new ApiRequestError(500, "<script>private-path</script>");
    expect(error.requestId).toBeNull();
  });

  it.each<OptionalDependencyKey>([
    "analyst_readiness", "metrics", "crm_preview", "monday_brief",
  ])("uses a stable failure key for %s", async (key) => {
    const paths: Record<OptionalDependencyKey, string> = {
      analyst_readiness: "/readiness",
      metrics: "/metrics",
      crm_preview: `/projects/${PROJECT_ID}/crm-preview`,
      monday_brief: "/monday-brief",
    };
    const result = await loadDashboardWith(mockGetter(paths[key]), PROJECT_ID);
    expect(result.optionalFailures[key]?.key).toBe(key);
  });
});

describe("commercial analyst streaming", () => {
  it("returns only the validated SSE payload", async () => {
    const stream = new ReadableStream({
      start(controller) {
        const encoder = new TextEncoder();
        controller.enqueue(encoder.encode('event: progress\ndata: {"stage":"packet"}\n\n'));
        controller.enqueue(encoder.encode('event: validated\ndata: {"status":"SUCCEEDED","answer":{"direct_conclusion":"Grounded"}}\n\n'));
        controller.enqueue(encoder.encode("event: done\ndata: {}\n\n"));
        controller.close();
      },
    });
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => new Response(stream, { status: 200 });
    try {
      const { askAnalyst } = await import("./api");
      const result = await askAnalyst(PROJECT_ID, "Why pursue this project?");
      expect(result.status).toBe("SUCCEEDED");
      expect(result.answer?.direct_conclusion).toBe("Grounded");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
