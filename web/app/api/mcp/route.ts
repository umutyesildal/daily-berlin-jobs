import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { z } from "zod";
import webPackage from "../../../package.json";
import {
  buildCompaniesQueryFromMcpInput,
  groupAndFilterCompanies,
  mcpCompaniesResult,
  type McpListCompaniesInput,
} from "@/lib/companies-api";
import {
  getAgentJob,
  getAgentJobs,
  getAgentStatus,
  getAgentUpdatedAt,
  getApiCompanyRows,
} from "@/lib/postgres";
import {
  buildJobsQueryFromMcpInput,
  MCP_INSTRUCTIONS,
  mcpJobResult,
  mcpSearchJobsResult,
  mcpStatusResult,
  mcpToolError,
  type McpSearchJobsInput,
} from "@/lib/mcp-tools";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Accept, MCP-Protocol-Version, Mcp-Session-Id",
  "Cache-Control": "no-store",
};

function withMcpHeaders(response: Response): Response {
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(CORS_HEADERS)) headers.set(name, value);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function methodNotAllowed(): Response {
  return withMcpHeaders(Response.json({ error: "Method not allowed" }, {
    status: 405,
    headers: { Allow: "POST, OPTIONS" },
  }));
}

export async function GET(): Promise<Response> {
  return methodNotAllowed();
}

export async function DELETE(): Promise<Response> {
  return methodNotAllowed();
}

export async function OPTIONS(): Promise<Response> {
  return withMcpHeaders(new Response(null, { status: 204 }));
}

export async function POST(request: Request): Promise<Response> {
  try {
    const baseUrl = new URL(request.url).origin;
    const server = new McpServer(
      { name: "daily-berlin-jobs", version: webPackage.version },
      { instructions: MCP_INSTRUCTIONS },
    );

    server.registerTool(
      "get_status",
      {
        description: "Get when the Berlin tech jobs list was last updated, how many jobs it holds, and the valid filter values for search_jobs. Call this first to learn the allowed roles, levels and work modes. Read-only.",
        annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
      },
      async () => mcpStatusResult(await getAgentStatus(baseUrl)),
    );

    server.registerTool(
      "search_jobs",
      {
        description: "Search current tech and engineering job postings in Berlin from Daily Berlin Jobs, refreshed once a day. Covers software, data/AI, platform/DevOps, security, mobile, QA, embedded and engineering leadership roles in Berlin only; it does not cover other cities or non-tech jobs. Filter by keyword, role, level and work mode; use since or latest to see new jobs; results are paginated with cursor. Read-only.",
        inputSchema: z.object({
          query: z.string().optional().describe(
            "Optional keyword phrase matched against job titles, company names and tech-stack terms.",
          ),
          roles: z.array(z.string()).optional().describe(
            "Filter by roles returned by get_status: Backend, Data / AI / ML, Embedded / Firmware / Robotics, Engineering Leadership, Frontend, Fullstack, Mobile, Platform / DevOps / SRE, QA / Test, Security, Software Engineering.",
          ),
          levels: z.array(z.string()).optional().describe(
            "Filter by levels returned by get_status: Intern / Working Student, Junior / Entry, Lead, Manager / Head / Director, Not specified, Senior, Staff / Principal.",
          ),
          work_modes: z.array(z.string()).optional().describe(
            "Filter by work modes returned by get_status: Hybrid, On-site, Remote.",
          ),
          source: z.enum(["ats", "linkedin"]).optional().describe(
            "Optionally limit results to jobs from ats or linkedin.",
          ),
          since: z.string().optional().describe(
            "Only include jobs first seen after this ISO 8601 timestamp.",
          ),
          latest: z.boolean().optional().describe(
            "When true, limit results to jobs from the latest data update.",
          ),
          limit: z.number().int().min(1).max(100).default(20).describe(
            "Maximum number of jobs to return per page (1-100; default 20).",
          ),
          cursor: z.string().optional().describe(
            "Pagination cursor returned as next_cursor from the previous search_jobs response.",
          ),
        }),
        annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
      },
      async (input) => {
        const originalInput = input as McpSearchJobsInput;
        try {
          const query = buildJobsQueryFromMcpInput(originalInput);
          const result = await getAgentJobs(query);
          return mcpSearchJobsResult({
            originalInput,
            query,
            updatedAt: result.updatedAt,
            jobs: result.jobs,
            nextCursor: result.nextCursor,
            baseUrl,
          });
        } catch (error) {
          return mcpToolError(error instanceof Error ? error.message : "Invalid search input");
        }
      },
    );

    server.registerTool(
      "get_job",
      {
        description: "Get one current Berlin job posting by its numeric id from search_jobs, including its description when available. Jobs sourced from LinkedIn have no description; ask the user to paste the ad text in that case. Read-only.",
        inputSchema: z.object({
          id: z.number().int().describe("Numeric id from a current search_jobs result."),
        }),
        annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
      },
      async ({ id }) => {
        const [job, updatedAt] = await Promise.all([
          getAgentJob(String(id)),
          getAgentUpdatedAt(),
        ]);
        return mcpJobResult(job, updatedAt, baseUrl);
      },
    );

    server.registerTool(
      "list_companies",
      {
        description: "List companies with active Berlin tech job sources and their number of open jobs. Optionally filter by company name or applicant tracking system, or only companies with open jobs. Read-only.",
        inputSchema: z.object({
          query: z.string().optional().describe("Optional substring to match company names."),
          ats: z.string().optional().describe("Optional applicant tracking system to filter companies."),
          has_jobs: z.boolean().optional().describe("If true, include only companies with open jobs."),
        }),
        annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
      },
      async (input) => {
        const filters = buildCompaniesQueryFromMcpInput(input as McpListCompaniesInput);
        const [rows, updatedAt] = await Promise.all([
          getApiCompanyRows(),
          getAgentUpdatedAt(),
        ]);
        const companies = groupAndFilterCompanies(rows, baseUrl, filters);
        return mcpCompaniesResult(updatedAt, companies);
      },
    );

    const transport = new WebStandardStreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
      enableJsonResponse: true,
    });
    await server.connect(transport);
    return withMcpHeaders(await transport.handleRequest(request));
  } catch {
    return withMcpHeaders(Response.json({ error: "MCP request failed" }, { status: 500 }));
  }
}
