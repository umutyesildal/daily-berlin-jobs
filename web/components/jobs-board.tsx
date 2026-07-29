"use client";

import { useEffect, useMemo, useState } from "react";
import { isLinkedInJob, type Job, type JobsSnapshot } from "@/lib/jobs";

const PAGE_SIZE = 40;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_NUMBER = new Map(MONTHS.map((month, index) => [month.toLowerCase(), index + 1]));

function dateParts(value: string): { year: number; month: number; day: number } | null {
  const normalized = value.trim();
  const iso = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(normalized);
  if (iso) return { year: Number(iso[1]), month: Number(iso[2]), day: Number(iso[3]) };

  const named = /^([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})/.exec(normalized);
  const month = named ? MONTH_NUMBER.get(named[1].slice(0, 3).toLowerCase()) : undefined;
  if (named && month) return { year: Number(named[3]), month, day: Number(named[2]) };
  return null;
}

function jobDate(value: string): string {
  const parsed = dateParts(value);
  if (!parsed) return value || "Unknown";
  return `${MONTHS[parsed.month - 1]} ${parsed.day}, ${parsed.year}`;
}

function dateValue(value: string): number {
  const parsed = dateParts(value);
  return parsed ? parsed.year * 10_000 + parsed.month * 100 + parsed.day : 0;
}

function compareText(left: string, right: string): number {
  const normalizedLeft = left.toLowerCase();
  const normalizedRight = right.toLowerCase();
  if (normalizedLeft < normalizedRight) return -1;
  if (normalizedLeft > normalizedRight) return 1;
  return 0;
}

function options(jobs: Job[], field: "role" | "level" | "workMode"): string[] {
  return [...new Set(jobs.map((job) => job[field]).filter(Boolean))].sort(compareText);
}

