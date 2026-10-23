import { formatRss, parseJobsQuery, textResponse } from "@/lib/agent-api";
import { getAgentJobs } from "@/lib/postgres";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const query = parseJobsQuery(new URLSearchParams("limit=100"));
  const result = await getAgentJobs(query);
  return textResponse(
    request,
    result.updatedAt,
    formatRss(result.jobs, url.origin, result.updatedAt),
    "application/rss+xml; charset=utf-8",
  );
}
