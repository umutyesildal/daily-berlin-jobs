import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SeoJobList } from "@/components/seo-job-list";
import { getAgentCompanyNames, getAgentJobsByCompany } from "@/lib/postgres";
import { CATEGORIES, SITE_URL, slugify } from "@/lib/seo";

export const revalidate = 3600;

type PageProps = {
  params: Promise<{ slug: string }>;
};

async function findCompany(slug: string): Promise<string | undefined> {
  return (await getAgentCompanyNames()).find((company) => slugify(company) === slug);
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const company = await findCompany(slug);
  if (!company) notFound();
  const title = `${company} engineering jobs in Berlin`;
  const description = `Browse current engineering jobs at ${company} in Berlin.`;
  const canonical = `${SITE_URL}/companies/${slugify(company)}`;
  return {
    title,
    description,
    alternates: { canonical },
    openGraph: {
      type: "website",
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

export default async function CompanyPage({ params }: PageProps) {
  const { slug } = await params;
  const company = await findCompany(slug);
  if (!company) notFound();
  const jobs = await getAgentJobsByCompany(company);
  const roles = new Set(jobs.map((job) => job.role));
  const roleCategories = CATEGORIES.filter(
    (category) => category.filter.roles?.some((role) => roles.has(role)),
  );

  return (
    <main className="page-shell seo-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <a href="/">Home</a>
        <span aria-hidden="true">/</span>
        <span>{company}</span>
      </nav>
      <header className="seo-page-header">
        <span className="eyebrow">Company career listings</span>
        <h1>{company} engineering jobs in Berlin</h1>
        <p>{jobs.length} current engineering {jobs.length === 1 ? "job" : "jobs"} at {company}.</p>
      </header>

      <section className="seo-section" aria-label={`${company} job listings`}>
        <SeoJobList jobs={jobs.slice(0, 200)} />
        {jobs.length > 200 && <p className="seo-note">Showing the first 200 of {jobs.length} current jobs.</p>}
      </section>

      {roleCategories.length > 0 && (
        <nav className="seo-related-links" aria-label="Role categories at this company">
          <h2>Browse these roles</h2>
          {roleCategories.map((category) => (
            <a href={`/berlin/${category.slug}`} key={category.slug}>{category.h1}</a>
          ))}
        </nav>
      )}
    </main>
  );
}
