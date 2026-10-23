import type { AgentJob } from "./agent-api";

export const SITE_URL = (process.env.SITE_URL?.trim() || "https://daily-berlin-jobs.vercel.app").replace(/\/+$/, "");

export type CategoryFilter = {
  roles?: readonly string[];
  levels?: readonly string[];
  workModes?: readonly string[];
};

export type JobCategory = {
  slug: string;
  h1: string;
  title: string;
  description: string;
  filter: CategoryFilter;
};

export const CATEGORIES: JobCategory[] = [
  {
    slug: "backend-engineer-jobs",
    h1: "Backend engineer jobs in Berlin",
    title: "Backend engineer jobs in Berlin",
    description: "Browse current backend engineering jobs in Berlin from company career sites and LinkedIn.",
    filter: { roles: ["Backend"] },
  },
  {
    slug: "frontend-engineer-jobs",
    h1: "Frontend engineer jobs in Berlin",
    title: "Frontend engineer jobs in Berlin",
    description: "Browse current frontend engineering jobs in Berlin from company career sites and LinkedIn.",
    filter: { roles: ["Frontend"] },
  },
  {
    slug: "fullstack-engineer-jobs",
    h1: "Fullstack engineer jobs in Berlin",
    title: "Fullstack engineer jobs in Berlin",
    description: "Browse current fullstack engineering jobs in Berlin from company career sites and LinkedIn.",
    filter: { roles: ["Fullstack"] },
  },
  {
    slug: "data-ai-ml-jobs",
    h1: "Data, AI and ML jobs in Berlin",
    title: "Data, AI and ML jobs in Berlin",
    description: "Browse current data, AI and machine learning jobs in Berlin from company career sites and LinkedIn.",
    filter: { roles: ["Data / AI / ML"] },
  },
  {
    slug: "devops-platform-sre-jobs",
    h1: "DevOps, platform and SRE jobs in Berlin",
    title: "DevOps, platform and SRE jobs in Berlin",
    description: "Browse current DevOps, platform and SRE jobs in Berlin from company career sites and LinkedIn.",
    filter: { roles: ["Platform / DevOps / SRE"] },
  },
  {
    slug: "security-engineer-jobs",
    h1: "Security engineer jobs in Berlin",
    title: "Security engineer jobs in Berlin",
    description: "Browse current security engineering jobs in Berlin from company career sites and LinkedIn.",
    filter: { roles: ["Security"] },
  },
  {
    slug: "mobile-developer-jobs",
    h1: "Mobile developer jobs in Berlin",
    title: "Mobile developer jobs in Berlin",
    description: "Browse current mobile development jobs in Berlin from company career sites and LinkedIn.",
    filter: { roles: ["Mobile"] },
  },
  {
    slug: "embedded-engineer-jobs",
    h1: "Embedded engineer jobs in Berlin",
    title: "Embedded engineer jobs in Berlin",
    description: "Browse current embedded, firmware and robotics engineering jobs in Berlin.",
    filter: { roles: ["Embedded / Firmware / Robotics"] },
  },
  {
    slug: "qa-test-engineer-jobs",
    h1: "QA and test engineer jobs in Berlin",
    title: "QA and test engineer jobs in Berlin",
    description: "Browse current quality assurance and test engineering jobs in Berlin.",
    filter: { roles: ["QA / Test"] },
  },
  {
    slug: "engineering-manager-jobs",
    h1: "Engineering manager jobs in Berlin",
    title: "Engineering manager jobs in Berlin",
    description: "Browse current engineering leadership jobs in Berlin from company career sites and LinkedIn.",
    filter: { roles: ["Engineering Leadership"] },
  },
  {
    slug: "software-engineer-jobs",
    h1: "Software engineer jobs in Berlin",
    title: "Software engineer jobs in Berlin",
    description: "Browse current software engineering jobs in Berlin from company career sites and LinkedIn.",
    filter: { roles: ["Software Engineering"] },
  },
  {
    slug: "remote-engineering-jobs",
    h1: "Remote engineering jobs in Berlin",
    title: "Remote engineering jobs in Berlin",
    description: "Browse current engineering jobs listed with remote work mode in Berlin.",
    filter: { workModes: ["Remote"] },
  },
  {
    slug: "hybrid-engineering-jobs",
    h1: "Hybrid engineering jobs in Berlin",
    title: "Hybrid engineering jobs in Berlin",
    description: "Browse current engineering jobs listed with hybrid work mode in Berlin.",
    filter: { workModes: ["Hybrid"] },
  },
  {
    slug: "junior-developer-jobs",
    h1: "Junior developer jobs in Berlin",
    title: "Junior developer jobs in Berlin",
    description: "Browse current engineering jobs in Berlin listed at junior or entry level.",
    filter: { levels: ["Junior / Entry"] },
  },
  {
    slug: "working-student-internship-jobs",
    h1: "Working student and internship jobs in Berlin",
    title: "Working student and internship jobs in Berlin",
    description: "Browse current engineering internships and working student jobs in Berlin.",
    filter: { levels: ["Intern / Working Student"] },
  },
  {
    slug: "senior-engineer-jobs",
    h1: "Senior engineer jobs in Berlin",
    title: "Senior engineer jobs in Berlin",
    description: "Browse current senior engineering jobs in Berlin from company career sites and LinkedIn.",
    filter: { levels: ["Senior"] },
  },
  {
    slug: "staff-principal-engineer-jobs",
    h1: "Staff and principal engineer jobs in Berlin",
    title: "Staff and principal engineer jobs in Berlin",
    description: "Browse current staff and principal engineering jobs in Berlin.",
    filter: { levels: ["Staff / Principal"] },
  },
];