export function JobsBoard({ snapshot }: { snapshot: JobsSnapshot }) {
  const [source, setSource] = useState<"all" | "daily">("all");
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const [level, setLevel] = useState("");
  const [workMode, setWorkMode] = useState("");
  const [sortDirection, setSortDirection] = useState<"desc" | "asc">("desc");
  const [page, setPage] = useState(1);
  const jobs = source === "all" ? snapshot.all : snapshot.daily;

  const filterOptions = useMemo(() => ({
    roles: options(jobs, "role"),
    levels: options(jobs, "level"),
    workModes: options(jobs, "workMode"),
  }), [jobs]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return jobs
      .filter((job) => {
        const searchable = [job.title, job.company, job.location, job.department, job.role, job.level, ...job.keywords, ...job.techStack]
          .join(" ").toLocaleLowerCase();
        return (!needle || searchable.includes(needle))
          && (!role || job.role === role)
          && (!level || job.level === level)
          && (!workMode || job.workMode === workMode);
      })
      .sort((a, b) => {
        const dateDifference = dateValue(a.postedDate) - dateValue(b.postedDate);
        if (dateDifference) return sortDirection === "asc" ? dateDifference : -dateDifference;
        return compareText(a.company, b.company) || compareText(a.title, b.title);
      });
  }, [jobs, query, role, level, workMode, sortDirection]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const visibleJobs = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const hasFilters = Boolean(query || role || level || workMode);

  useEffect(() => setPage(1), [source, query, role, level, workMode, sortDirection]);

  function clearFilters() {
    setQuery("");
    setRole("");
    setLevel("");
    setWorkMode("");
  }

  return (
    <main className="page-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Daily Berlin Jobs home">
          <span className="brand-mark">B</span>
          <span>Daily Berlin Jobs</span>
        </a>
        <span className="header-note">Fresh Berlin engineering roles, daily.</span>
      </header>

      <section className="hero">
        <span className="eyebrow">Updated daily from verified company sources</span>
        <h1>Engineering jobs in Berlin,<br />without the noise.</h1>
        <p>Software, data, platform, security and embedded engineering roles in one place.</p>
      </section>

      <section className="controls">
        <div className="tabs">
          <button className={source === "all" ? "active" : ""} onClick={() => setSource("all")}>All Jobs <b>{snapshot.all.length}</b></button>
          <button className={source === "daily" ? "active" : ""} onClick={() => setSource("daily")}>New Today <b>{snapshot.daily.length}</b></button>
        </div>
        <input aria-label="Search jobs" placeholder="Search role, company, or technology" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
      </section>

      <section className="filter-bar" aria-label="Job filters">
        <label className="filter-field"><span>Engineering area</span><select value={role} onChange={(event) => setRole(event.target.value)}>
          <option value="">All areas</option>{filterOptions.roles.map((item) => <option key={item}>{item}</option>)}
        </select></label>
        <label className="filter-field"><span>Level</span><select value={level} onChange={(event) => setLevel(event.target.value)}>
          <option value="">Any level</option>{filterOptions.levels.map((item) => <option key={item}>{item}</option>)}
        </select></label>
        <label className="filter-field"><span>Work style</span><select value={workMode} onChange={(event) => setWorkMode(event.target.value)}>
          <option value="">Any work style</option>{filterOptions.workModes.map((item) => <option key={item}>{item}</option>)}
        </select></label>
        <button className="clear-filters" disabled={!hasFilters} onClick={clearFilters}>Clear</button>
        <span className="result-count">{filtered.length} jobs</span>
      </section>

      <div className="jobs-table">
        <div className="table-head">
          <span>Role</span><span>Company</span><span>Location</span>
          <button className="sort-button" onClick={() => setSortDirection((current) => current === "desc" ? "asc" : "desc")}>
            Date <span aria-hidden="true">{sortDirection === "desc" ? "↓" : "↑"}</span>
          </button>
        </div>
        {visibleJobs.map((job: Job, index) => (
          <a className="job-row" href={job.link || undefined} target="_blank" rel="noreferrer" key={`${job.link}-${index}`}>
            <div className="role-cell">
              <div className="job-title-line">
                <strong>{job.title || "Untitled role"}</strong>
                {isLinkedInJob(job) && (
                  <span className="linkedin-source" role="img" aria-label="LinkedIn source" title="Source: LinkedIn">
                    <svg aria-hidden="true" viewBox="0 0 24 24">
                      <path d="M5.2 7.1A2.1 2.1 0 1 0 5.2 3a2.1 2.1 0 0 0 0 4.1ZM3.4 21h3.7V8.7H3.4V21Zm5.9-12.3H13v1.7h.1c.5-1 1.8-2.1 3.7-2.1 4 0 4.7 2.6 4.7 6V21h-3.8v-5.9c0-1.4 0-3.2-2-3.2s-2.3 1.5-2.3 3.1v6H9.3V8.7Z" />
                    </svg>
                  </span>
                )}
              </div>
              <div className="job-tags">
                <span className="role-tag">{job.role}</span>
                {job.level !== "Not specified" && <span className="meta-tag">{job.level}</span>}
                {job.workMode !== "Not specified" && <span className="meta-tag">{job.workMode}</span>}
              </div>
            </div>
            <span>{job.company || "Unknown company"}</span>
            <span>{job.location || "Berlin"}</span>
            <time>{jobDate(job.postedDate)}</time>
          </a>
        ))}
        {!filtered.length && <p className="empty">No jobs match these filters.</p>}
      </div>

      {filtered.length > 0 && (
        <nav className="pagination" aria-label="Job list pages">
          <button disabled={currentPage === 1} onClick={() => setPage((current) => current - 1)}>Previous</button>
          <span>Page {currentPage} of {pageCount}</span>
          <button disabled={currentPage === pageCount} onClick={() => setPage((current) => current + 1)}>Next</button>
        </nav>
      )}

      <footer className="site-footer">
        <span>Daily Berlin Jobs · Engineering roles updated daily.</span>
        <nav aria-label="Creator links">
          <a href="https://github.com/umutyesildal/daily-berlin-jobs/issues/new?template=company_suggestion.yml" target="_blank" rel="noreferrer">Suggest a company</a>
          <a className="admin-footer-link" href="/admin" aria-label="Admin">Admin</a>
        </nav>
      </footer>
    </main>
  );
}
