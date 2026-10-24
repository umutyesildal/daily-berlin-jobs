import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PrivacyFooter } from "@/components/privacy-footer";
import { SeoJobList } from "@/components/seo-job-list";
import { formatHomeFreshnessLabel, parseJobsQuery } from "@/lib/agent-api";
import { getAgentUpdatedAt, getAllAgentJobs } from "@/lib/postgres";
import {
  buildCategoryIntro,
  CATEGORIES,
  SITE_URL,
} from "@/lib/seo";

export const revalidate = 3600;

type PageProps = {
  params: Promise<{ slug: string }>;
};

function findCategory(slug: string) {
  return CATEGORIES.find((category) => category.slug === slug);
}

function categoryQuery(slug: string) {
  const category = findCategory(slug);
  if (!category) return null;
  const params = new URLSearchParams();
  if (category.filter.roles) params.set("role", category.filter.roles.join(","));
  if (category.filter.levels) params.set("level", category.filter.levels.join(","));
  if (category.filter.workModes) params.set("work_mode", category.filter.workModes.join(","));
  params.set("limit", "500");
  return parseJobsQuery(params);
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const category = findCategory(slug);
  if (!category) notFound();
  const canonical = `${SITE_URL}/berlin/${category.slug}`;
  return {
    title: category.title,
    description: category.description,
    alternates: { canonical },
    openGraph: {
      type: "website",
      title: category.title,
      description: category.description,
      url: canonical,
    },
    twitter: {
      card: "summary_large_image",
      title: category.title,
      description: category.description,
    },
  };
}

export default async function CategoryPage({ params }: PageProps) {
  const { slug } = await params;
  const category = findCategory(slug);
  if (!category) notFound();

  const query = categoryQuery(slug);
  if (!query) notFound();
  const jobs = await getAllAgentJobs(query);
  const updatedAt = await getAgentUpdatedAt();
  const freshnessLabel = formatHomeFreshnessLabel(updatedAt, new Date());
  const related = CATEGORIES.filter((candidate) => candidate.slug !== category.slug);

  return (
    <main className="page-shell seo-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <a href="/">Home</a>
        <span aria-hidden="true">/</span>
        <span>{category.h1}</span>
      </nav>
      <header className="seo-page-header">
        <span className="eyebrow">Berlin engineering jobs</span>
        <h1>{category.h1}</h1>
        <p>{category.description}</p>
        <p className="seo-freshness">{freshnessLabel}</p>
        <p className="seo-count">{jobs.length} current jobs</p>
        <p className="seo-intro">{buildCategoryIntro(jobs)}</p>
      </header>

      <section className="seo-section" aria-label={`${category.h1} listings`}>
        <SeoJobList jobs={jobs.slice(0, 200)} />
        {jobs.length > 200 && (
          <p className="seo-note">Showing the first 200 of {jobs.length} current jobs.</p>
        )}
      </section>

      <nav className="seo-related-links" aria-label="Related searches">
        <h2>Related searches</h2>
        {related.map((item) => (
          <a href={`/berlin/${item.slug}`} key={item.slug}>{item.h1}</a>
        ))}
      </nav>
      <PrivacyFooter />
    </main>
  );
}
