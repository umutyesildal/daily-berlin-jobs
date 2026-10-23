export type SourceType = "ats" | "linkedin";

export type AgentJob = {
  id: number;
  company: string;
  title: string;
  location: string;
  url: string;
  role: string;
  level: string;
  workMode: string;
  employmentType: string | null;
  department: string | null;
  techStack: string[];
  postedDate: string | null;
  firstSeenAt: string;
  lastSeenAt: string;
  sourceType: SourceType;
  description: string | null;
};

export type Cursor = {
  firstSeenAt: string;
  id: string;
};

export type JobsQuery = {
  since: string | null;
  latest: boolean;
  roles: string[];
  levels: string[];
  workModes: string[];
  query: string;
  source: SourceType | null;
  limit: number;
  cursor: Cursor | null;
  format: "json" | "md";
};

export type AgentApiStatus = {
  updated_at: string;
  updated_at_berlin: string;
  job_count: number;
  latest_update_count: number;
  last_run: {
    inserted: number;
    updated: number;
    deleted: number;
  };
  stale: boolean;
  next_expected_window: {
    from: string;
    to: string;
  };
  filters: {
    roles: string[];
    levels: string[];
    work_modes: string[];
  };
  docs: {
    llms_txt: string;
    agents_md: string;
    jobs_md: string;
    today_md: string;
    rss: string;
  };
};

export class AgentApiInputError extends Error {}

function parseIsoDate(value: string): string | null {
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  if (!dateOnly && !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) {
    return null;
  }
  const datePart = value.slice(0, 10);
  const [year, month, day] = datePart.split("-").map(Number);
  const calendarDate = new Date(Date.UTC(year, month - 1, day));
  if (
    calendarDate.getUTCFullYear() !== year
    || calendarDate.getUTCMonth() !== month - 1
    || calendarDate.getUTCDate() !== day
  ) return null;
  const timestamp = dateOnly ? `${value}T00:00:00.000Z` : value;
  const milliseconds = Date.parse(timestamp);
  return Number.isFinite(milliseconds) ? timestamp : null;
}

function parseList(value: string | null): string[] {
  if (!value) return [];
  return [...new Set(value.split(",").map((item) => item.trim().toLocaleLowerCase()).filter(Boolean))];
}

export function decodeCursor(value: string): Cursor {
  try {
    const payload = JSON.parse(Buffer.from(value, "base64url").toString("utf8")) as {
      firstSeenAt?: unknown;
      id?: unknown;
    };
    if (typeof payload.firstSeenAt !== "string" || typeof payload.id !== "string" || !/^\d+$/.test(payload.id)) {
      throw new Error("Invalid cursor");
    }
    const firstSeenAt = parseIsoDate(payload.firstSeenAt);
    if (!firstSeenAt) throw new Error("Invalid cursor");
    return { firstSeenAt: payload.firstSeenAt, id: payload.id };
  } catch {
    throw new AgentApiInputError("Invalid cursor");
  }
}

export function encodeCursor(job: Pick<AgentJob, "firstSeenAt" | "id">): string {
  return Buffer.from(JSON.stringify({
    firstSeenAt: job.firstSeenAt,
    id: String(job.id),
  })).toString("base64url");
}

export function parseJobsQuery(params: URLSearchParams): JobsQuery {
  const rawSince = params.get("since");
  let since: string | null = null;
  if (rawSince !== null) {
    since = parseIsoDate(rawSince);
    if (!since) throw new AgentApiInputError("since must be a valid ISO 8601 timestamp");
  }

  let source: SourceType | null = null;
  if (params.has("source")) {
    const value = params.get("source")?.trim().toLocaleLowerCase();
    if (value !== "ats" && value !== "linkedin") {
      throw new AgentApiInputError("source must be ats or linkedin");
    }
    source = value;
  }

  const rawLimit = params.get("limit");
  const parsedLimit = rawLimit !== null && /^-?\d+$/.test(rawLimit.trim()) ? Number(rawLimit) : 100;
  const limit = Math.min(500, Math.max(1, Number.isSafeInteger(parsedLimit) ? parsedLimit : 100));
  const rawCursor = params.get("cursor");

  return {
    since,
    latest: params.get("latest") === "1",
    roles: parseList(params.get("role")),
    levels: parseList(params.get("level")),
    workModes: parseList(params.get("work_mode")),
    query: params.get("q")?.trim() ?? "",
    source,
    limit,
    cursor: rawCursor ? decodeCursor(rawCursor) : null,
    format: params.get("format")?.toLocaleLowerCase() === "md" ? "md" : "json",
  };
}

