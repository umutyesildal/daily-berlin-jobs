import assert from "node:assert/strict";
import test from "node:test";
import {
  buildJobsQueryFromMcpInput,
  MCP_INSTRUCTIONS,
  mcpJobResult,
  mcpSearchJobsResult,
  mcpStatusResult,
} from "./mcp-tools.ts";
import type { AgentApiStatus, AgentJob } from "./agent-api.ts";

const job: AgentJob = {
  id: 1,
  company: "Open Source Labs",
  title: "Backend Engineer",
  location: "Berlin, Germany",
  url: "https://example.com/jobs/1",
  role: "Backend",
  level: "Senior",
  workMode: "Hybrid",
  employmentType: "Full-time",
  department: "Engineering",
  techStack: ["TypeScript"],
  postedDate: "2026-10-22",
  firstSeenAt: "2026-10-23T04:00:00.000Z",
  lastSeenAt: "2026-10-23T05:00:00.000Z",
  sourceType: "ats",
  description: "<p>Build dependable services.</p>",
};

test("MCP server instructions describe the daily status-search-detail routine", () => {
  assert.equal(
    MCP_INSTRUCTIONS,
    "Daily Berlin Jobs lists tech engineering jobs in Berlin and refreshes once a day. Call get_status first, then search_jobs with since set to the updated_at you saw last time (or latest=true on the first run), then get_job for details. Jobs sourced from LinkedIn have no description.",
  );
});

test("MCP search query defaults, clamps the page size, and joins filter arrays", () => {
  const defaults = buildJobsQueryFromMcpInput({});
  assert.equal(defaults.limit, 20);
  assert.deepEqual(defaults.roles, []);
  assert.equal(defaults.format, "json");
  assert.equal(buildJobsQueryFromMcpInput({ limit: 250 }).limit, 100);
  assert.equal(buildJobsQueryFromMcpInput({ limit: 0 }).limit, 1);

  const query = buildJobsQueryFromMcpInput({
    query: "platform",
    roles: ["Backend", "Fullstack"],
    levels: ["Senior", "Junior / Entry"],
    work_modes: ["Remote", "Hybrid"],
    source: "ats",
    latest: true,
    limit: 30,
  });
  assert.equal(query.query, "platform");
  assert.deepEqual(query.roles, ["backend", "fullstack"]);
  assert.deepEqual(query.levels, ["senior", "junior / entry"]);
  assert.deepEqual(query.workModes, ["remote", "hybrid"]);
  assert.equal(query.source, "ats");
  assert.equal(query.latest, true);
  assert.equal(query.limit, 30);
});

test("MCP search query delegates ISO validation to the agent API parser", () => {
  assert.throws(
    () => buildJobsQueryFromMcpInput({ since: "not-a-date" }),
    /valid ISO 8601 timestamp/,
  );
});

test("MCP status result includes JSON text and structured content", () => {
  const status: AgentApiStatus = {
    updated_at: "2026-10-23T05:00:00.000Z",
    updated_at_berlin: "2026-10-23 07:00 Europe/Berlin",
    job_count: 2,
    latest_update_count: 1,
    last_run: { inserted: 1, updated: 0, deleted: 0 },
    stale: false,
    next_expected_window: {
      from: "2026-10-24T05:00:00.000Z",
      to: "2026-10-24T06:30:00.000Z",
    },
    filters: { roles: ["Backend"], levels: ["Senior"], work_modes: ["Hybrid"] },
    sources: {
      active: 10,
      healthy: 8,
      empty: 1,
      failing: 1,
      unchecked: 0,
      disabled_last_7_days: 1,
      last_checked_at: "2026-10-23T04:00:00.000Z",
    },
    docs: {
      llms_txt: "https://daily.example/llms.txt",
      agents_md: "https://daily.example/agents.md",
      jobs_md: "https://daily.example/jobs.md",
      today_md: "https://daily.example/today.md",
      rss: "https://daily.example/feed.xml",
    },
  };
  const result = mcpStatusResult(status);

  assert.deepEqual(result.structuredContent, status);
  assert.deepEqual(JSON.parse(result.content[0].text), status);
});

test("MCP search result shapes Markdown and structured list jobs", () => {
  const originalInput = { roles: ["Backend"], limit: 20 };
  const query = buildJobsQueryFromMcpInput(originalInput);
  const result = mcpSearchJobsResult({
    originalInput,
    query,
    updatedAt: "2026-10-23T05:00:00.000Z",
    jobs: [job],
    nextCursor: null,
    baseUrl: "https://daily.example",
  });

  assert.match(result.content[0].text, /^# Daily Berlin Jobs/m);
  assert.match(result.content[0].text, /\*\*Backend Engineer\*\*/);
  assert.deepEqual(result.structuredContent, {
    updated_at: "2026-10-23T05:00:00.000Z",
    next_cursor: null,
    jobs: [{
      id: 1,
      title: "Backend Engineer",
      company: "Open Source Labs",
      location: "Berlin, Germany",
      url: "https://example.com/jobs/1",
      detail_url: "https://daily.example/api/v1/jobs/1",
      role: "Backend",
      level: "Senior",
      work_mode: "Hybrid",
      tech_stack: ["TypeScript"],
      posted_date: "2026-10-22",
      first_seen_at: "2026-10-23T04:00:00.000Z",
      source: "ats",
    }],
  });
});

test("MCP job results match the REST detail shape and report missing jobs as tool errors", () => {
  const result = mcpJobResult(job, "2026-10-23T05:00:00.000Z", "https://daily.example");
  assert.match(result.content[0].text, /Build dependable services/);
  assert.equal(result.structuredContent?.updated_at, "2026-10-23T05:00:00.000Z");
  assert.equal(result.structuredContent?.description, "<p>Build dependable services.</p>");
  assert.equal(result.structuredContent?.description_available, true);

  const linkedin = mcpJobResult(
    { ...job, sourceType: "linkedin", description: null },
    "2026-10-23T05:00:00.000Z",
    "https://daily.example",
  );
  assert.equal(linkedin.structuredContent?.description, null);
  assert.equal(linkedin.structuredContent?.description_available, false);
  assert.match(linkedin.content[0].text, /description not available/i);

  const missing = mcpJobResult(null, "2026-10-23T05:00:00.000Z", "https://daily.example");
  assert.equal(missing.isError, true);
  assert.equal(missing.content[0].text, "Job not found");
});
