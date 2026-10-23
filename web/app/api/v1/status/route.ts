import { jsonResponse } from "@/lib/agent-api";
import { getAgentStatus } from "@/lib/postgres";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request): Promise<Response> {
  const baseUrl = new URL(request.url).origin;
  const status = await getAgentStatus(baseUrl);
  return jsonResponse(request, status.updated_at, status);
}
