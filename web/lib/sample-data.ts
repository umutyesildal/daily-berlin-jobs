import type { Job, JobsSnapshot } from "./jobs";
import type { AgentJob } from "./agent-api";

function sampleDate(daysAgo: number): string {
  const value = new Date();
  value.setUTCDate(value.getUTCDate() - daysAgo);
  return value.toISOString().slice(0, 10);
}

const SAMPLE_JOBS: Job[] = [
  {
    source: "ats",
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
  },
  {
    source: "ats",
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
  },
  {
    source: "ats",
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
  },
  {
    source: "linkedin",
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
  },
  {
    source: "ats",
    company: "Future Labs",
    title: "Fullstack Engineer",
    location: "Berlin, Germany",
    link: "https://example.com/jobs/fullstack-engineer",
    postedDate: sampleDate(0),
    remote: "Hybrid",
    department: "Product Engineering",
    keywords: ["fullstack", "typescript", "react"],
    techStack: ["TypeScript", "React", "PostgreSQL"],
    level: "Mid-level",
    role: "Fullstack",
    workMode: "Hybrid",
  },
  {
    source: "ats",
    company: "Civic Systems",
    title: "Backend Developer",
    location: "Berlin, Germany",
    link: "https://example.com/jobs/backend-developer",
    postedDate: sampleDate(0),
    remote: "Remote",
    department: "Engineering",
    keywords: ["backend", "python", "postgresql"],
    techStack: ["Python", "PostgreSQL"],
    level: "Senior",
    role: "Backend",
    workMode: "Remote",
  },
];

export function getSampleJobsSnapshot(): JobsSnapshot {
  return {
    all: SAMPLE_JOBS.map((job) => ({ ...job })),
    daily: SAMPLE_JOBS.slice(0, 3).map((job) => ({ ...job })),
    updatedAt: new Date().toISOString(),
  };
}

export function getSampleAgentJobs(now = new Date()): AgentJob[] {
  return SAMPLE_JOBS.map((job, index) => {
    const isLinkedIn = index === 3;
    const recentMinutes = new Map([[0, 5], [4, 4], [5, 1]]).get(index);
    const firstSeenAt = new Date(
      now.getTime() - (recentMinutes === undefined ? (index + 1) * 24 * 60 * 60 * 1000 : recentMinutes * 60 * 1000),
    ).toISOString();
    return {
      id: index + 1,
      company: job.company,
      title: job.title,
      location: job.location,
      url: job.link,
      role: job.role,
      level: job.level,
      workMode: job.workMode,
      employmentType: "Full-time",
      department: job.department,
      techStack: [...job.techStack],
      postedDate: job.postedDate,
      firstSeenAt,
      lastSeenAt: now.toISOString(),
      sourceType: isLinkedIn ? "linkedin" : "ats",
      description: isLinkedIn ? null : `${job.title} at ${job.company}. ${job.department} team in Berlin.`,
    };
  });
}
