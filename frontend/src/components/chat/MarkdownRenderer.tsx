"use client";

interface MarkdownRendererProps {
  content: string;
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  // Convert markdown to HTML with proper styling
  const renderMarkdown = (text: string): string => {
    let html = text;

    // Escape HTML first
    html = html
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Headers (must be done before other replacements)
    html = html.replace(
      /^### (.+)$/gim,
      '<h3 class="text-base font-semibold mt-4 mb-2 text-foreground">$1</h3>',
    );
    html = html.replace(
      /^## (.+)$/gim,
      '<h2 class="text-lg font-bold mt-5 mb-3 text-foreground">$1</h2>',
    );
    html = html.replace(
      /^# (.+)$/gim,
      '<h1 class="text-xl font-bold mt-6 mb-4 text-foreground">$1</h1>',
    );

    // Bold
    html = html.replace(
      /\*\*(.+?)\*\*/g,
      '<strong class="font-semibold text-foreground">$1</strong>',
    );

    // Italic
    html = html.replace(/\*(.+?)\*/g, '<em class="italic">$1</em>');

    // Code inline
    html = html.replace(
      /`(.+?)`/g,
      '<code class="bg-muted px-1.5 py-0.5 rounded text-xs font-mono">$1</code>',
    );

    // Horizontal rule
    html = html.replace(/^---+$/gim, '<hr class="my-4 border-border" />');

    // Tables - improved handling
    const lines = html.split("\n");
    let inTable = false;
    let tableHtml = "";
    const processedLines: string[] = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      if (line.includes("|")) {
        if (!inTable) {
          inTable = true;
          tableHtml =
            '<table class="w-full border-collapse my-3 text-sm"><tbody>';
        }

        const cells = line.split("|").filter((cell) => cell.trim());

        // Skip separator lines (e.g., |---|---|)
        if (cells.every((cell) => /^[-:\s]+$/.test(cell))) {
          continue;
        }

        const cellsHtml = cells
          .map(
            (cell) =>
              `<td class="border border-border px-3 py-2">${cell.trim()}</td>`,
          )
          .join("");
        tableHtml += `<tr>${cellsHtml}</tr>`;
      } else {
        if (inTable) {
          tableHtml += "</tbody></table>";
          processedLines.push(tableHtml);
          tableHtml = "";
          inTable = false;
        }
        processedLines.push(line);
      }
    }

    if (inTable) {
      tableHtml += "</tbody></table>";
      processedLines.push(tableHtml);
    }

    html = processedLines.join("\n");

    // Unordered lists
    html = html.replace(/^[\-\*] (.+)$/gim, '<li class="ml-4 my-1">$1</li>');
    html = html.replace(
      /(<li class="ml-4 my-1">[\s\S]*?<\/li>\n?)+/g,
      '<ul class="list-disc space-y-1 my-2 ml-4">$&</ul>',
    );

    // Ordered lists
    html = html.replace(/^\d+\. (.+)$/gim, '<li class="ml-4 my-1">$1</li>');

    // Paragraphs - split by double newlines
    const paragraphs = html.split("\n\n");
    html = paragraphs
      .map((para) => {
        const trimmed = para.trim();
        if (!trimmed) return "";

        // Don't wrap if already wrapped in a tag
        if (
          trimmed.startsWith("<h") ||
          trimmed.startsWith("<ul") ||
          trimmed.startsWith("<ol") ||
          trimmed.startsWith("<table") ||
          trimmed.startsWith("<hr") ||
          trimmed.startsWith("<div")
        ) {
          return trimmed;
        }

        return `<p class="my-2 text-sm leading-relaxed text-foreground">${trimmed}</p>`;
      })
      .join("\n");

    // Single line breaks within paragraphs
    html = html.replace(/\n/g, "<br />");

    return html;
  };

  return (
    <div
      className="markdown-content"
      dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
    />
  );
}
