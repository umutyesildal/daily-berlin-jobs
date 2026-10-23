import { hasValidCronBearer } from "@/lib/auth";
import { dispatchWorkflow } from "@/lib/github";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function cronResponse(body: { ok: boolean; skipped?: string; error?: string }, status = 200): Response {
  return Response.json(body, { status, headers: { "Cache-Control": "no-store" } });
}

export async function GET(request: Request): Promise<Response> {
  if (!hasValidCronBearer(request)) {
    return cronResponse({ ok: false, error: "Unauthorized" }, 401);
  }

  try {
    await dispatchWorkflow();
    return cronResponse({ ok: true });
  } catch (error) {
    if (error instanceof Error && error.message.toLocaleLowerCase().includes("already running")) {
      return cronResponse({ ok: true, skipped: "already running" });
    }
    return cronResponse({ ok: false, error: "Unable to dispatch daily update" }, 502);
  }
}
