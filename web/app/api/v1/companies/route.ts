import { jsonResponse, textResponse } from "@/lib/agent-api";
import { formatCompaniesMarkdown, groupAndFilterCompanies } from "@/lib/companies-api";
import { getAgentUpdatedAt, getApiCompanyRows } from "@/lib/postgres";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const baseUrl = url.origin;
  const updatedAt = await getAgentUpdatedAt();
  const companies = groupAndFilterCompanies(await getApiCompanyRows(), baseUrl, {
    q: url.searchParams.get("q") ?? undefined,
    ats: url.searchParams.get("ats") ?? undefined,
    has_jobs: url.searchParams.get("has_jobs") === "1",
  });

  if (url.searchParams.get("format") === "md" || url.pathname === "/companies.md") {
    return textResponse(
      request,
      updatedAt,
      formatCompaniesMarkdown(companies),
      "text/markdown; charset=utf-8",
    );
  }
  return jsonResponse(request, updatedAt, {
    updated_at: updatedAt,
    count: companies.length,
    companies,
  });
}
