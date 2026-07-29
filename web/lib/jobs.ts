export type Job = {
  company: string;
  title: string;
  location: string;
  link: string;
  postedDate: string;
  remote: string;
  department: string;
  keywords: string[];
  techStack: string[];
  level: string;
  role: string;
  workMode: string;
  source: string;
};

export type JobsSnapshot = {
  all: Job[];
  daily: Job[];
  updatedAt: string;
};

export function isLinkedInJob(job: Pick<Job, "source" | "link">): boolean {
  if (job.source.trim().toLocaleLowerCase().includes("linkedin")) return true;

  try {
    const hostname = new URL(job.link).hostname.toLocaleLowerCase();
    return hostname === "linkedin.com" || hostname.endsWith(".linkedin.com");
  } catch {
    return false;
  }
}
