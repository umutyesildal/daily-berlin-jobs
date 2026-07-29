import { Pool } from "pg";
import type { Job, JobsSnapshot } from "./jobs";
import { getSampleJobsSnapshot } from "./sample-data";

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
  source: string | null;
  ats_label: string | null;
  updated_at: string | Date;
};

let pool: Pool | undefined;

function databasePool(): Pool {
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
    source: row.source ?? row.ats_label ?? "",
  };
}

const JOB_COLUMNS = `
  company_name, title, location, canonical_url, posted_at, remote, department,
  keywords, tech_stack, level, role, work_mode, updated_at, source, ats_label
`;

export async function getJobsSnapshot(): Promise<JobsSnapshot> {
  if (process.env.USE_SAMPLE_DATA?.trim().toLowerCase() === "true") {
    return getSampleJobsSnapshot();
  }

  const client = databasePool();
  const [allResult, dailyResult, updatedResult] = await Promise.all([
    client.query<JobRow>(`SELECT ${JOB_COLUMNS} FROM public_jobs ORDER BY posted_at DESC NULLS LAST, first_seen_at DESC`),
    client.query<JobRow>(`SELECT ${JOB_COLUMNS} FROM daily_jobs ORDER BY posted_at DESC, first_seen_at DESC`),
    client.query<{ updated_at: string | Date | null }>("SELECT updated_at FROM data_status"),
  ]);
  const updatedAt = updatedResult.rows[0]?.updated_at;
  return {
    all: allResult.rows.map(toJob),
    daily: dailyResult.rows.map(toJob),
    updatedAt: updatedAt ? new Date(updatedAt).toISOString() : new Date().toISOString(),
  };
}
