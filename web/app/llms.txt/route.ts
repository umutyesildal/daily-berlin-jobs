import { textResponse } from "@/lib/agent-api";
import { getLlmsText } from "@/lib/agent-texts";
import { getAgentUpdatedAt } from "@/lib/postgres";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request): Promise<Response> {
  const baseUrl = new URL(request.url).origin;
  const updatedAt = await getAgentUpdatedAt();
  return textResponse(request, updatedAt, getLlmsText(baseUrl), "text/plain; charset=utf-8");
}
