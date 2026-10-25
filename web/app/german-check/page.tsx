import type { Metadata } from "next";
import { PrivacyFooter } from "@/components/privacy-footer";
import { GermanCheckTool } from "@/components/german-check-tool";
import { SITE_URL } from "@/lib/seo";

export const metadata: Metadata = {
  title: "Does this job need German? Free checker",
  description: "Paste a job ad and see whether German is required, a plus, or not mentioned, with the exact line quoted.",
  alternates: { canonical: `${SITE_URL}/german-check` },
};

export default function GermanCheckPage() {
  return (
    <main className="page-shell seo-page">
      <header className="seo-page-header">
        <h1>Does this job need German?</h1>
        <p>Paste a job ad. You&apos;ll see whether German is required, a plus, or not mentioned, with the exact line quoted. Your text never leaves your browser.</p>
      </header>
      <section className="seo-section">
        <GermanCheckTool />
      </section>
      <PrivacyFooter />
    </main>
  );
}
