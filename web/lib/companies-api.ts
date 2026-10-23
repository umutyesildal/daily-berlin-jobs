import type { AgentJob } from "./agent-api.ts";
import { slugify } from "./seo.ts";

export type ApiCompanySourceRow = {
  company_id: string | number;
  name: string;
  website: string | null;
  ats: string;
  career_page: string;
  health: string | null;
  last_checked_at: string | Date | null;
  open_jobs: number;
};

export type CompanySource = {
  ats: string;
  career_page: string;
  health: string | null;
  last_checked_at: string | null;
};

export type ApiCompany = {
  name: string;
  slug: string;
  website: string | null;
  company_page: string;
  open_jobs: number;
  sources: CompanySource[];
};

export type CompanyFilters = {
  q?: string;
  ats?: string;
  has_jobs?: boolean;
};

export type McpListCompaniesInput = {
  query?: string;
  ats?: string;
  has_jobs?: boolean;
};

export function groupAndFilterCompanies(
  rows: ApiCompanySourceRow[],
  baseUrl: string,
  filters: CompanyFilters = {},
): ApiCompany[] {
  const grouped = new Map<string, ApiCompany>();
  for (const row of rows) {
    const key = String(row.company_id);
    let company = grouped.get(key);
    if (!company) {
      const slug = slugify(row.name);
      company = {
        name: row.name,
        slug,
        website: row.website,
        company_page: `${baseUrl}/companies/${slug}`,
        open_jobs: Number(row.open_jobs) || 0,
        sources: [],
      };
      grouped.set(key, company);
    } else {
      company.open_jobs = Math.max(company.open_jobs, Number(row.open_jobs) || 0);
      if (!company.website && row.website) company.website = row.website;
    }

    const source = {
      ats: row.ats,
      career_page: row.career_page,
      health: row.health,
      last_checked_at: row.last_checked_at
        ? new Date(row.last_checked_at).toISOString()
        : null,
    };
    if (!company.sources.some(
      (item) => item.ats === source.ats && item.career_page === source.career_page,
    )) {
      company.sources.push(source);
    }
  }

  const query = filters.q?.trim().toLocaleLowerCase() ?? "";
  const ats = filters.ats?.trim().toLocaleLowerCase() ?? "";
  return [...grouped.values()]
    .filter((company) => !query || company.name.toLocaleLowerCase().includes(query))
    .filter((company) => !filters.has_jobs || company.open_jobs > 0)
    .filter((company) => (
      !ats || company.sources.some((source) => source.ats.toLocaleLowerCase() === ats)
    ))
    .map((company) => ({
      ...company,
      sources: [...company.sources].sort(
        (left, right) => left.ats.localeCompare(right.ats)
          || left.career_page.localeCompare(right.career_page),
      ),
    }))
    .sort((left, right) => right.open_jobs - left.open_jobs || left.name.localeCompare(right.name));
}

function markdownField(value: string | null | undefined): string {
  return (value ?? "").replace(/[\r\n]+/g, " ").replace(/\s+/g, " ").trim() || "—";
}

export function formatCompaniesMarkdown(companies: ApiCompany[]): string {
  return companies.map((company) => {
    const ats = [...new Set(company.sources.map((source) => source.ats))]
      .sort((left, right) => left.localeCompare(right))
      .join(", ");
    return `- **${markdownField(company.name)}** — ${markdownField(company.website)} · `
      + `${markdownField(ats)} · ${company.open_jobs} open jobs · [jobs](${company.company_page})`;
  }).join("\n");
}

export function buildCompaniesQueryFromMcpInput(input: McpListCompaniesInput): CompanyFilters {
  return {
    q: input.query,
    ats: input.ats,
    has_jobs: input.has_jobs ?? false,
  };
}

export function mcpCompaniesResult(updatedAt: string, companies: ApiCompany[]) {
  const structuredContent = {
    updated_at: updatedAt,
    count: companies.length,
    companies,
  };
  return {
    content: [{ type: "text" as const, text: formatCompaniesMarkdown(companies) }],
    structuredContent,
  };
}

export function sampleCompanyRows(jobs: AgentJob[]): ApiCompanySourceRow[] {
  const names = [...new Set(jobs.map((job) => job.company))]
    .sort((left, right) => left.localeCompare(right));
  const companyIds = new Map(names.map((name, index) => [name, index + 1]));
  const jobCounts = new Map<string, number>();
  for (const job of jobs) jobCounts.set(job.company, (jobCounts.get(job.company) ?? 0) + 1);

  const rows = new Map<string, ApiCompanySourceRow>();
  for (const job of jobs) {
    const ats = job.sourceType === "linkedin" ? "linkedin" : "sample";
    const key = `${job.company}\u001f${ats}\u001f${job.url}`;
    if (rows.has(key)) continue;
    rows.set(key, {
      company_id: companyIds.get(job.company) ?? 0,
      name: job.company,
      website: `https://${slugify(job.company)}.example.com`,
      ats,
      career_page: job.url,
      health: "ok",
      last_checked_at: job.lastSeenAt,
      open_jobs: jobCounts.get(job.company) ?? 0,
    });
  }
  return [...rows.values()];
}
