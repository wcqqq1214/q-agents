import removeMd from "remove-markdown";

/**
 * Returns a plain-text summary truncated to maxLength characters.
 * Uses remove-markdown to safely handle nested blockquotes, tables,
 * and code blocks that hand-rolled regexes commonly miss.
 */
export function markdownSummary(text: string, maxLength = 200): string {
  const plain = removeMd(text).replace(/\s+/g, " ").trim();
  if (plain.length <= maxLength) return plain;
  return plain.slice(0, maxLength).trimEnd() + "...";
}
