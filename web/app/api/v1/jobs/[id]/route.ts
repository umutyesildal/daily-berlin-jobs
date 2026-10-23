import {
  formatJobDetailMarkdown,
  isMarkdownDetailRequest,
  jsonResponse,
  textResponse,
  toDetailJob,
} from "@/lib/agent-api";
import { getAgentJob, getAgentUpdatedAt } from "@/lib/postgres";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ id: string }>;
};

const MAX_POSTGRES_ID = BigInt("9223372036854775807");

export async function GET(request: Request, context: RouteContext): Promise<Response> {
  const updatedAt = await getAgentUpdatedAt();
  const { id: rawId } = await context.params;
  if (!/^\d+$/.test(rawId) || BigInt(rawId) > MAX_POSTGRES_ID) {
    return jsonResponse(request, updatedAt, { error: "Not found" }, 404);
  }

  const job = await getAgentJob(BigInt(rawId).toString());
  if (!job) return jsonResponse(request, updatedAt, { error: "Not found" }, 404);

  const url = new URL(request.url);
  if (isMarkdownDetailRequest(url.pathname, url.searchParams)) {
    return textResponse(
      request,
      updatedAt,
      formatJobDetailMarkdown(job),
      "text/markdown; charset=utf-8",
    );
  }

  return jsonResponse(request, updatedAt, toDetailJob(job, url.origin, updatedAt));
}
