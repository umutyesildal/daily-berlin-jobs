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
        description: "Get the latest data update time, counts, filters, and API links.",
        annotations: { readOnlyHint: true, openWorldHint: false },
      },
      async () => mcpStatusResult(await getAgentStatus(baseUrl)),
    );

    server.registerTool(
      "search_jobs",
      {
        description: "Search current Berlin engineering jobs with filters and keyset pagination.",
        inputSchema: z.object({
          query: z.string().optional(),
          roles: z.array(z.string()).optional(),
          levels: z.array(z.string()).optional(),
          work_modes: z.array(z.string()).optional(),
          source: z.enum(["ats", "linkedin"]).optional(),
          since: z.string().optional(),
          latest: z.boolean().optional(),
          limit: z.number().int().min(1).max(100).default(20),
          cursor: z.string().optional(),
        }),
        annotations: { readOnlyHint: true, openWorldHint: false },
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
        description: "Get a current job listing and its available description.",
        inputSchema: z.object({ id: z.number().int() }),
        annotations: { readOnlyHint: true, openWorldHint: false },
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
        description: "List companies with active Berlin job sources and their open-job counts.",
        inputSchema: z.object({
          query: z.string().optional(),
          ats: z.string().optional(),
          has_jobs: z.boolean().optional(),
        }),
        annotations: { readOnlyHint: true, openWorldHint: false },
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
