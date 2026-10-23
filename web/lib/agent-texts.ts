const llmsText = [
  "# Daily Berlin Jobs",
  "",
  "> Open-source board of tech engineering jobs in Berlin: software, data/AI, platform/DevOps/SRE, security, mobile, QA and embedded. Refreshed once a day. Free, read-only, no API key.",
  "",
  "The data is refreshed once per day, usually between 06:00 and 07:30 Europe/Berlin. Always read the status endpoint first and treat its `updated_at` as the source of truth; do not assume a fixed update time.",
  "",
  "## For agents",
  "",
  "- [Agent instructions](${base}/agents.md): a ready-made routine for a scheduled daily job check",
  "- [Status](${base}/api/v1/status): last update time, job counts, next expected update window, allowed filter values",
  "- [New in the latest update (Markdown)](${base}/today.md)",
  "- [All open jobs (Markdown)](${base}/jobs.md)",
  "",
  "## API",
  "",
  "- [Jobs (JSON)](${base}/api/v1/jobs): query parameters `since` (ISO 8601; jobs first seen after this time), `latest=1` (jobs added in the most recent update), `role`, `level`, `work_mode` (comma-separated, values listed in status `filters`), `q` (free text over title, company and tech stack), `source` (`ats` or `linkedin`), `limit` (1-500, default 100), `cursor` (from `next_cursor`), `format=md`",
  "- Job detail: `${base}/api/v1/jobs/{id}` (JSON) or `${base}/jobs/{id}.md` (Markdown)",
  "- [RSS feed](${base}/feed.xml)",
  "",
  "## Notes",
  "",
  "- Jobs are removed 30 days after posting.",
  "- Full descriptions are included only for jobs that come from a company's own career site (`source: \"ats\"`). Jobs with `source: \"linkedin\"` include metadata and a link only.",
  "- Responses are cached and change about once a day; a few requests per run are enough.",
  "- Source code and issues: https://github.com/umutyesildal/daily-berlin-jobs",
].join("\n");

const agentsText = [
  "# Daily Berlin Jobs: routine for AI agents",
  "",
  "Use this file as the instructions for a scheduled AI agent, for example a task that runs every day at 08:00 Europe/Berlin. Base URL: ${base}",
  "",
  "## Ask the user once and keep with the task",
  "",
  "- Roles, e.g. Backend, Fullstack (allowed values: `filters.roles` in ${base}/api/v1/status)",
  "- Levels, e.g. Junior / Entry, Senior",
  "- Work mode: Remote, Hybrid, On-site, or any",
  "- Must-have and nice-to-have skills, e.g. TypeScript, PostgreSQL",
  "- Whether German-language roles are acceptable",
  "- Deal-breakers, e.g. recruitment agencies, on-site only",
  "",
  "## Daily routine",
  "",
  "1. GET ${base}/api/v1/status and read `updated_at`.",
  "   - If `updated_at` is not newer than the value you saved last time, the data has not been refreshed yet. Check again later; `next_expected_window` tells you when the next refresh is expected. If `stale` is true, tell the user the data may be out of date.",
  "2. Get the jobs added since your last run:",
  "   GET ${base}/api/v1/jobs?since=<saved updated_at>&role=<roles>&level=<levels>&work_mode=<mode>",
  "   - On the very first run, use `latest=1` instead of `since`.",
  "   - If `next_cursor` is not null, request the same URL with `cursor=<next_cursor>` until it is null.",
  "3. Shortlist jobs whose title, role, level and tech_stack fit the profile. For each shortlisted job, GET its `detail_url` and read the description when `description_available` is true. Check language requirements, seniority and deal-breakers. If the description is not available, judge from the metadata and say so.",
  "4. Report to the user: the best matches, each with title, company, why it fits, any concerns, and the apply link. If nothing fits, say so in one line. Only use information present in the data; do not invent salaries, visa sponsorship or requirements.",
  "5. Save the `updated_at` value from step 1 and use it as `since` on the next run.",
  "",
  "## Notes",
  "",
  "- Free and read-only; no API key. Responses are cached and change about once a day, so keep each run to a handful of requests.",
  "- Jobs are removed 30 days after posting.",
  "- Prefer the apply link from the data; do not guess company career URLs.",
].join("\n");

export function getLlmsText(baseUrl: string): string {
  return llmsText.replaceAll("${base}", () => baseUrl);
}

export function getAgentsText(baseUrl: string): string {
  return agentsText.replaceAll("${base}", () => baseUrl);
}
