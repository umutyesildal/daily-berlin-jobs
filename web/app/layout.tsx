import type { Metadata } from "next";
import { Analytics } from "@vercel/analytics/next";
import { SITE_URL } from "@/lib/seo";
import "./styles.css";

const siteDescription = "Current Berlin engineering jobs from company career sites and LinkedIn, updated daily.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Engineering jobs in Berlin, updated daily",
    template: "%s | Daily Berlin Jobs",
  },
  description: siteDescription,
  openGraph: {
    type: "website",
    siteName: "Daily Berlin Jobs",
    title: "Engineering jobs in Berlin, updated daily",
    description: siteDescription,
    url: SITE_URL,
    images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: "Daily Berlin Jobs" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Engineering jobs in Berlin, updated daily",
    description: siteDescription,
    images: ["/opengraph-image"],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        {children}
        <Analytics />
      </body>
    </html>
  );
}
