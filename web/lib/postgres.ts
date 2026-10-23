import { Pool } from "pg";
import {
  createAgentStatus,
  filterAndSortJobs,
  paginateJobs,
  type AgentJob,
  type JobsQuery,
} from "./agent-api";
import type { Job, JobsSnapshot } from "./jobs";
import { getSampleAgentJobs, getSampleJobsSnapshot } from "./sample-data";

type JobRow = {
  company_name: string;
  title: string;
  location: string;
  canonical_url: string | null;
  posted_at: string | Date | null;
  remote: string | null;
  department: string | null;
  keywords: string[] | null;
  tech_stack: string[] | null;
  level: string | null;
  role: string;
  work_mode: string | null;
  updated_at: string | Date;
};

type AgentJobRow = {
  id: string | number;
  company_name: string;
  title: string;
  location: string;
  canonical_url: string | null;
  role: string;
  level: string | null;
  work_mode: string | null;
  employment_type: string | null;
  department: string | null;
  tech_stack: string[] | null;
  posted_at: string | Date | null;
  first_seen_at: string | Date;
  last_seen_at: string | Date;
  source_type: string;
  description?: string | null;
};

let pool: Pool | undefined;

export function databasePool(): Pool {
  const connectionString = process.env.DATABASE_URL?.trim();
  if (!connectionString) throw new Error("Missing environment variable: DATABASE_URL");
  if (!pool) {
    const needsSsl = process.env.DATABASE_SSL === "true" || connectionString.includes("supabase.com");
    pool = new Pool({
      connectionString,
      max: 3,
      idleTimeoutMillis: 10_000,
      ssl: needsSsl ? { rejectUnauthorized: false } : undefined,
    });
  }
  return pool;
}

function toJob(row: JobRow): Job {
  return {
    company: row.company_name,
    title: row.title,
    location: row.location,
    link: row.canonical_url ?? "",
    postedDate: row.posted_at ? new Date(row.posted_at).toISOString().slice(0, 10) : "",
    remote: row.remote ?? "",
    department: row.department ?? "",
    keywords: row.keywords ?? [],
    techStack: row.tech_stack ?? [],
    level: row.level ?? "Not specified",
    role: row.role,
    workMode: row.work_mode ?? "Not specified",
  };
}

const JOB_COLUMNS = `
  company_name, title, location, canonical_url, posted_at, remote, department,
  keywords, tech_stack, level, role, work_mode, updated_at
`;

const LIST_AGENT_JOB_COLUMNS = `
  id, company_name, title, location, canonical_url, role, level, work_mode,
  employment_type, department, tech_stack, posted_at,
  to_char(first_seen_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS first_seen_at,
  last_seen_at,
  source_type
`;
const DETAIL_AGENT_JOB_COLUMNS = `${LIST_AGENT_JOB_COLUMNS}, description`;

function toAgentJob(row: AgentJobRow): AgentJob {
  return {
    id: Number(row.id),
    company: row.company_name,
    title: row.title,
    location: row.location,
    url: row.canonical_url ?? "",
    role: row.role,
    level: row.level ?? "Not specified",
    workMode: row.work_mode ?? "Not specified",
    employmentType: row.employment_type,
    department: row.department,
    techStack: row.tech_stack ?? [],
    postedDate: row.posted_at
      ? row.posted_at instanceof Date
        ? row.posted_at.toISOString().slice(0, 10)
        : String(row.posted_at).slice(0, 10)
      : null,
    firstSeenAt: row.first_seen_at instanceof Date
      ? row.first_seen_at.toISOString()
      : String(row.first_seen_at),
    lastSeenAt: new Date(row.last_seen_at).toISOString(),
    sourceType: row.source_type === "linkedin" ? "linkedin" : "ats",
    description: row.description ?? null,
  };
}

