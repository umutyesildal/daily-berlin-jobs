export type GermanVerdict = "required" | "nice_to_have" | "not_required" | "unknown";

export interface GermanCheck {
  verdict: GermanVerdict;
  evidence: string[];
  inferred: boolean;
  language: "de" | "en" | "unknown";
}

const GERMAN_STOPWORDS = new Set((
  "aber als am an auch auf aus bei das dass dem den der des die doch durch ein eine " +
    "einer einem einen für gegen hat im in ist mit nach nicht oder sein sie sind und von " +
    "vor wie zu zum zur"
).split(/\s+/));

const ENGLISH_STOPWORDS = new Set((
  "a about after all also an and any are as at be because been before being between both " +
    "but by can could did do does doing for from had has have he her here him his how i if " +
    "in into is it its may more most my no not of on or our out over she should so some than " +
    "that the their them then there these they this to up was we were what when where which " +
    "who will with would you your"
).split(/\s+/));

const WORD_CHAR = String.raw`[\p{L}\p{N}_]`;
const NON_WORD_CHAR = String.raw`[^\p{L}\p{N}_]`;
const WORD_BOUNDARY = String.raw`(?:(?<=[\p{L}\p{N}_])(?![\p{L}\p{N}_])|(?<![\p{L}\p{N}_])(?=[\p{L}\p{N}_]))`;

function translatePythonPattern(pattern: string): string {
  let translated = "";
  let inCharacterClass = false;
  for (let index = 0; index < pattern.length; index += 1) {
    const current = pattern[index];
    if (current === "\\" && index + 1 < pattern.length) {
      const escaped = pattern[index + 1];
      if (escaped === "b" && !inCharacterClass) translated += WORD_BOUNDARY;
      else if (escaped === "w") translated += inCharacterClass ? String.raw`\p{L}\p{N}_` : WORD_CHAR;
      else if (escaped === "W" && !inCharacterClass) translated += NON_WORD_CHAR;
      else translated += `\\${escaped}`;
      index += 1;
      continue;
    }
    if (current === "[" && !inCharacterClass) inCharacterClass = true;
    else if (current === "]" && inCharacterClass) inCharacterClass = false;
    translated += current;
  }
  return translated;
}

function compilePythonPattern(pattern: string): RegExp {
  return new RegExp(translatePythonPattern(pattern), "iu");
}

const REQUIRED_GERMAN = [
  String.raw`\b(?:fließende|fliessende|fließend|fliessend|gute|sehr gute|ausgezeichnete|fundierte|verhandlungssichere)\s+deutschkenntnisse\b`,
  String.raw`\bdeutschkenntnisse\s+(?:sind\s+)?(?:fließend|fliessend)\b`,
  String.raw`\b(?:gute|sehr gute|ausgezeichnete|fundierte|verhandlungssichere|fließende|fliessende)\s+kenntnisse\s+(?:in|der)\s+deutsch(?:en)?(?:\s+sprache)?\b`,
  String.raw`\bdeutsch\s+(?:fließend|fliessend)\b`,
  String.raw`\b(?:fließend|fliessend)\s+deutsch\b`,
  String.raw`\b(?:fließend|fliessend)\s+in\s+deutsch(?:\s+und\s+englisch)?(?:\s*\([^)]*\))?`,
  String.raw`\bdeutsch\s+in\s+wort\s+und\s+schrift\b`,
  String.raw`\b(?:sehr\s+)?gute[sn]?\s+deutsch\b(?![-\w])`,
  String.raw`\bspeaks?\s+german\s+fluently\b`,
  String.raw`\bfluent\s+(?:in\s+)?german\b`,
  String.raw`\bfluent\s+in\s+english\s+and\s+german\b`,
  String.raw`\bfluency\s+in\s+(?:(?:english)\s+and\s+)?german(?:\s+and\s+english)?\b`,
  String.raw`\bfluent\s+german\s+and\s+english\b`,
  String.raw`\b(?:excellent|strong|very good)\s+(?:written\s+and\s+verbal\s+)?(?:communication\s+)?skills\s+in\s+english\s+and\s+german\b`,
  String.raw`\b(?:sehr\s+)?gute[nr]?\s+deutsch[- ]kenntnisse\b`,
  String.raw`\bdeutsch[- ]kenntnisse\s*\(\s*(?:mind(?:estens)?\.?\s*)?(?:b1|b2|c1|c2)\+?\s*\)`,
  String.raw`\b(?:fließende|fliessende|gute[nr]?|sehr gute[nr]?|ausgezeichnete[nr]?|fundierte[nr]?|verhandlungssichere[nr]?)\s+deutsch\s*-\s+und\s+(?:gute[nr]?\s+)?englischkenntnisse\b`,
  String.raw`\b(?:very\s+good|excellent|strong|proficient)\s+(?:level\s+of\s+)?german\b`,
  String.raw`\bdeutsch\s+und\s+englisch\s+auf\s+c[12]\s+bzw\.?\s+c[12](?:[- ]?niveau)\b`,
  String.raw`\bproficiency\s+in\s+german\b`,
  String.raw`\bdeutschkenntnisse\s*\(\s*mind(?:estens)?\.?\s*(?:b2|c1|c2)\+?\s*\)`,
  String.raw`\bdeutschkenntnisse\s+mind(?:estens)?\.?\s*(?:b2|c1|c2)\+?\b`,
  String.raw`\bdeutsch(?:kenntnisse)?\s*(?:\(\s*)?(?:b2|c1|c2)\+?(?:[- ]level)?\s*\)?(?=\W|$)`,
  String.raw`\bdeutsch\s+auf\s+(?:dem\s+)?(?:b2|c1|c2)\+?[- ]niveau\b`,
  String.raw`\bgerman\s*(?:\(\s*)?(?:b2|c1|c2)\+?(?:[- ]level)?\s*\)?(?=\W|$)`,
  String.raw`\bgerman\s+(?:at|on)\s+(?:the\s+)?(?:b2|c1|c2)\+?\s+level\b`,
  String.raw`\bgerman\s+language\s+skills?\s*\(\s*(?:b2|c1|c2)\+?(?:[- ]level)?\s*\)`,
  String.raw`\bgerman\s+(?:is\s+)?a\s+must\b`,
  String.raw`\bnative\s+(?:level\s+)?german\b`,
  String.raw`\bdeutsch(?:kenntnisse)?\s+(?:auf\s+)?(?:muttersprachlichem|muttersprachler)\w*\s+niveau\b`,
  String.raw`\bsehr gute kenntnisse der deutschen sprache\b`,
].map(compilePythonPattern);

