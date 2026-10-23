import {
  AgentApiInputError,
  formatJobsMarkdown,
  jsonResponse,
  parseJobsRequest,
  textResponse,
  toListJob,
  type JobsQuery,
} from "@/lib/agent-api";
import { getAgentJobs, getAgentUpdatedAt } from "@/lib/postgres";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  let query: JobsQuery;
  try {
    query = parseJobsRequest(url.pathname, url.searchParams);
  } catch (error) {
    if (!(error instanceof AgentApiInputError)) throw error;
    const updatedAt = await getAgentUpdatedAt();
    return jsonResponse(request, updatedAt, { error: error.message }, 400);
  }

  const result = await getAgentJobs(query);
  if (query.format === "md") {
    return textResponse(
      request,
      result.updatedAt,
      formatJobsMarkdown({
        jobs: result.jobs,
        updatedAt: result.updatedAt,
        baseUrl: url.origin,
        requestUrl: request.url,
        query,
        nextCursor: result.nextCursor,
      }),
      "text/markdown; charset=utf-8",
    );
  }

  return jsonResponse(request, result.updatedAt, {
    updated_at: result.updatedAt,
    count: result.jobs.length,
    next_cursor: result.nextCursor,
    jobs: result.jobs.map((job) => toListJob(job, url.origin)),
  });
}
