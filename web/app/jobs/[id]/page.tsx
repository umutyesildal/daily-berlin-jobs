import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PrivacyFooter } from "@/components/privacy-footer";
import { SeoJobList, SourceBadge } from "@/components/seo-job-list";
import { formatHomeFreshnessLabel, parseJobsQuery } from "@/lib/agent-api";
import { getAgentJob, getAgentJobs, getAgentUpdatedAt } from "@/lib/postgres";
import {
  buildJobPostingJsonLd,
  categoryForRole,
  htmlToText,
  SITE_URL,
  slugify,
} from "@/lib/seo";

export const revalidate = 3600;

type PageProps = {
  params: Promise<{ id: string }>;
};

function fallbackDescription(job: NonNullable<Awaited<ReturnType<typeof getAgentJob>>>): string {
  return `${job.role} · ${job.level} · ${job.workMode} role at ${job.company} in Berlin.`;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const job = await getAgentJob(id);
  if (!job) return { title: { absolute: "Job not found | Daily Berlin Jobs" } };

  const plainDescription = htmlToText(job.description);
  const description = (job.sourceType === "ats" && plainDescription
    ? plainDescription
    : fallbackDescription(job)).slice(0, 155);
  const title = `${job.title} at ${job.company} – Berlin | Daily Berlin Jobs`;
  const canonical = `${SITE_URL}/jobs/${job.id}`;
  return {
    title: { absolute: title },
    description,
    alternates: { canonical },
    openGraph: {
      type: "article",
      title,
      description,
      url: canonical,
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}

export default async function JobPage({ params }: PageProps) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const job = await getAgentJob(id);
  if (!job) notFound();

  const updatedAt = await getAgentUpdatedAt();
  const freshnessLabel = formatHomeFreshnessLabel(updatedAt, new Date());
  const roleQuery = new URLSearchParams();
  roleQuery.set("role", job.role);
  roleQuery.set("limit", "20");
  const similar = (await getAgentJobs(parseJobsQuery(roleQuery))).jobs
    .filter((candidate) => candidate.id !== job.id)
    .slice(0, 6);
  const category = categoryForRole(job.role);
  const plainDescription = job.sourceType === "ats" ? htmlToText(job.description) : "";
  const descriptionParagraphs = plainDescription.split(/\n{2,}/).filter(Boolean);
  const jsonLd = buildJobPostingJsonLd(job);
  const postedDate = job.postedDate || job.firstSeenAt.slice(0, 10);

  return (
    <main className="page-shell seo-page">
      {jsonLd && (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: jsonLd }}
        />
      )}
      <header className="seo-page-header">
        <nav className="breadcrumbs" aria-label="Breadcrumb">
          <a href="/">Home</a>
          <span aria-hidden="true">/</span>
          {category && <a href={`/berlin/${category.slug}`}>{category.h1}</a>}
        </nav>
        <p className="eyebrow">Berlin engineering role</p>
        <h1>{job.title}</h1>
        <p className="seo-company-name">
          <a href={`/companies/${slugify(job.company)}`}>{job.company}</a>
        </p>
        <p className="seo-location">{job.location || "Berlin"}</p>
        <div className="seo-job-meta">
          <span className="meta-tag">{job.role}</span>
          <span className="meta-tag">{job.level}</span>
          <span className="meta-tag">{job.workMode}</span>
          {postedDate && <time dateTime={postedDate}>Posted {postedDate}</time>}
          <SourceBadge source={job.sourceType} detailed />
        </div>
        <p className="seo-freshness">{freshnessLabel}</p>
        {job.url && (
          <a
            className="apply-button"
            href={job.url}
            target="_blank"
            rel="nofollow noopener noreferrer"
          >
            Apply on company site
          </a>
        )}
      </header>

      <section className="seo-section" aria-labelledby="job-description-title">
        <h2 id="job-description-title">Job description</h2>
        {descriptionParagraphs.length ? (
          <div className="job-description">
            {descriptionParagraphs.map((paragraph, index) => <p key={index}>{paragraph}</p>)}
          </div>
        ) : (
          <p className="seo-note">Full descriptions are available for jobs sourced directly from company career sites.</p>
        )}
      </section>

      {similar.length > 0 && (
        <section className="seo-section" aria-labelledby="similar-jobs-title">
          <h2 id="similar-jobs-title">Similar {job.role.toLowerCase()} jobs</h2>
          <SeoJobList jobs={similar} />
        </section>
      )}

      <nav className="seo-related-links" aria-label="Related pages">
        {category && <a href={`/berlin/${category.slug}`}>More {category.h1.toLowerCase()}</a>}
        <a href="/">All Berlin engineering jobs</a>
      </nav>
      <PrivacyFooter />
    </main>
  );
}
