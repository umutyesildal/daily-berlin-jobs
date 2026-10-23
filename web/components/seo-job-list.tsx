import type { AgentJob } from "@/lib/agent-api";
import { slugify } from "@/lib/seo";

export function SourceBadge({
  source,
  detailed = false,
}: {
  source: "ats" | "linkedin";
  detailed?: boolean;
}) {
  return (
    <span className={`source-badge source-badge-${source}`}>
      {source === "linkedin"
        ? (detailed ? "via LinkedIn" : "LinkedIn")
        : (detailed ? "Direct from company" : "Direct")}
    </span>
  );
}

export function SeoJobList({
  jobs,
  emptyMessage = "No current jobs match this page.",
}: {
  jobs: AgentJob[];
  emptyMessage?: string;
}) {
  if (!jobs.length) {
    return (
      <div className="seo-empty">
        <p>{emptyMessage}</p>
        <a href="/">Browse all current Berlin engineering jobs</a>
      </div>
    );
  }

  return (
    <div className="seo-job-list">
      {jobs.map((job) => {
        const postedDate = job.postedDate || job.firstSeenAt.slice(0, 10);
        return (
          <article className="seo-job-card" key={job.id}>
            <div className="seo-job-heading">
              <h2><a href={`/jobs/${job.id}`}>{job.title}</a></h2>
              <SourceBadge source={job.sourceType} />
            </div>
            <p className="seo-job-company">
              <a href={`/companies/${slugify(job.company)}`}>{job.company}</a>
            </p>
            <div className="seo-job-meta">
              <span>{job.location || "Berlin"}</span>
              <span>{job.level}</span>
              <span>{job.workMode}</span>
              <time dateTime={postedDate}>Posted {postedDate}</time>
            </div>
          </article>
        );
      })}
    </div>
  );
}
