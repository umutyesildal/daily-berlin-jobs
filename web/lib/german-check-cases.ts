import type { GermanVerdict } from "./german-check.ts";

export type GermanCheckExpectation = {
  verdict?: GermanVerdict;
  evidence?: string[];
  evidenceNonEmpty?: boolean;
  evidenceIncludes?: string;
  evidenceMaxLength?: number;
  inferred?: boolean;
  language?: "de" | "en" | "unknown";
};

export type GermanCheckCase = {
  name: string;
  text: string;
  title?: string;
  expected: GermanCheckExpectation;
};

const explicitRequiredPhrasings = [
  "Wir erwarten fließende Deutschkenntnisse.",
  "Sehr gute Deutschkenntnisse sind erforderlich.",
  "Verhandlungssichere Deutschkenntnisse werden vorausgesetzt.",
  "Deutsch (B2) ist zwingend erforderlich.",
  "The candidate must be fluent in German.",
  "German (C1) is required for this role.",
  "German is a must for customer communication.",
  "Native German is required.",
  "Dein Profil: Sehr gutes Deutsch in Wort und Schrift (mind. C1).",
  "Sehr gutes Deutsch und Englisch.",
];

const niceToHavePhrasings = [
  "German is a plus.",
  "German is a bonus.",
  "German is an advantage.",
  "German is advantageous.",
  "German is nice to have.",
  "German is preferred.",
  "German is desirable.",
  "German skills are nice to have.",
  "Deutschkenntnisse sind von Vorteil.",
  "Deutschkenntnisse sind wünschenswert.",
  "No German required. Fluent German is a plus.",
];

const notRequiredPhrasings = [
  "No German required.",
  "German is not required.",
  "Keine Deutschkenntnisse erforderlich.",
  "English is our working language.",
];

const additionalRequiredPhrasings = [
  "We require fluent in English and German.",
  "Fluent in German (and English) is needed.",
  "Deutschkenntnisse mindestens B2.",
  "German (C1-level) is essential.",
  "German at C1 level is required.",
  "German on C1 level is required.",
  "Deutsch auf C1-Niveau erforderlich.",
  "Deutschkenntnisse (mind. B2) sind Voraussetzung.",
  "Excellent German language skills are required.",
  "Proficiency in German is needed.",
  "Excellent written and verbal communication skills in English and German.",
  "Fluent in German and English.",
  "Fluency in German and English.",
  "Fluency in English and German.",
  "We require fluent German and English.",
  "Fließend in Deutsch.",
  "Fliessend in Deutsch.",
  "Fließend in Deutsch und Englisch (mindestens C1-Niveau).",
  "Sehr gute Deutsch-Kenntnisse.",
  "Gute Deutsch-Kenntnisse.",
  "Deutsch-Kenntnisse (C1).",
  "Deutsch und Englisch auf C2 bzw. C1-Niveau.",
  "Sehr gute Deutschkenntnisse, gute Englischkenntnisse von Vorteil.",
  "Verhandlungssichere Deutsch- und Englischkenntnisse.",
  "Du sprichst fließend Deutsch und sehr gutes Englisch.",
  "Deine sehr guten Deutsch- und Englischkenntnisse sind erforderlich.",
];

const titleSignals = [
  "German Speaker Recruiter",
  "Recruiter with German",
  "German-speaking Talent Partner",
  "Deutschsprachige Recruiterin",
];

const longEvidenceText =
  "Earlier role requirements. " +
  "Additional duties and responsibilities. ".repeat(20) +
  "Verhandlungssichere Deutsch- und Englischkenntnisse" +
  " further posting text".repeat(20);

function makeCase(
  name: string,
  text: string,
  expected: GermanCheckExpectation,
  title?: string,
): GermanCheckCase {
  return { name, text, title, expected };
}

