import { AdminPanel } from "@/components/admin-panel";
import { PrivacyFooter } from "@/components/privacy-footer";

export const dynamic = "force-dynamic";

export default function AdminPage() {
  return (
    <>
      <AdminPanel />
      <div className="page-shell">
        <PrivacyFooter />
      </div>
    </>
  );
}
