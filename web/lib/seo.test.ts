import assert from "node:assert/strict";
import test from "node:test";
import { getSampleAgentJobs } from "./sample-data.ts";
import {
  buildCategoryIntro,
  buildJobPostingJsonLd,
  CATEGORIES,
  htmlToText,
  SITE_URL,
  slugify,
} from "./seo.ts";
import type { AgentJob } from "./agent-api.ts";

const atsJob: AgentJob = {
  id: 1,
  company: "Acme Labs",
  title: "Senior Backend Engineer",
  location: "Berlin, Germany",
  url: "https://example.com/jobs/1",
  role: "Backend",
  level: "Senior",
  workMode: "Hybrid",
  employmentType: "Full-time",
  department: "Engineering",
  techStack: [],
  postedDate: "2026-01-31",
  firstSeenAt: "2026-02-01T10:00:00.000Z",
  lastSeenAt: "2026-02-01T10:00:00.000Z",
  sourceType: "ats",
  description: "<p>Build <strong>reliable</strong> systems.</p><p>Use &lt;open&gt; standards.</p>",
};

test("slugify normalizes umlauts, ampersands, and punctuation", () => {
  assert.equal(slugify("München & Co."), "munchen-co");
  assert.equal(slugify("  R&D / Platform  "), "r-d-platform");
});

test("site URL has no trailing slash and falls back to the production origin", () => {
  assert.equal(SITE_URL.endsWith("/"), false);
  assert.equal(
    SITE_URL,
    (process.env.SITE_URL?.trim() || "https://daily-berlin-jobs.vercel.app").replace(/\/+$/, ""),
  );
});

test("category slugs and filters match the supported search vocabulary", () => {
  const expected = [
    ["backend-engineer-jobs", "Backend"],
    ["frontend-engineer-jobs", "Frontend"],
    ["fullstack-engineer-jobs", "Fullstack"],
    ["data-ai-ml-jobs", "Data / AI / ML"],
    ["devops-platform-sre-jobs", "Platform / DevOps / SRE"],
    ["security-engineer-jobs", "Security"],
    ["mobile-developer-jobs", "Mobile"],
    ["embedded-engineer-jobs", "Embedded / Firmware / Robotics"],
    ["qa-test-engineer-jobs", "QA / Test"],
    ["engineering-manager-jobs", "Engineering Leadership"],
    ["software-engineer-jobs", "Software Engineering"],
    ["remote-engineering-jobs", "Remote"],
    ["hybrid-engineering-jobs", "Hybrid"],
    ["junior-developer-jobs", "Junior / Entry"],
    ["working-student-internship-jobs", "Intern / Working Student"],
    ["senior-engineer-jobs", "Senior"],
    ["staff-principal-engineer-jobs", "Staff / Principal"],
  ];
  assert.deepEqual(
    CATEGORIES.map(({ slug, filter }) => [
      slug,
      filter.roles?.[0] ?? filter.levels?.[0] ?? filter.workModes?.[0],
    ]),
    expected,
  );
  assert.equal(new Set(CATEGORIES.map((category) => category.slug)).size, CATEGORIES.length);

  const samples = getSampleAgentJobs();
  const roles = new Set([
    ...samples.map((job) => job.role),
    "Frontend",
    "Security",
    "Mobile",
    "QA / Test",
    "Engineering Leadership",
    "Software Engineering",
  ]);
  const levels = new Set([
    ...samples.map((job) => job.level),
    "Intern / Working Student",
    "Junior / Entry",
    "Staff / Principal",
    "Senior",
  ]);
  const workModes = new Set(samples.map((job) => job.workMode));
  for (const category of CATEGORIES) {
    for (const value of category.filter.roles ?? []) assert.ok(roles.has(value), value);
    for (const value of category.filter.levels ?? []) assert.ok(levels.has(value), value);
    for (const value of category.filter.workModes ?? []) assert.ok(workModes.has(value), value);
  }
});

test("HTML-to-text removes markup and preserves paragraph breaks", () => {
  assert.equal(
    htmlToText("<p>First <strong>paragraph</strong>.</p><p>Second&nbsp;paragraph.</p>"),
    "First paragraph.\n\nSecond paragraph.",
  );
});

test("JobPosting JSON-LD is withheld for LinkedIn and empty descriptions", () => {
  assert.equal(
    buildJobPostingJsonLd({ ...atsJob, sourceType: "linkedin" }),
    null,
  );
  assert.equal(
    buildJobPostingJsonLd({ ...atsJob, description: "  " }),
    null,
  );
});

test("JobPosting JSON-LD maps dates, employment types, remote requirements, and escapes <", () => {
  const jsonLd = buildJobPostingJsonLd(atsJob);
  assert.ok(jsonLd);
  assert.doesNotMatch(jsonLd, /</);
  const posting = JSON.parse(jsonLd);
  assert.equal(posting.datePosted, "2026-01-31");
  assert.equal(posting.validThrough, "2026-03-02");
  assert.equal(posting.employmentType, "FULL_TIME");
  assert.equal(posting.directApply, false);
  assert.equal(posting.jobLocationType, undefined);
  assert.equal(posting.applicantLocationRequirements, undefined);
  assert.equal(posting.description, "Build reliable systems.\n\nUse <open> standards.");

  for (const [value, schemaValue] of [
    ["Part-time", "PART_TIME"],
    ["Internship", "INTERN"],
    ["Contract", "CONTRACTOR"],
    ["Freelance", "CONTRACTOR"],
  ]) {
    const serialized = buildJobPostingJsonLd({ ...atsJob, employmentType: value });
    assert.ok(serialized);
    assert.equal(JSON.parse(serialized).employmentType, schemaValue);
  }

  const remote = buildJobPostingJsonLd({ ...atsJob, workMode: "Remote" });
  assert.ok(remote);
  const remotePosting = JSON.parse(remote);
  assert.equal(remotePosting.jobLocationType, "TELECOMMUTE");
  assert.deepEqual(remotePosting.applicantLocationRequirements, {
    "@type": "Country",
    name: "Germany",
  });
});

test("category intro uses counts, top companies, and remote share", () => {
  const intro = buildCategoryIntro([
    { company: "Acme", workMode: "Remote" },
    { company: "Acme", workMode: "Hybrid" },
    { company: "Berlin Labs", workMode: "Remote" },
    { company: "Civic", workMode: "On-site" },
    { company: "Delta", workMode: "On-site" },
  ]);
  assert.equal(
    intro,
    "5 current jobs; top companies: Acme, Berlin Labs, Civic; 40% are remote.",
  );
});
