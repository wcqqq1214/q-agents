import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const reportCardSource = readFileSync(
  new URL("./ReportCard.tsx", import.meta.url),
  "utf8",
);

test("report card tabs use english copy", () => {
  assert.match(
    reportCardSource,
    /<TabsTrigger value="cio">CIO Decision<\/TabsTrigger>/,
  );
  assert.match(
    reportCardSource,
    /<TabsTrigger value="quant">Quant Analysis<\/TabsTrigger>/,
  );
  assert.match(
    reportCardSource,
    /<TabsTrigger value="news">News Sentiment<\/TabsTrigger>/,
  );
  assert.match(
    reportCardSource,
    /<TabsTrigger value="social">Social Sentiment<\/TabsTrigger>/,
  );
});

test("report card query line does not render raw report query directly", () => {
  assert.doesNotMatch(
    reportCardSource,
    /\{report\.query \|\| "No query available\."\}/,
  );
});