const NICE_GERMAN = [
  String.raw`\bgerman(?:\s+language)?(?:\s+skills?)?\s+(?:is|are)?\s*(?:(?:a|an)\s+)?(?:plus|bonus|advantage|advantageous|nice to have|preferred|desirable)\b`,
  String.raw`\bdeutschkenntnisse\s+(?:sind\s+)?(?:von vorteil|wünschenswert|wuenschenswert|ein plus)\b`,
  String.raw`\bdeutsch\s+(?:ist\s+)?(?:ein\s+)?(?:plus|vorteil|bonus|wünschenswert|wuenschenswert)\b`,
].map(compilePythonPattern);

const NOT_REQUIRED_GERMAN = [
  String.raw`\bno german required\b`,
  String.raw`\bgerman\s+(?:is\s+)?not required\b`,
  String.raw`\bkeine deutschkenntnisse erforderlich\b`,
  String.raw`\bdeutschkenntnisse sind nicht erforderlich\b`,
  String.raw`\benglish is our\s+(?:working|company)\s+language\b`,
  String.raw`\benglish is the (?:working|company) language\b`,
].map(compilePythonPattern);

const GERMAN_QUALIFIER = compilePythonPattern(
  String.raw`\b(?:a\s+plus|plus|bonus|advantage|advantageous|nice\s+to\s+have|preferred|desirable|von\s+vorteil|wünschenswert|wuenschenswert|ein\s+plus)\b(?!\s*:)`,
);
const EVIDENCE_BREAK = /[.!?;\n•]/gu;
const LANGUAGE_NOUN = String.raw`(?:german|english|deutsch\w*|englisch\w*)`;
const GERMAN_CLAUSE_BREAK = compilePythonPattern(
  String.raw`[,;.!?\n•]|\b(?:und|and)\b(?=\s+${LANGUAGE_NOUN}\b)`,
);
const TITLE_GERMAN_REQUIRED = [
  String.raw`\bgerman[- ]speaker\b`,
  String.raw`\bwith\s+german\b`,
  String.raw`\bgerman[- ]speaking\b`,
  String.raw`\bdeutschsprachig\w*\b`,
].map(compilePythonPattern);

type RegexMatch = { start: number; end: number; value: string };

