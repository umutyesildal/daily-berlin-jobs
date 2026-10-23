export type Job = {
  source: "ats" | "linkedin";
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
};

export type JobsSnapshot = {
  all: Job[];
  daily: Job[];
  updatedAt: string;
};
