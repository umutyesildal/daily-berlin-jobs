import type { Metadata } from "next";
import { PrivacyFooter } from "@/components/privacy-footer";
import { SITE_URL } from "@/lib/seo";

export const metadata: Metadata = {
  title: "Privacy policy",
  description: "Daily Berlin Jobs is a free, non-commercial board of Berlin tech jobs, run by Umut Yesildal in Berlin, Germany.",
  alternates: { canonical: `${SITE_URL}/privacy` },
};

export default function PrivacyPage() {
  return (
    <main className="page-shell seo-page">
      <header className="seo-page-header">
        <h1>Privacy policy</h1>
        <p>Last updated: 25 October 2026</p>
      </header>
      <article className="seo-section job-description">
        <p>Daily Berlin Jobs is a free, non-commercial board of Berlin tech jobs, run by Umut Yesildal in Berlin, Germany. It has no user accounts, sign-up forms, newsletters, ads or tracking cookies.</p>

        <section>
          <h2>What happens when you visit</h2>
          <p><strong>Hosting.</strong> The site, its API (<code>/api/v1</code>), RSS feed and MCP server (<code>/api/mcp</code>) run on Vercel. To deliver pages and keep the service secure, Vercel processes technical request data such as your IP address, browser user agent, the requested URL (including any search terms in it) and the time of the request. Vercel keeps these logs for a limited period under its own policy. They are not combined with other data and are not used to identify visitors.</p>
          <p><strong>Analytics.</strong> The site uses Vercel Web Analytics to count page views. It sets no cookies and stores no IP addresses. For each page view it records the page URL, the referring page, approximate location (country/region/city), browser, operating system and device type. Visitors are counted using a hash of the request that is discarded after 24 hours, so visits can't be linked across days or across other websites. Only aggregated statistics are shown. Details: <a href="https://vercel.com/docs/analytics/privacy-policy">Vercel Web Analytics privacy</a>.</p>
          <p><strong>Cookies.</strong> Public pages set no cookies. The only cookie, <code>daily_berlin_admin</code>, is set when the site's administrator signs in to the admin area.</p>
          <p><strong>API, RSS and MCP users.</strong> Requests from apps and AI assistants (for example a connector in Claude or another MCP client) are handled like any other web request: no key, no account, no stored profile. When you use an AI assistant, the assistant provider's own privacy policy also applies.</p>
        </section>

        <section>
          <h2>Job data</h2>
          <p>The listings come from public company career pages and public LinkedIn job pages. They describe jobs and employers, not job seekers. If a listing contains personal data about you (for example a recruiter's name) or should be removed, open an issue on <a href="https://github.com/umutyesildal/daily-berlin-jobs/issues">GitHub</a> and it will be corrected or removed.</p>
        </section>

        <section>
          <h2>Service providers</h2>
          <ul>
            <li><strong>Vercel Inc.</strong> (hosting, analytics), USA. Certified under the EU–US Data Privacy Framework.</li>
            <li><strong>Supabase</strong> (database for job listings). It stores no visitor data.</li>
          </ul>
        </section>

        <section>
          <h2>Legal basis and your rights</h2>
          <p>Processing is based on legitimate interest (Art. 6(1)(f) GDPR) in running a secure, working website and understanding its use in aggregate. You have the right to access, rectification, erasure, restriction of processing and objection, and the right to complain to a data protection authority. In Berlin that is the <a href="https://www.datenschutz-berlin.de/">Berliner Beauftragte für Datenschutz und Informationsfreiheit</a>.</p>
        </section>

        <section>
          <h2>Contact</h2>
          <p>Questions or requests: open an issue at <a href="https://github.com/umutyesildal/daily-berlin-jobs/issues">github.com/umutyesildal/daily-berlin-jobs</a> or contact <a href="https://github.com/umutyesildal">Umut Yesildal on GitHub</a>.</p>
        </section>

        <section>
          <h2>Changes</h2>
          <p>If this policy changes, the date at the top changes too.</p>
        </section>
      </article>
      <PrivacyFooter />
    </main>
  );
}
