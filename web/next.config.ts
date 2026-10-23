import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return {
      beforeFiles: [
        { source: "/jobs.md", destination: "/api/v1/jobs?format=md" },
        { source: "/today.md", destination: "/api/v1/jobs?format=md&latest=1" },
        { source: "/jobs/:id(\\d+).md", destination: "/api/v1/jobs/:id?format=md" },
        { source: "/companies.md", destination: "/api/v1/companies?format=md" },
      ],
      afterFiles: [],
      fallback: [],
    };
  },
};

export default nextConfig;
