import assert from "node:assert/strict";
import test from "node:test";
import { GERMAN_CHECK_CASES } from "./german-check-cases.ts";
import { checkGerman } from "./german-check.ts";

for (const fixture of GERMAN_CHECK_CASES) {
  test(fixture.name, () => {
    const result = checkGerman(fixture.text, fixture.title);
    const expected = fixture.expected;

    if (expected.verdict !== undefined) assert.equal(result.verdict, expected.verdict);
    if (expected.inferred !== undefined) assert.equal(result.inferred, expected.inferred);
    if (expected.language !== undefined) assert.equal(result.language, expected.language);
    if (expected.evidence !== undefined) assert.deepEqual(result.evidence, expected.evidence);
    if (expected.evidenceNonEmpty) assert.ok(result.evidence.length > 0);
    if (expected.evidenceIncludes !== undefined) {
      assert.ok(result.evidence.some((line) => line.includes(expected.evidenceIncludes!)));
    }
    if (expected.evidenceMaxLength !== undefined) {
      assert.ok(result.evidence[0]?.length <= expected.evidenceMaxLength);
    }
  });
}