export function slugify(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function htmlToText(value: string | null | undefined): string {
  if (!value) return "";
  const text = value
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(?:p|div|li|h[1-6]|section|article|tr|blockquote)\s*>/gi, "\n\n")
    .replace(/<[^>]*>/g, "")
    .replace(/&(#x[\da-f]+|#\d+|[a-z][\da-z]+);/gi, (entity, code: string) => {
      if (code[0] === "#") {
        const numeric = code[1].toLowerCase() === "x"
          ? Number.parseInt(code.slice(2), 16)
          : Number.parseInt(code.slice(1), 10);
        return Number.isFinite(numeric) ? String.fromCodePoint(numeric) : entity;
      }
      const named: Record<string, string> = {
        amp: "&",
        apos: "'",
        gt: ">",
        lt: "<",
        nbsp: " ",
        quot: "\"",
      };
      return named[code.toLowerCase()] ?? entity;
    });
  return text
    .replace(/\r/g, "")
    .split(/\n+/)
    .map((line) => line.replace(/[ \t]+/g, " ").trim())
    .filter(Boolean)
    .join("\n\n");
}

function employmentTypeForSchema(value: string | null): string | undefined {
  const normalized = (value ?? "").trim().toLowerCase();
  if (/^full[- ]?time$/.test(normalized)) return "FULL_TIME";
  if (/^part[- ]?time$/.test(normalized)) return "PART_TIME";
  if (/^intern/.test(normalized)) return "INTERN";
  if (/contract|freelance/.test(normalized)) return "CONTRACTOR";
  return undefined;
}

export function buildJobPostingJsonLd(
  job: Pick<
    AgentJob,
    "sourceType" | "description" | "title" | "postedDate" | "firstSeenAt" | "company" | "employmentType" | "workMode"
  >,
): string | null {
  const description = htmlToText(job.description);
  if (job.sourceType !== "ats" || !description) return null;

  const datePosted = job.postedDate || job.firstSeenAt.slice(0, 10);
  const validThroughDate = new Date(`${datePosted}T00:00:00.000Z`);
  validThroughDate.setUTCDate(validThroughDate.getUTCDate() + 30);
  const posting: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    title: job.title,
    description,
    datePosted,
    validThrough: validThroughDate.toISOString().slice(0, 10),
    hiringOrganization: {
      "@type": "Organization",
      name: job.company,
    },
    jobLocation: {
      "@type": "Place",
      address: {
        "@type": "PostalAddress",
        addressLocality: "Berlin",
        addressCountry: "DE",
      },
    },
    directApply: false,
  };
  const employmentType = employmentTypeForSchema(job.employmentType);
  if (employmentType) posting.employmentType = employmentType;
  if (job.workMode.trim().toLowerCase() === "remote") {
    posting.jobLocationType = "TELECOMMUTE";
    posting.applicantLocationRequirements = {
      "@type": "Country",
      name: "Germany",
    };
  }
  return JSON.stringify(posting).replace(/</g, "\\u003c");
}

export function buildCategoryIntro(jobs: readonly Pick<AgentJob, "company" | "workMode">[]): string {
  const counts = new Map<string, number>();
  for (const job of jobs) counts.set(job.company, (counts.get(job.company) ?? 0) + 1);
  const topCompanies = [...counts.entries()]
    .sort(([nameA, countA], [nameB, countB]) => countB - countA || nameA.localeCompare(nameB))
    .slice(0, 3)
    .map(([name]) => name);
  const remoteCount = jobs.filter((job) => job.workMode.toLowerCase() === "remote").length;
  const remotePercent = jobs.length ? Math.round((remoteCount / jobs.length) * 100) : 0;
  const companySummary = topCompanies.length ? topCompanies.join(", ") : "none";
  return `${jobs.length} current jobs; top companies: ${companySummary}; ${remotePercent}% are remote.`;
}

export function categoryForRole(role: string): JobCategory | undefined {
  return CATEGORIES.find((category) => category.filter.roles?.includes(role));
}

export function matchesCategory(job: AgentJob, category: JobCategory): boolean {
  return (!category.filter.roles || category.filter.roles.includes(job.role))
    && (!category.filter.levels || category.filter.levels.includes(job.level))
    && (!category.filter.workModes || category.filter.workModes.includes(job.workMode));
}
