import assert from "node:assert/strict";
import test from "node:test";
import { isLinkedInJob } from "./jobs.ts";

test("recognizes LinkedIn jobs from their stored source", () => {
  assert.equal(isLinkedInJob({ source: "LinkedIn", link: "https://example.com/job/1" }), true);
  assert.equal(isLinkedInJob({ source: "linkedin", link: "" }), true);
});

test("uses the canonical URL as a fallback without matching lookalike hosts", () => {
  assert.equal(isLinkedInJob({ source: "", link: "https://de.linkedin.com/jobs/view/123" }), true);
  assert.equal(isLinkedInJob({ source: "", link: "https://linkedin.com.example.org/jobs/123" }), false);
  assert.equal(isLinkedInJob({ source: "Greenhouse", link: "not a URL" }), false);
});
