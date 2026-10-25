"use client";

import { useState } from "react";
import { checkGerman, type GermanCheck } from "@/lib/german-check";

const VERDICT_LABELS: Record<GermanCheck["verdict"], string> = {
  required: "German required",
  nice_to_have: "German is a plus",
  not_required: "German not required",
  unknown: "Not mentioned",
};

export function GermanCheckTool() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [result, setResult] = useState<GermanCheck | null>(null);

  function runCheck() {
    setResult(checkGerman(description, title));
  }

  return (
    <>
      <div className="german-check-form">
        <label htmlFor="german-check-title">Job title (optional)</label>
        <input
          autoComplete="off"
          id="german-check-title"
          onChange={(event) => setTitle(event.target.value)}
          type="text"
          value={title}
        />
        <label htmlFor="german-check-description">Job description</label>
        <textarea
          id="german-check-description"
          onChange={(event) => setDescription(event.target.value)}
          rows={12}
          value={description}
        />
        <button onClick={runCheck} type="button">Check</button>
      </div>

      <p className="german-check-caveat">
        This checks the wording of the ad only. It isn&apos;t legal or immigration advice.
      </p>

      {result && (
        <section className="german-check-result" aria-live="polite" aria-labelledby="german-check-result-title">
          <h2 id="german-check-result-title">Result</h2>
          <p><strong>{VERDICT_LABELS[result.verdict]}</strong></p>
          {result.evidence.length > 0 && (
            <div>
              <p>Evidence</p>
              {result.evidence.map((line, index) => (
                <blockquote key={`${index}-${line}`}>{line}</blockquote>
              ))}
            </div>
          )}
          {result.inferred && (
            <p>The ad itself is written in German, so German is very likely required.</p>
          )}
          {result.verdict === "unknown" && (
            <p>The ad doesn&apos;t mention German. Check the full posting or ask the recruiter before assuming English is enough.</p>
          )}
        </section>
      )}

      <aside className="german-check-cta">
        <p>
          Want the full assistant? <a href="https://github.com/umutyesildal/berlin-job-search">Berlin Job Search</a> finds jobs across Germany, checks Blue Card salary rules and helps you write a Lebenslauf. Free and open source.
        </p>
      </aside>
    </>
  );
}
