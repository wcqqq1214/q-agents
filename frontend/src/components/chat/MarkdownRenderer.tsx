"use client";

import type { ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

interface MarkdownRendererProps {
  content: string;
}

function MarkdownLink({
  className,
  href,
  ...props
}: ComponentPropsWithoutRef<"a">) {
  const isHashLink = href?.startsWith("#");

  return (
    <a
      {...props}
      className={cn(
        "font-medium text-primary underline underline-offset-4",
        className,
      )}
      href={href}
      rel={isHashLink ? undefined : "noreferrer noopener"}
      target={isHashLink ? undefined : "_blank"}
    />
  );
}

const markdownComponents: Components = {
  a({ className, href, ...props }) {
    return <MarkdownLink className={className} href={href} {...props} />;
  },
  blockquote({ className, ...props }) {
    return (
      <blockquote
        {...props}
        className={cn(
          "my-4 border-l-2 border-border pl-4 text-muted-foreground italic",
          className,
        )}
      />
    );
  },
  code({ className, ...props }) {
    return (
      <code
        {...props}
        className={cn(
          "rounded bg-muted px-1.5 py-0.5 font-mono text-xs",
          className,
        )}
      />
    );
  },
  del({ className, ...props }) {
    return <del {...props} className={cn("line-through", className)} />;
  },
  h1({ className, ...props }) {
    return (
      <h1
        {...props}
        className={cn(
          "mt-6 mb-4 text-xl font-bold text-foreground first:mt-0",
          className,
        )}
      />
    );
  },
  h2({ className, ...props }) {
    return (
      <h2
        {...props}
        className={cn(
          "mt-5 mb-3 text-lg font-bold text-foreground first:mt-0",
          className,
        )}
      />
    );
  },
  h3({ className, ...props }) {
    return (
      <h3
        {...props}
        className={cn(
          "mt-4 mb-2 text-base font-semibold text-foreground first:mt-0",
          className,
        )}
      />
    );
  },
  hr({ className, ...props }) {
    return <hr {...props} className={cn("my-4 border-border", className)} />;
  },
  li({ className, ...props }) {
    return <li {...props} className={cn("my-1", className)} />;
  },
  ol({ className, ...props }) {
    return (
      <ol {...props} className={cn("my-2 ml-4 list-decimal", className)} />
    );
  },
  p({ className, ...props }) {
    return (
      <p
        {...props}
        className={cn(
          "my-2 text-sm leading-relaxed text-foreground",
          className,
        )}
      />
    );
  },
  pre({ className, ...props }) {
    return (
      <pre
        {...props}
        className={cn(
          "my-4 overflow-x-auto rounded-md bg-muted p-4 text-sm text-foreground [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-inherit",
          className,
        )}
      />
    );
  },
  strong({ className, ...props }) {
    return (
      <strong
        {...props}
        className={cn("font-semibold text-foreground", className)}
      />
    );
  },
  table({ className, ...props }) {
    return (
      <table
        {...props}
        className={cn("my-3 w-full border-collapse text-sm", className)}
      />
    );
  },
  tbody({ className, ...props }) {
    return <tbody {...props} className={cn("align-top", className)} />;
  },
  td({ className, ...props }) {
    return (
      <td
        {...props}
        className={cn("border border-border px-3 py-2", className)}
      />
    );
  },
  th({ className, ...props }) {
    return (
      <th
        {...props}
        className={cn(
          "border border-border px-3 py-2 text-left font-semibold",
          className,
        )}
      />
    );
  },
  thead({ className, ...props }) {
    return <thead {...props} className={cn("align-bottom", className)} />;
  },
  ul({ className, ...props }) {
    return <ul {...props} className={cn("my-2 ml-4 list-disc", className)} />;
  },
};

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <div className="markdown-content text-sm text-foreground">
      <ReactMarkdown
        components={markdownComponents}
        remarkPlugins={[remarkGfm]}
        skipHtml
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