export function parseJobsRequest(pathname: string, searchParams: URLSearchParams): JobsQuery {
  const params = new URLSearchParams(searchParams);
  if (pathname === "/jobs.md") params.set("format", "md");
  if (pathname === "/today.md") {
    params.set("format", "md");
    params.set("latest", "1");
  }
  return parseJobsQuery(params);
}

export function isMarkdownDetailRequest(pathname: string, searchParams: URLSearchParams): boolean {
  return searchParams.get("format")?.toLocaleLowerCase() === "md" || /^\/jobs\/\d+\.md$/.test(pathname);
}

export function filterAndSortJobs(
  jobs: AgentJob[],
  query: JobsQuery,
  latestStartedAt: string | null,
): AgentJob[] {
  const needle = query.query.toLocaleLowerCase();
  return jobs
    .filter((job) => {
      if (query.since && Date.parse(job.firstSeenAt) <= Date.parse(query.since)) return false;
      if (
        query.latest
        && latestStartedAt
        && Date.parse(job.firstSeenAt) < Date.parse(latestStartedAt) - 5 * 60 * 1000
      ) return false;
      if (query.roles.length && !query.roles.includes(job.role.toLocaleLowerCase())) return false;
      if (query.levels.length && !query.levels.includes(job.level.toLocaleLowerCase())) return false;
      if (query.workModes.length && !query.workModes.includes(job.workMode.toLocaleLowerCase())) return false;
      if (query.source && query.source !== job.sourceType) return false;
      if (
        needle
        && ![job.title, job.company, job.techStack.join(" ")].join(" ").toLocaleLowerCase().includes(needle)
      ) return false;
      if (query.cursor) {
        const timestampDifference = Date.parse(job.firstSeenAt) - Date.parse(query.cursor.firstSeenAt);
        if (timestampDifference > 0) return false;
        if (timestampDifference === 0 && BigInt(job.id) >= BigInt(query.cursor.id)) return false;
      }
      return true;
    })
    .sort((left, right) => {
      const timestampDifference = Date.parse(right.firstSeenAt) - Date.parse(left.firstSeenAt);
      if (timestampDifference !== 0) return timestampDifference;
      return BigInt(right.id) > BigInt(left.id) ? 1 : BigInt(right.id) < BigInt(left.id) ? -1 : 0;
    });
}

export function paginateJobs(jobs: AgentJob[], limit: number): {
  jobs: AgentJob[];
  nextCursor: string | null;
} {
  const page = jobs.slice(0, limit);
  return {
    jobs: page,
    nextCursor: jobs.length > limit && page.length ? encodeCursor(page[page.length - 1]) : null,
  };
}

function berlinParts(value: string | Date, options: Intl.DateTimeFormatOptions): Record<string, string> {
  return Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", { ...options, timeZone: "Europe/Berlin" })
      .formatToParts(new Date(value))
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );
}