function sampleJobsQuery(query: JobsQuery, now: Date) {
  const latestStartedAt = new Date(now.getTime() - 10 * 60 * 1000).toISOString();
  const filtered = filterAndSortJobs(getSampleAgentJobs(now), query, latestStartedAt);
  return {
    updatedAt: now.toISOString(),
    ...paginateJobs(filtered, query.limit),
  };
}

export async function getJobsSnapshot(): Promise<JobsSnapshot> {
  if (process.env.USE_SAMPLE_DATA?.trim().toLowerCase() === "true") {
    return getSampleJobsSnapshot();
  }

  const client = databasePool();
  const [allResult, dailyResult, updatedResult] = await Promise.all([
    client.query<JobRow>(`SELECT ${JOB_COLUMNS} FROM public_jobs ORDER BY posted_at DESC NULLS LAST, first_seen_at DESC`),
    client.query<JobRow>(`SELECT ${JOB_COLUMNS} FROM daily_jobs ORDER BY posted_at DESC, first_seen_at DESC`),
    client.query<{ finished_at: string | Date | null; updated_at: string | Date | null }>(
      "SELECT (SELECT finished_at FROM crawl_status) AS finished_at, updated_at FROM data_status",
    ).catch(() => client.query<{ finished_at: null; updated_at: string | Date | null }>(
      "SELECT NULL AS finished_at, updated_at FROM data_status",
    )),
  ]);
  const updatedAt = updatedResult.rows[0]?.finished_at ?? updatedResult.rows[0]?.updated_at;
  return {
    all: allResult.rows.map(toJob),
    daily: dailyResult.rows.map(toJob),
    updatedAt: updatedAt ? new Date(updatedAt).toISOString() : new Date().toISOString(),
  };
}

export async function getAgentUpdatedAt(): Promise<string> {
  if (process.env.USE_SAMPLE_DATA?.trim().toLowerCase() === "true") {
    return new Date().toISOString();
  }
  const result = await databasePool().query<{
    finished_at: string | Date | null;
    updated_at: string | Date | null;
  }>("SELECT (SELECT finished_at FROM crawl_status) AS finished_at, updated_at FROM data_status");
  const value = result.rows[0]?.finished_at ?? result.rows[0]?.updated_at;
  return value ? new Date(value).toISOString() : new Date().toISOString();
}

export async function getAgentStatus(baseUrl: string, now = new Date()) {
  if (process.env.USE_SAMPLE_DATA?.trim().toLowerCase() === "true") {
    const jobs = getSampleAgentJobs(now);
    const latestStartedAt = now.getTime() - 10 * 60 * 1000;
    return createAgentStatus({
      updatedAt: now.toISOString(),
      jobCount: jobs.length,
      latestUpdateCount: jobs.filter((job) => Date.parse(job.firstSeenAt) >= latestStartedAt - 5 * 60 * 1000).length,
      inserted: 3,
      updated: 0,
      deleted: 0,
      roles: jobs.map((job) => job.role),
      levels: jobs.map((job) => job.level),
      workModes: jobs.map((job) => job.workMode),
      now,
      baseUrl,
    });
  }

  const client = databasePool();
  const [
    runResult,
    statusResult,
    countResult,
    latestCountResult,
    rolesResult,
    levelsResult,
    workModesResult,
  ] = await Promise.all([
    client.query<{
      finished_at: string | Date;
      inserted_count: number;
      updated_count: number;
      deleted_count: number;
    }>("SELECT finished_at, inserted_count, updated_count, deleted_count FROM crawl_status"),
    client.query<{ updated_at: string | Date | null }>("SELECT updated_at FROM data_status"),
    client.query<{ job_count: number }>("SELECT count(*)::integer AS job_count FROM api_jobs"),
    client.query<{ latest_update_count: number }>(
      "SELECT count(*)::integer AS latest_update_count FROM api_jobs "
      + "WHERE first_seen_at >= COALESCE((SELECT started_at FROM crawl_status), now()) - interval '5 minutes'",
    ),
    client.query<{ role: string }>(
      "SELECT DISTINCT role FROM api_jobs WHERE role IS NOT NULL AND btrim(role) <> '' ORDER BY role",
    ),
    client.query<{ level: string }>(
      "SELECT DISTINCT level FROM api_jobs WHERE level IS NOT NULL AND btrim(level) <> '' ORDER BY level",
    ),
    client.query<{ work_mode: string }>(
      "SELECT DISTINCT work_mode FROM api_jobs WHERE work_mode IS NOT NULL AND btrim(work_mode) <> '' ORDER BY work_mode",
    ),
  ]);
  const run = runResult.rows[0];
  const updatedAt = run?.finished_at ?? statusResult.rows[0]?.updated_at ?? now;
  return createAgentStatus({
    updatedAt: new Date(updatedAt).toISOString(),
    jobCount: countResult.rows[0]?.job_count ?? 0,
    latestUpdateCount: latestCountResult.rows[0]?.latest_update_count ?? 0,
    inserted: run?.inserted_count ?? 0,
    updated: run?.updated_count ?? 0,
    deleted: run?.deleted_count ?? 0,
    roles: rolesResult.rows.map((row) => row.role),
    levels: levelsResult.rows.map((row) => row.level),
    workModes: workModesResult.rows.map((row) => row.work_mode),
    now,
    baseUrl,
  });
}

