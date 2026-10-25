import type { MetadataRoute } from "next";
import { getAllAgentJobs } from "@/lib/postgres";
import { CATEGORIES, SITE_URL, slugify } from "@/lib/seo";

export const revalidate = 3600;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const jobs = await getAllAgentJobs();
  const latestSeen = jobs.reduce<Date | null>((latest, job) => {
    const lastSeen = new Date(job.lastSeenAt);
    return !latest || lastSeen > latest ? lastSeen : latest;
  }, null);
  const companyLastSeen = new Map<string, Date>();
  for (const job of jobs) {
    const lastSeen = new Date(job.lastSeenAt);
    const current = companyLastSeen.get(job.company);
    if (!current || lastSeen > current) companyLastSeen.set(job.company, lastSeen);
  }

  return [
    {
      url: `${SITE_URL}/`,
      lastModified: latestSeen ?? new Date(),
      changeFrequency: "daily",
      priority: 1,
    },
    {
      url: `${SITE_URL}/privacy`,
      lastModified: new Date("2026-10-25"),
      changeFrequency: "yearly",
      priority: 0.2,
    },
    {
      url: `${SITE_URL}/german-check`,
      lastModified: new Date("2026-10-25"),
      changeFrequency: "yearly",
      priority: 0.5,
    },
    ...CATEGORIES.map((category) => ({
      url: `${SITE_URL}/berlin/${category.slug}`,
      lastModified: latestSeen ?? new Date(),
      changeFrequency: "daily" as const,
      priority: 0.8,
    })),
    ...[...companyLastSeen.entries()].map(([company, lastModified]) => ({
      url: `${SITE_URL}/companies/${slugify(company)}`,
      lastModified,
      changeFrequency: "daily" as const,
      priority: 0.6,
    })),
    ...jobs.map((job) => ({
      url: `${SITE_URL}/jobs/${job.id}`,
      lastModified: new Date(job.lastSeenAt),
      changeFrequency: "daily" as const,
      priority: 0.7,
    })),
  ];
}
