import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function loadRenderMarkdown(): (text: string) => string {
  const source = readFileSync(
    new URL("./MarkdownRenderer.tsx", import.meta.url),
    "utf8",
  );
  const helpersMatch = source.match(
    /function getMarkdownTableCells[\s\S]*?function isMarkdownTableSeparator[\s\S]*?\n}\n\nexport function MarkdownRenderer/,
  );
  const match = source.match(
    /const renderMarkdown = \(text: string\): string => \{([\s\S]*?)\n  \};\n\n  return \(/,
  );

  assert.ok(helpersMatch, "markdown table helpers should exist");
  assert.ok(match, "renderMarkdown implementation should exist");

  const helpersSource = helpersMatch[0]
    .replace(/\n\nexport function MarkdownRenderer$/, "")
    .replace(/: string\[\] \| null/g, "")
    .replace(/: string/g, "")
    .replace(/: boolean/g, "");
  const functionBody = match[1].replace(/: string\[\]/g, "");
  return new Function(
    `${helpersSource}\nreturn (text) => {${functionBody}};`,
  )() as (text: string) => string;
}

test("report source bullets with pipes are not mis-rendered as a table", () => {
  const renderMarkdown = loadRenderMarkdown();
  const content = [
    "## Recent Sources",
    "",
    '- **N/A | Wed, 01 Apr 2026 13:49:00 GMT**: Example source with linked tickers DIA | QQQ | SPY.',
  ].join("\n");

  const html = renderMarkdown(content);

  assert.doesNotMatch(html, /<table/);
  assert.match(html, /<ul class="list-disc/);
});

test("markdown tables still render as tables", () => {
  const renderMarkdown = loadRenderMarkdown();
  const content = [
    "| Name | Bias |",
    "| --- | --- |",
    "| MSFT | bearish |",
  ].join("\n");

  const html = renderMarkdown(content);

  assert.match(html, /<table/);
  assert.match(html, /<td class="border border-border px-3 py-2">MSFT<\/td>/);
});