export function formatBerlinClock(value: string | Date): string {
  const parts = berlinParts(value, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  return `${parts.hour}:${parts.minute}`;
}

export function formatBerlinTimestamp(value: string | Date): string {
  const parts = berlinParts(value, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute} Europe/Berlin`;
}

export function nextExpectedWindow(now: Date): { from: string; to: string } {
  const from = new Date(now);
  from.setUTCHours(5, 0, 0, 0);
  if (from.getTime() <= now.getTime()) from.setUTCDate(from.getUTCDate() + 1);
  const to = new Date(from.getTime() + 90 * 60 * 1000);
  return { from: from.toISOString(), to: to.toISOString() };
}

export function isStale(updatedAt: string | Date, now: Date): boolean {
  return now.getTime() - new Date(updatedAt).getTime() > 26 * 60 * 60 * 1000;
}

export function formatHomeFreshnessLabel(updatedAt: string | Date, now: Date): string {
  const updated = berlinParts(updatedAt, {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const window = nextExpectedWindow(now);
  const windowStart = new Date(window.from);
  const currentDate = berlinParts(now, { year: "numeric", month: "2-digit", day: "2-digit" });
  const windowDate = berlinParts(windowStart, { year: "numeric", month: "2-digit", day: "2-digit" });
  const currentDay = Date.UTC(Number(currentDate.year), Number(currentDate.month) - 1, Number(currentDate.day));
  const windowDay = Date.UTC(Number(windowDate.year), Number(windowDate.month) - 1, Number(windowDate.day));
  const dayDifference = Math.round((windowDay - currentDay) / (24 * 60 * 60 * 1000));
  const relativeDay = dayDifference === 0
    ? "today"
    : dayDifference === 1
      ? "tomorrow"
      : new Intl.DateTimeFormat("en-GB", {
        timeZone: "Europe/Berlin",
        weekday: "short",
        day: "2-digit",
        month: "short",
      }).format(windowStart);

  return `Updated ${updated.weekday} ${updated.day} ${updated.month}, ${updated.hour}:${updated.minute} Berlin time · next update ${relativeDay} ~${formatBerlinClock(window.from)}–${formatBerlinClock(window.to)}`;
}

export function createAgentStatus(input: {
  updatedAt: string;
  jobCount: number;
  latestUpdateCount: number;
  inserted: number;
  updated: number;
  deleted: number;
  roles: string[];
  levels: string[];
  workModes: string[];
  now: Date;
  baseUrl: string;
}): AgentApiStatus {
  const window = nextExpectedWindow(input.now);
  return {
    updated_at: new Date(input.updatedAt).toISOString(),
    updated_at_berlin: formatBerlinTimestamp(input.updatedAt),
    job_count: input.jobCount,
    latest_update_count: input.latestUpdateCount,
    last_run: {
      inserted: input.inserted,
      updated: input.updated,
      deleted: input.deleted,
    },
    stale: isStale(input.updatedAt, input.now),
    next_expected_window: window,
    filters: {
      roles: [...new Set(input.roles)].sort((left, right) => left.localeCompare(right)),
      levels: [...new Set(input.levels)].sort((left, right) => left.localeCompare(right)),
      work_modes: [...new Set(input.workModes)].sort((left, right) => left.localeCompare(right)),
    },
    docs: {
      llms_txt: `${input.baseUrl}/llms.txt`,
      agents_md: `${input.baseUrl}/agents.md`,
      jobs_md: `${input.baseUrl}/jobs.md`,
      today_md: `${input.baseUrl}/today.md`,
      rss: `${input.baseUrl}/feed.xml`,
    },
  };
}

export function toListJob(job: AgentJob, baseUrl: string) {
  return {
    id: job.id,
    title: job.title,
    company: job.company,
    location: job.location,
    url: job.url,
    detail_url: `${baseUrl}/api/v1/jobs/${job.id}`,
    role: job.role,
    level: job.level,
    work_mode: job.workMode,
    tech_stack: job.techStack,
    posted_date: job.postedDate,
    first_seen_at: job.firstSeenAt,
    source: job.sourceType,
  };
}

function markdownField(value: string | null | undefined): string {
  return (value ?? "").replace(/[\r\n]+/g, " ").replace(/\s+/g, " ").trim() || "—";
}

export function formatJobsMarkdown(input: {
  jobs: AgentJob[];
  updatedAt: string;
  baseUrl: string;
  requestUrl: string;
  query: JobsQuery;
  nextCursor: string | null;
}): string {
  const filters = [
    `roles=${input.query.roles.join(",") || "all"}`,
    `levels=${input.query.levels.join(",") || "all"}`,
    `work_modes=${input.query.workModes.join(",") || "all"}`,
    `source=${input.query.source ?? "all"}`,
    `q=${input.query.query || "all"}`,
    `since=${input.query.since ?? "all"}`,
    `latest=${input.query.latest ? "1" : "0"}`,
  ].join(" · ");
  const lines = [
    "# Daily Berlin Jobs",
    `Updated: ${formatBerlinTimestamp(input.updatedAt)} · ${input.jobs.length} jobs`,
    `Filters: ${markdownField(filters)}`,
    "",
    ...input.jobs.map((job) => {
      const apply = job.url ? `[apply](${markdownField(job.url)})` : "apply link unavailable";
      return `- **${markdownField(job.title)}** — ${markdownField(job.company)} · ${markdownField(job.location)} · ${markdownField(job.role)} · ${markdownField(job.level)} · ${markdownField(job.workMode)} · posted ${markdownField(job.postedDate)} · ${apply} · [details](${input.baseUrl}/jobs/${job.id}.md)`;
    }),
  ];
  if (input.nextCursor) {
    const nextUrl = new URL(input.requestUrl);
    nextUrl.searchParams.set("cursor", input.nextCursor);
    lines.push("", `Next page: ${nextUrl.toString()}`);
  }
  return `${lines.join("\n")}\n`;
}

export function formatJobDetailMarkdown(job: AgentJob): string {
  const description = job.sourceType === "linkedin"
    ? "Description not available for LinkedIn-sourced jobs."
    : job.description?.trim() || "Description not available.";
  return [
    `# ${markdownField(job.title)}`,
    "",
    `- **Company:** ${markdownField(job.company)}`,
    `- **Location:** ${markdownField(job.location)}`,
    `- **Role:** ${markdownField(job.role)}`,
    `- **Level:** ${markdownField(job.level)}`,
    `- **Work mode:** ${markdownField(job.workMode)}`,
    `- **Posted:** ${markdownField(job.postedDate)}`,
    `- **Source:** ${job.sourceType}`,
    `- **Apply:** ${job.url || "unavailable"}`,
    "",
    "## Description",
    "",
    description,
    "",
  ].join("\n");
}

