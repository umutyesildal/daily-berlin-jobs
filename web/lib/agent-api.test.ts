import assert from "node:assert/strict";
import test from "node:test";
import {
  decodeCursor,
  encodeCursor,
  escapeXml,
  formatBerlinClock,
  formatJobDetailMarkdown,
  formatJobsMarkdown,
  formatRss,
  isStale,
  isMarkdownDetailRequest,
  nextExpectedWindow,
  parseJobsRequest,
  parseJobsQuery,
  type AgentJob,
} from "./agent-api.ts";

const sampleJob: AgentJob = {
  id: 12,
  company: "Berlin Systems",
  title: "Backend Engineer",
  location: "Berlin, Germany",
  url: "https://example.com/jobs/12",
  role: "Backend",
  level: "Senior",
  workMode: "Hybrid",
  employmentType: "Full-time",
  department: "Engineering",
  techStack: ["TypeScript", "PostgreSQL"],
  postedDate: "2026-10-22",
  firstSeenAt: "2026-10-23T04:50:00.000Z",
  lastSeenAt: "2026-10-23T05:00:00.000Z",
  sourceType: "ats",
  description: "Build reliable services.",
};

test("job query parsing clamps limits and normalizes comma-separated filters", () => {
  assert.equal(parseJobsQuery(new URLSearchParams()).limit, 100);
  assert.equal(parseJobsQuery(new URLSearchParams("limit=0")).limit, 1);
  assert.equal(parseJobsQuery(new URLSearchParams("limit=501")).limit, 500);

  const query = parseJobsQuery(new URLSearchParams(
    "role=Backend,%20Fullstack,backend&level=Senior,Junior&work_mode=Hybrid,Remote&source=LINKEDIN",
  ));
  assert.deepEqual(query.roles, ["backend", "fullstack"]);
  assert.deepEqual(query.levels, ["senior", "junior"]);
  assert.deepEqual(query.workModes, ["hybrid", "remote"]);
  assert.equal(query.source, "linkedin");
});

test("job query parsing rejects invalid timestamps and source values", () => {
  assert.throws(
    () => parseJobsQuery(new URLSearchParams("since=garbage")),
    /valid ISO 8601 timestamp/,
  );
  assert.throws(
    () => parseJobsQuery(new URLSearchParams("source=other")),
    /source must be ats or linkedin/,
  );
});

test("Markdown aliases select Markdown while preserving the latest-update filter", () => {
  const jobs = parseJobsRequest("/jobs.md", new URLSearchParams());
  const today = parseJobsRequest("/today.md", new URLSearchParams());
  assert.equal(jobs.format, "md");
  assert.equal(jobs.latest, false);
  assert.equal(today.format, "md");
  assert.equal(today.latest, true);
  assert.equal(isMarkdownDetailRequest("/jobs/4.md", new URLSearchParams()), true);
});

test("cursor encoding and decoding round-trip the keyset fields", () => {
  const cursor = encodeCursor(sampleJob);
  assert.deepEqual(decodeCursor(cursor), {
    firstSeenAt: sampleJob.firstSeenAt,
    id: String(sampleJob.id),
  });
});

test("Markdown list headers are present and newlines in fields collapse", () => {
  const query = parseJobsQuery(new URLSearchParams());
  const markdown = formatJobsMarkdown({
    jobs: [{ ...sampleJob, title: "Backend\nEngineer" }],
    updatedAt: "2026-10-23T05:00:00.000Z",
    baseUrl: "https://daily.example",
    requestUrl: "https://daily.example/api/v1/jobs",
    query,
    nextCursor: null,
  });
  assert.match(markdown, /^# Daily Berlin Jobs/m);
  assert.match(markdown, /\*\*Backend Engineer\*\*/);
  assert.doesNotMatch(markdown, /Backend\nEngineer/);
});

test("LinkedIn detail Markdown does not include a description", () => {
  const markdown = formatJobDetailMarkdown({
    ...sampleJob,
    sourceType: "linkedin",
    description: null,
  });
  assert.match(markdown, /description not available/i);
  assert.doesNotMatch(markdown, /Build reliable services/);
});

test("Berlin clock formatting respects the daylight-saving transition", () => {
  assert.equal(formatBerlinClock("2026-10-24T05:10:00Z"), "07:10");
  assert.equal(formatBerlinClock("2026-10-26T05:10:00Z"), "06:10");
});

test("next expected window is the next 05:00 UTC strictly after now", () => {
  assert.deepEqual(nextExpectedWindow(new Date("2026-10-23T04:59:00Z")), {
    from: "2026-10-23T05:00:00.000Z",
    to: "2026-10-23T06:30:00.000Z",
  });
  assert.deepEqual(nextExpectedWindow(new Date("2026-10-23T05:01:00Z")), {
    from: "2026-10-24T05:00:00.000Z",
    to: "2026-10-24T06:30:00.000Z",
  });
});

test("staleness begins after 26 hours", () => {
  const now = new Date("2026-10-23T10:00:00Z");
  assert.equal(isStale("2026-10-22T09:00:00Z", now), false);
  assert.equal(isStale("2026-10-22T07:00:00Z", now), true);
});

test("RSS escapes XML special characters", () => {
  assert.equal(escapeXml("A & <B> > \"C\""), "A &amp; &lt;B&gt; &gt; &quot;C&quot;");
  const rss = formatRss([{
    ...sampleJob,
    title: "Engineer & <Designer>",
  }], "https://daily.example", "2026-10-23T05:00:00Z");
  assert.match(rss, /Engineer &amp; &lt;Designer&gt;/);
});