function findMatches(
  pattern: RegExp,
  text: string,
  start = 0,
  end = text.length,
): RegexMatch[] {
  const target = text.slice(0, end);
  const flags = pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`;
  const scanner = new RegExp(pattern.source, flags);
  scanner.lastIndex = start;
  const matches: RegexMatch[] = [];
  let match = scanner.exec(target);
  while (match) {
    matches.push({ start: match.index, end: match.index + match[0].length, value: match[0] });
    if (!match[0].length) scanner.lastIndex += 1;
    match = scanner.exec(target);
  }
  return matches;
}

function searchFrom(
  pattern: RegExp,
  text: string,
  start: number,
  end = text.length,
): RegexMatch | undefined {
  return findMatches(pattern, text, start, end)[0];
}

function caseFold(value: string): string {
  return value
    .toLowerCase()
    .replace(/ß/g, "ss")
    .replace(/ı/g, "i")
    .replace(/ſ/g, "s")
    .replace(/ς/g, "σ");
}

function decodeHtmlEntities(value: string): string {
  const named: Record<string, string> = {
    amp: "&",
    apos: "'",
    auml: "ä",
    copy: "©",
    gt: ">",
    lt: "<",
    nbsp: " ",
    ouml: "ö",
    quot: "\"",
    szlig: "ß",
    uuml: "ü",
  };
  return value.replace(/&(#x[\da-f]+|#\d+|[a-z][\da-z]+);/gi, (entity, code: string) => {
    if (code[0] !== "#") return named[code.toLowerCase()] ?? entity;
    const numeric = code[1].toLowerCase() === "x"
      ? Number.parseInt(code.slice(2), 16)
      : Number.parseInt(code.slice(1), 10);
    if (!Number.isFinite(numeric) || numeric < 0 || numeric > 0x10ffff) return entity;
    try {
      return String.fromCodePoint(numeric);
    } catch {
      return entity;
    }
  });
}

function stripHtml(value: string): string {
  return decodeHtmlEntities(
    value
      .replace(/<!--[\s\S]*?-->/g, " ")
      .replace(/<(script|style|noscript)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, " ")
      .replace(/<[^>]*>/g, " "),
  );
}

function cleanText(text: string): string {
  const withVisibleText = /<\s*(?:html|body|div|p|section|ul|li)\b/i.test(text)
    ? stripHtml(text)
    : text;
  return withVisibleText.replace(/\s+/gu, " ").trim();
}

function languageOf(text: string): GermanCheck["language"] {
  const words = caseFold(text).match(/[a-zäöüß]+/gu) ?? [];
  if (!words.length) return "unknown";
  const de = words.filter((word) => GERMAN_STOPWORDS.has(word)).length;
  const en = words.filter((word) => ENGLISH_STOPWORDS.has(word)).length;
  if (Math.max(de, en) < 2 || de === en) return "unknown";
  return de > en ? "de" : "en";
}

function stripEvidenceEdges(value: string): string {
  return value.replace(/^[ \u2022]+|[ \u2022]+$/gu, "");
}

function sentenceEvidence(text: string, span: [number, number]): string {
  const [start, end] = span;
  const previous = findMatches(EVIDENCE_BREAK, text, 0, start);
  const sentenceStart = previous.length ? previous[previous.length - 1].end : 0;
  const following = searchFrom(EVIDENCE_BREAK, text, end);
  const sentenceEnd = following
    ? (following.value === "•" ? following.start : following.end)
    : text.length;
  let evidence = stripEvidenceEdges(text.slice(sentenceStart, sentenceEnd));
  if ([...evidence].length > 240) evidence = stripEvidenceEdges(text.slice(start, end));
  return evidence || stripEvidenceEdges(text.slice(start, end));
}

function germanRequirement(
  text: string,
  language: GermanCheck["language"],
  title?: string,
): Pick<GermanCheck, "verdict" | "evidence" | "inferred"> {
  const titleText = String(title ?? "").trim();
  if (titleText && TITLE_GERMAN_REQUIRED.some((pattern) => pattern.test(titleText))) {
    return { verdict: "required", evidence: [titleText], inferred: false };
  }

  const collectSpans = (patterns: RegExp[]) =>
    patterns.flatMap((pattern) => findMatches(pattern, text).map(({ start, end }) => [start, end] as [number, number]));
  const requiredMatches = collectSpans(REQUIRED_GERMAN);
  const niceMatches = collectSpans(NICE_GERMAN);
  const notRequiredMatches = collectSpans(NOT_REQUIRED_GERMAN);

  function isQualified(span: [number, number]): boolean {
    const end = span[1];
    const clauseBreak = searchFrom(GERMAN_CLAUSE_BREAK, text, end);
    const clauseEnd = clauseBreak?.start ?? text.length;
    const windowEnd = Math.min(clauseEnd, end + 41);
    const qualifier = searchFrom(GERMAN_QUALIFIER, text, end, windowEnd);
    return Boolean(qualifier && qualifier.start - end <= 40);
  }

  let verdict: GermanVerdict = "unknown";
  let matches: [number, number][] = [];
  if (requiredMatches.length) {
    verdict = requiredMatches.every(isQualified) ? "nice_to_have" : "required";
    matches = requiredMatches;
  } else if (niceMatches.length) {
    verdict = "nice_to_have";
    matches = niceMatches;
  } else if (notRequiredMatches.length) {
    verdict = "not_required";
    matches = notRequiredMatches;
  }

  if (matches.length) {
    const evidence: string[] = [];
    for (const span of matches) {
      const snippet = sentenceEvidence(text, span);
      if (!evidence.includes(snippet)) evidence.push(snippet);
    }
    return { verdict, evidence, inferred: false };
  }
  return language === "de"
    ? { verdict: "required", evidence: [], inferred: true }
    : { verdict: "unknown", evidence: [], inferred: false };
}

export function checkGerman(text: string, title?: string): GermanCheck {
  const cleaned = cleanText(text);
  const language = languageOf(cleaned);
  const requirement = germanRequirement(cleaned, language, title);
  return { ...requirement, language };
}
