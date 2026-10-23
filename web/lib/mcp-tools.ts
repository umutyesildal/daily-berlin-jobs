import {
  AgentApiInputError,
  formatJobDetailMarkdown,
  formatJobsMarkdown,
  parseJobsQuery,
  toDetailJob,
  toListJob,
  type AgentApiStatus,
  type AgentJob,
  type JobsQuery,
} from "./agent-api.ts";

export const MCP_INSTRUCTIONS = "Daily Berlin Jobs lists tech engineering jobs in Berlin and refreshes once a day. Call get_status first, then search_jobs with since set to the updated_at you saw last time (or latest=true on the first run), then get_job for details. Jobs sourced from LinkedIn have no description.";

export type McpSearchJobsInput = {
  query?: string;
  roles?: string[];
  levels?: string[];
  work_modes?: string[];
  source?: "ats" | "linkedin";
  since?: string;
  latest?: boolean;
  limit?: number;
  cursor?: string;
};

export type McpToolResult = {
  content: { type: "text"; text: string }[];
  structuredContent?: Record<string, unknown>;
  isError?: boolean;
};

function searchParamsFromMcpInput(input: McpSearchJobsInput): URLSearchParams {
  const params = new URLSearchParams();
  if (input.query !== undefined) params.set("q", input.query);
  if (input.roles?.length) params.set("role", input.roles.join(","));
  if (input.levels?.length) params.set("level", input.levels.join(","));
  if (input.work_modes?.length) params.set("work_mode", input.work_modes.join(","));
  if (input.source !== undefined) params.set("source", input.source);
  if (input.since !== undefined) params.set("since", input.since);
  if (input.latest) params.set("latest", "1");
  if (input.limit !== undefined && !Number.isInteger(input.limit)) {
    throw new AgentApiInputError("limit must be an integer between 1 and 100");
  }
  const limit = input.limit ?? 20;
  params.set("limit", String(Math.min(100, Math.max(1, limit))));
  if (input.cursor !== undefined) params.set("cursor", input.cursor);
  return params;
}

export function buildJobsQueryFromMcpInput(input: McpSearchJobsInput): JobsQuery {
  return parseJobsQuery(searchParamsFromMcpInput(input));
}

export function mcpStatusResult(status: AgentApiStatus): McpToolResult {
  return {
    content: [{ type: "text", text: JSON.stringify(status) }],
    structuredContent: status,
  };
}

export function mcpSearchJobsResult(input: {
  originalInput: McpSearchJobsInput;
  query: JobsQuery;
  updatedAt: string;
  jobs: AgentJob[];
  nextCursor: string | null;
  baseUrl: string;
}): McpToolResult {
  const params = searchParamsFromMcpInput(input.originalInput);
  params.set("format", "md");
  const requestUrl = `${input.baseUrl}/api/v1/jobs?${params.toString()}`;
  const markdown = formatJobsMarkdown({
    jobs: input.jobs,
    updatedAt: input.updatedAt,
    baseUrl: input.baseUrl,
    requestUrl,
    query: { ...input.query, format: "md" },
    nextCursor: input.nextCursor,
  });
  return {
    content: [{ type: "text", text: markdown }],
    structuredContent: {
      updated_at: input.updatedAt,
      next_cursor: input.nextCursor,
      jobs: input.jobs.map((job) => toListJob(job, input.baseUrl)),
    },
  };
}

export function mcpJobResult(
  job: AgentJob | null,
  updatedAt: string,
  baseUrl: string,
): McpToolResult {
  if (!job) return mcpToolError("Job not found");
  return {
    content: [{ type: "text", text: formatJobDetailMarkdown(job) }],
    structuredContent: toDetailJob(job, baseUrl, updatedAt),
  };
}

export function mcpToolError(message: string): McpToolResult {
  return {
    isError: true,
    content: [{ type: "text", text: message }],
  };
}