export const GERMAN_CHECK_CASES: GermanCheckCase[] = [
  ...explicitRequiredPhrasings.map((text) =>
    makeCase(`explicit German requirement: ${text}`, text, {
      verdict: "required",
      inferred: false,
      evidenceNonEmpty: true,
    })),
  ...niceToHavePhrasings.map((text) =>
    makeCase(`German is nice to have: ${text}`, text, {
      verdict: "nice_to_have",
      evidenceNonEmpty: true,
    })),
  ...notRequiredPhrasings.map((text) =>
    makeCase(`German is not required: ${text}`, text, { verdict: "not_required" })),
  makeCase(
    "German-language ad without an explicit statement is inferred required",
    "Wir suchen eine Person für unser Team und freuen uns auf Ihre Bewerbung.",
    { language: "de", verdict: "required", inferred: true, evidence: [] },
  ),
  makeCase(
    "English-language ad without a German statement stays unknown",
    "We are looking for an engineer who will work with our team and customers.",
    { language: "en", verdict: "unknown", inferred: false },
  ),
  makeCase(
    "HTML text is stripped before language detection",
    "<p>Wir suchen eine Person im <b>Team</b>.</p>",
    { language: "de" },
  ),
  makeCase(
    "fluent German followed by a plus qualifier is nice to have",
    "We are an English-speaking team. No German required. Fluent German is a plus. Salary up to 80k.",
    { verdict: "nice_to_have", inferred: false },
  ),
  makeCase(
    "German fluency and German written-language phrasing are explicit",
    "Your profile: You speak German fluently. Deutsch fließend in Wort und Schrift. We offer a great team in Berlin and you will work with our customers.",
    { verdict: "required", inferred: false },
  ),
  makeCase(
    "German C1 is an explicit requirement",
    "Requirements: 5 years of Python, German C1 and English B2. You will build our platform and the team is in Munich.",
    { verdict: "required", inferred: false },
  ),
  makeCase(
    "gute Deutschkenntnisse are explicit and ticket benefits are not salary",
    "Ihr Profil: abgeschlossene Ausbildung, gute Deutschkenntnisse, Führerschein Klasse B. Wir bieten 30 Tage Urlaub und ein Deutschlandticket für 49 €.",
    { verdict: "required", inferred: false },
  ),
  ...additionalRequiredPhrasings.map((text) =>
    makeCase(`additional explicit German requirement: ${text}`, text, {
      verdict: "required",
      inferred: false,
      evidenceIncludes: text,
    })),
  makeCase("bare Deutschkenntnisse plus wording is nice to have", "Deutschkenntnisse ein Plus.", {
    verdict: "nice_to_have",
  }),
  makeCase("unrelated German company wording is unknown", "We are a German company serving the German market.", {
    verdict: "unknown",
    inferred: false,
  }),
  makeCase("bare hyphenated Deutsch-Kenntnisse in English remains unknown", "The posting mentions Deutsch-Kenntnisse.", {
    verdict: "unknown",
    inferred: false,
  }),
  makeCase("bare Deutsch-Kenntnisse in a German ad keeps inferred semantics", "Die Ausschreibung ist auf Deutsch. Deutsch-Kenntnisse.", {
    verdict: "required",
    inferred: true,
  }),
  ...titleSignals.map((title) =>
    makeCase(`German title signal: ${title}`, "English-language job text.", {
      verdict: "required",
      inferred: false,
      evidence: [title],
    }, title)),
  makeCase(
    "Bonus heading does not qualify the preceding required language clause",
    "Fließend in Deutsch und Englisch (mindestens C1-Niveau) Bonus: Erfahrung mit MCP/APIs.",
    {
      verdict: "required",
      inferred: false,
      evidenceIncludes: "Fließend in Deutsch und Englisch (mindestens C1-Niveau)",
    },
  ),
  makeCase(
    "German evidence stays with its bullet and language clause",
    "Responsibilities • Sehr gute Deutschkenntnisse, gute Englischkenntnisse von Vorteil • Gute MS Office-Kenntnisse.",
    {
      verdict: "required",
      evidence: ["Sehr gute Deutschkenntnisse, gute Englischkenntnisse von Vorteil"],
    },
  ),
  makeCase("long-ad German evidence keeps the explicit language clause", longEvidenceText, {
    verdict: "required",
    evidenceIncludes: "Verhandlungssichere Deutsch- und Englischkenntnisse",
    evidenceMaxLength: 99,
  }),
];