export function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

export function formatRss(jobs: AgentJob[], baseUrl: string, updatedAt: string): string {
  const items = jobs.slice(0, 100).map((job) => [
    "<item>",
    `<title>${escapeXml(`${job.title} — ${job.company}`)}</title>`,
    `<link>${escapeXml(job.url)}</link>`,
    `<guid isPermaLink="false">${escapeXml(`${baseUrl}/api/v1/jobs/${job.id}`)}</guid>`,
    `<pubDate>${escapeXml(new Date(job.firstSeenAt).toUTCString())}</pubDate>`,
    `<description>${escapeXml(`${job.role} · ${job.level} · ${job.workMode}`)}</description>`,
    "</item>",
  ].join(""));
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0"><channel>',
    "<title>Daily Berlin Jobs</title>",
    `<link>${escapeXml(`${baseUrl}/jobs.md`)}</link>`,
    "<description>Engineering jobs in Berlin, refreshed daily.</description>",
    `<lastBuildDate>${escapeXml(new Date(updatedAt).toUTCString())}</lastBuildDate>`,
    ...items,
    "</channel></rss>",
    "",
  ].join("\n");
}

export function responseHeaders(updatedAt: string, contentType?: string): Headers {
  const headers = new Headers({
    "Access-Control-Allow-Origin": "*",
    "Cache-Control": "public, s-maxage=900, stale-while-revalidate=3600",
    "Last-Modified": new Date(updatedAt).toUTCString(),
  });
  if (contentType) headers.set("Content-Type", contentType);
  return headers;
}

export function notModifiedResponse(request: Request, updatedAt: string): Response | null {
  const ifModifiedSince = request.headers.get("if-modified-since");
  const ifModifiedTime = ifModifiedSince ? Date.parse(ifModifiedSince) : Number.NaN;
  const updatedTime = new Date(updatedAt).getTime();
  const lastModifiedTime = Math.floor(updatedTime / 1000) * 1000;
  if (Number.isFinite(ifModifiedTime) && Number.isFinite(updatedTime) && lastModifiedTime <= ifModifiedTime) {
    return new Response(null, { status: 304, headers: responseHeaders(updatedAt) });
  }
  return null;
}

export function jsonResponse(
  request: Request,
  updatedAt: string,
  body: unknown,
  status = 200,
): Response {
  if (status === 200) {
    const notModified = notModifiedResponse(request, updatedAt);
    if (notModified) return notModified;
  }
  return new Response(JSON.stringify(body), {
    status,
    headers: responseHeaders(updatedAt, "application/json; charset=utf-8"),
  });
}

export function textResponse(
  request: Request,
  updatedAt: string,
  body: string,
  contentType: string,
): Response {
  const notModified = notModifiedResponse(request, updatedAt);
  if (notModified) {
    const headers = responseHeaders(updatedAt, contentType);
    return new Response(null, { status: 304, headers });
  }
  return new Response(body, { headers: responseHeaders(updatedAt, contentType) });
}
