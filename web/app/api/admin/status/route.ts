import { isAdmin } from "@/lib/auth";
import { workflowStatus } from "@/lib/github";
import { getAdminSourceHealth } from "@/lib/postgres";

export async function GET() {
  if (!(await isAdmin())) return Response.json({ error: "Unauthorized" }, { status: 401 });
  try {
    const [workflow, sourceHealth] = await Promise.all([
      workflowStatus(),
      getAdminSourceHealth().catch(() => []),
    ]);
    return Response.json({ ...workflow, source_health: sourceHealth });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Could not load status" }, { status: 502 });
  }
}
