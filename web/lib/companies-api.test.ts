import assert from "node:assert/strict";
import test from "node:test";
import { getSampleAgentJobs } from "./sample-data.ts";
import {
  buildCompaniesQueryFromMcpInput,
  formatCompaniesMarkdown,
  groupAndFilterCompanies,
  mcpCompaniesResult,
  sampleCompanyRows,
  type ApiCompanySourceRow,
} from "./companies-api.ts";

const rows: ApiCompanySourceRow[] = [
  {
    company_id: 1,
    name: "Acme Labs",
    website: "https://acme.example",
    ats: "greenhouse",
    career_page: "https://boards.greenhouse.io/acme",
    health: "ok",
    last_checked_at: "2026-10-23T10:00:00.000Z",
    open_jobs: 3,
  },
  {
    company_id: 1,
    name: "Acme Labs",
    website: "https://acme.example",
    ats: "workday",
    career_page: "https://acme.wd1.myworkdayjobs.com/careers",
    health: "error",
    last_checked_at: null,
    open_jobs: 3,
  },
  {
    company_id: 2,
    name: "Beta Systems",
    website: "https://beta.example",
    ats: "greenhouse",
    career_page: "https://boards.greenhouse.io/beta",
    health: "empty",
    last_checked_at: null,
    open_jobs: 5,
  },
  {
    company_id: 3,
    name: "Zero Jobs",
    website: "https://zero.example",
    ats: "phenom",
    career_page: "https://careers.zero.example/search-results",
    health: null,
    last_checked_at: null,
    open_jobs: 0,
  },
];

test("company rows group per company, sort by jobs, then name, and filter exactly", () => {
  const companies = groupAndFilterCompanies(rows, "https://daily.example");
  assert.deepEqual(companies.map((company) => [company.name, company.open_jobs]), [
    ["Beta Systems", 5],
    ["Acme Labs", 3],
    ["Zero Jobs", 0],
  ]);
  const acme = companies[1];
  assert.equal(acme.slug, "acme-labs");
  assert.equal(acme.company_page, "https://daily.example/companies/acme-labs");
  assert.deepEqual(acme.sources.map((source) => source.ats), ["greenhouse", "workday"]);
  assert.equal(acme.sources[0]?.last_checked_at, "2026-10-23T10:00:00.000Z");

  assert.deepEqual(
    groupAndFilterCompanies(rows, "https://daily.example", { q: "ACME" }).map((company) => company.name),
    ["Acme Labs"],
  );
  assert.deepEqual(
    groupAndFilterCompanies(rows, "https://daily.example", { ats: "workday" }).map((company) => company.name),
    ["Acme Labs"],
  );
  assert.deepEqual(
    groupAndFilterCompanies(rows, "https://daily.example", { ats: "work" }),
    [],
  );
  assert.deepEqual(
    groupAndFilterCompanies(rows, "https://daily.example", { has_jobs: true }).map((company) => company.name),
    ["Beta Systems", "Acme Labs"],
  );
});

test("company Markdown uses one line with the website, ATS labels, count, and page link", () => {
  const companies = groupAndFilterCompanies(rows, "https://daily.example");
  assert.equal(
    formatCompaniesMarkdown(companies).split("\n")[1],
    "- **Acme Labs** — https://acme.example · greenhouse, workday · 3 open jobs · "
      + "[jobs](https://daily.example/companies/acme-labs)",
  );
});

test("MCP company filters map to API filters and structured results match the JSON shape", () => {
  const filters = buildCompaniesQueryFromMcpInput({
    query: "Acme",
    ats: "workday",
    has_jobs: true,
  });
  assert.deepEqual(filters, { q: "Acme", ats: "workday", has_jobs: true });

  const companies = groupAndFilterCompanies(rows, "https://daily.example", filters);
  const result = mcpCompaniesResult("2026-10-23T10:00:00.000Z", companies);
  assert.equal(result.structuredContent.updated_at, "2026-10-23T10:00:00.000Z");
  assert.equal(result.structuredContent.count, 1);
  assert.match(result.content[0].text, /^\- \*\*Acme Labs\*\*/);
  assert.deepEqual(result.structuredContent.companies, companies);
});

test("sample company rows derive companies from jobs and include websites", () => {
  const companies = groupAndFilterCompanies(sampleCompanyRows(getSampleAgentJobs()), "https://daily.example");

  assert.ok(companies.length > 0);
  assert.ok(companies.every((company) => company.website?.startsWith("https://")));
  assert.ok(companies.some((company) => company.name === "Open Source Labs"));
});
