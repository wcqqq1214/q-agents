function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function getReportQueryDisplay(query: string, symbol: string): string {
  const normalizedQuery = query.trim();
  const normalizedSymbol = symbol.trim();

  if (!normalizedQuery || !normalizedSymbol) {
    return normalizedQuery;
  }

  const symbolPattern = new RegExp(
    `\\b${escapeRegExp(normalizedSymbol)}\\b`,
    "gi",
  );
  const withoutSymbol = normalizedQuery.replace(symbolPattern, " ");

  return withoutSymbol
    .replace(/\(\s*\)/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .replace(/([,.;:!?]){2,}/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}
