import assert from "node:assert/strict";
import test from "node:test";
import { getSampleAgentJobs, getSampleJobsSnapshot } from "./sample-data.ts";

test("sample mode always contains current rolling dates", () => {
  const snapshot = getSampleJobsSnapshot();
  const today = new Date().toISOString().slice(0, 10);
  assert.equal(snapshot.all[0]?.postedDate, today);
  assert.equal(snapshot.daily.length, 3);
  assert.equal(snapshot.all.find((job) => job.company === "Responsible AI Berlin")?.source, "linkedin");
});

test("sample API jobs include metadata and redact LinkedIn descriptions", () => {
  const jobs = getSampleAgentJobs(new Date("2026-10-23T05:00:00Z"));
  assert.ok(jobs.every((job) => job.id && job.firstSeenAt && job.sourceType && "description" in job));
  const linkedinJob = jobs.find((job) => job.sourceType === "linkedin");
  assert.ok(linkedinJob);
  assert.equal(linkedinJob.description, null);
});