export async function getAgentJobs(query: JobsQuery, now = new Date()) {
  if (process.env.USE_SAMPLE_DATA?.trim().toLowerCase() === "true") {
    return sampleJobsQuery(query, now);
  }

  const clauses: string[] = [];
  const values: unknown[] = [];
  const bind = (value: unknown) => {
    values.push(value);
    return `$${values.length}`;
  };

  if (query.since) clauses.push(`first_seen_at > ${bind(query.since)}::timestamptz`);
  if (query.latest) {
    clauses.push(
      "first_seen_at >= COALESCE((SELECT started_at FROM crawl_status), now()) - interval '5 minutes'",
    );
  }
  if (query.roles.length) clauses.push(`lower(role) = ANY(${bind(query.roles)}::text[])`);
  if (query.levels.length) clauses.push(`lower(level) = ANY(${bind(query.levels)}::text[])`);
  if (query.workModes.length) clauses.push(`lower(work_mode) = ANY(${bind(query.workModes)}::text[])`);
  if (query.source) clauses.push(`source_type = ${bind(query.source)}`);
  if (query.query) {
    const search = bind(`%${query.query}%`);
    clauses.push(`(title ILIKE ${search} OR company_name ILIKE ${search} OR array_to_string(tech_stack, ' ') ILIKE ${search})`);
  }
  if (query.cursor) {
    const timestamp = bind(query.cursor.firstSeenAt);
    const id = bind(query.cursor.id);
    clauses.push(`(first_seen_at, id) < (${timestamp}::timestamptz, ${id}::bigint)`);
  }

  const limit = bind(query.limit + 1);
  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const [jobsResult, updatedAt] = await Promise.all([
    databasePool().query<AgentJobRow>(
      `SELECT ${LIST_AGENT_JOB_COLUMNS} FROM api_jobs ${where} ORDER BY first_seen_at DESC, id DESC LIMIT ${limit}`,
      values,
    ),
    getAgentUpdatedAt(),
  ]);
  const jobs = jobsResult.rows.map(toAgentJob);
  return {
    updatedAt,
    ...paginateJobs(jobs, query.limit),
  };
}

export async function getAgentJob(id: string): Promise<AgentJob | null> {
  if (process.env.USE_SAMPLE_DATA?.trim().toLowerCase() === "true") {
    return getSampleAgentJobs().find((job) => String(job.id) === id) ?? null;
  }
  const result = await databasePool().query<AgentJobRow>(
    `SELECT ${DETAIL_AGENT_JOB_COLUMNS} FROM api_jobs WHERE id = $1::bigint`,
    [id],
  );
  return result.rows[0] ? toAgentJob(result.rows[0]) : null;
}
