"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

type Status = {
  run: null | { status: string; conclusion: string | null; html_url: string; updated_at: string };
  progress: number;
  step: string;
  source_health: {
    company_name: string;
    career_page: string;
    ats_label: string | null;
    active: boolean;
    last_status: string | null;
    consecutive_errors: number;
    last_status_code: number | null;
    last_error: string | null;
    disabled_at: string | null;
    disabled_reason: string | null;
  }[];
};

export function AdminPanel() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const response = await fetch("/api/admin/status", { cache: "no-store" });
    if (response.status === 401) { setAuthenticated(false); return; }
    const payload = await response.json();
    if (!response.ok) { setMessage(payload.error ?? "Could not load status"); return; }
    setAuthenticated(true);
    setStatus(payload);
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!authenticated || status?.run?.status === "completed") return;
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [authenticated, refresh, status?.run?.status]);

  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage("");
    const response = await fetch("/api/admin/login", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }),
    });
    setBusy(false);
    if (!response.ok) { setMessage("Password is incorrect"); return; }
    setPassword(""); await refresh();
  }

  async function runUpdate() {
    setBusy(true); setMessage("");
    const response = await fetch("/api/admin/run", { method: "POST" });
    const payload = await response.json(); setBusy(false);
    if (!response.ok) { setMessage(payload.error ?? "Could not start update"); return; }
    setMessage("Daily update queued.");
    window.setTimeout(() => void refresh(), 1500);
  }

  if (authenticated === null) return <main className="admin-shell"><p>Checking session…</p></main>;
  if (!authenticated) return (
    <main className="admin-shell">
      <a href="/" className="back-link">← Job board</a>
      <form className="admin-card login-card" onSubmit={login}>
        <span className="eyebrow">Private access</span><h1>Daily update admin</h1>
        <p>Sign in to run the crawler and publish the latest database snapshot.</p>
        <label>Admin password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        <button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        {message && <p className="error">{message}</p>}
      </form>
    </main>
  );

  const running = status?.run && status.run.status !== "completed";
  return (
    <main className="admin-shell">
      <a href="/" className="back-link">← Job board</a>
      <section className="admin-card">
        <span className="eyebrow">GitHub Actions worker</span><h1>Daily update</h1>
        <p>The crawler runs outside Vercel and publishes the canonical PostgreSQL dataset.</p>
        <div className="progress-copy"><strong>{status?.step ?? "Ready"}</strong><span>{status?.progress ?? 0}%</span></div>
        <div className="progress"><span style={{ width: `${status?.progress ?? 0}%` }} /></div>
        <div className="admin-actions">
          <button onClick={runUpdate} disabled={busy || Boolean(running)}>{running ? "Update running…" : busy ? "Starting…" : "Run Daily Update"}</button>
          {status?.run?.html_url && <a href={status.run.html_url} target="_blank" rel="noreferrer">Open GitHub run</a>}
        </div>
        {status?.run?.updated_at && <small>Last activity: {new Date(status.run.updated_at).toLocaleString()}</small>}
        {message && <p className="notice">{message}</p>}
      </section>
      <section className="admin-card source-health-card">
        <span className="eyebrow">Crawler sources</span>
        <h2>Source health</h2>
        <p>Failing sources and sources automatically disabled in the last seven days.</p>
        {status?.source_health?.length ? (
          <div className="source-health-list">
            {status.source_health.map((source) => (
              <article className="source-health-item" key={`${source.company_name}-${source.career_page}`}>
                <div className="source-health-heading">
                  <strong>{source.company_name}</strong>
                  <span>{source.ats_label ?? "Unknown ATS"}</span>
                </div>
                <a href={source.career_page} target="_blank" rel="noreferrer">{source.career_page}</a>
                <p>
                  {source.consecutive_errors} consecutive errors
                  {source.last_status_code ? ` · HTTP ${source.last_status_code}` : ""}
                  {source.last_status ? ` · ${source.last_status}` : ""}
                </p>
                {source.last_error && <p className="source-health-error">{source.last_error}</p>}
                {source.disabled_reason && <p className="source-health-reason">{source.disabled_reason}</p>}
              </article>
            ))}
          </div>
        ) : (
          <p className="notice">No failing or recently disabled sources.</p>
        )}
      </section>
    </main>
  );
}
