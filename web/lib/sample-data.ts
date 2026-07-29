import type { Job, JobsSnapshot } from "./jobs";

function sampleDate(daysAgo: number): string {
  const value = new Date();
  value.setUTCDate(value.getUTCDate() - daysAgo);
  return value.toISOString().slice(0, 10);
}

const SAMPLE_JOBS: Job[] = [
  {
    company: "Open Source Labs",
    title: "Backend Engineer",
    location: "Berlin, Germany",
    link: "https://example.com/jobs/backend-engineer",
    postedDate: sampleDate(0),
    remote: "Hybrid",
    department: "Engineering",
    keywords: ["backend", "typescript", "api"],
    techStack: ["TypeScript", "PostgreSQL"],
    level: "Senior",
    role: "Backend",
    workMode: "Hybrid",
    source: "LinkedIn",
  },
  {
    company: "Community Cloud",
    title: "Platform Engineer",
    location: "Berlin, Germany",
    link: "https://example.com/jobs/platform-engineer",
    postedDate: sampleDate(0),
    remote: "Remote",
    department: "Infrastructure",
    keywords: ["platform", "cloud", "kubernetes"],
    techStack: ["Kubernetes", "AWS"],
    level: "Staff / Principal",
    role: "Platform / DevOps / SRE",
    workMode: "Remote",
    source: "Greenhouse",
  },
  {
    company: "Civic Robotics",
    title: "Embedded Software Engineer",
    location: "Berlin, Germany",
    link: "https://example.com/jobs/embedded-software-engineer",
    postedDate: sampleDate(1),
    remote: "On-site",
    department: "Robotics",
    keywords: ["embedded", "firmware", "robotics"],
    techStack: ["C++", "Linux"],
    level: "Junior / Entry",
    role: "Embedded / Firmware / Robotics",
    workMode: "On-site",
    source: "Ashby",
  },
  {
    company: "Responsible AI Berlin",
    title: "Machine Learning Engineer",
    location: "Berlin, Germany",
    link: "https://example.com/jobs/ml-engineer",
    postedDate: sampleDate(2),
    remote: "Hybrid",
    department: "Data",
    keywords: ["machine learning", "data", "python"],
    techStack: ["Python", "PyTorch"],
    level: "Not specified",
    role: "Data / AI / ML",
    workMode: "Hybrid",
    source: "Lever",
  },
];

export function getSampleJobsSnapshot(): JobsSnapshot {
  return {
    all: SAMPLE_JOBS.map((job) => ({ ...job })),
    daily: SAMPLE_JOBS.slice(0, 3).map((job) => ({ ...job })),
    updatedAt: new Date().toISOString(),
  };
}
