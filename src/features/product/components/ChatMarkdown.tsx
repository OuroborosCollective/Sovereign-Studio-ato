/**
 * ChatMarkdown - Lightweight markdown/code rendering for assistant chat bubbles
 * 
 * Renders assistant messages with:
 * - Fenced code sections as scrollable monospace blocks with copy control
 * - Bold text: **bold**
 * - Inline code: `code`
 * - Links: [text](url)
 * 
 * No large formatting dependencies, no raw HTML rendering.
 */

import React, { useCallback, useState, useMemo } from 'react';

export interface ChatMarkdownProps {
  content: string;
}

const C = {
  text:      '#cdd9e5',
  textSub:   '#768390',
  border:    '#232d3a',
  codeBg:    '#0e1116',
  accent:    '#00d9b1',
};

// Hoisted regex patterns to avoid redundant re-instantiation during high-frequency UI updates.
const BOLD_REGEX = /\*\*([^*\n]+)\*\*/;
const CODE_REGEX = /`([^`\n]+)`/;
const LINK_REGEX = /\[([^\]\n]+)\]\(([^)\n]+)\)/;
const CODE_BLOCK_START_REGEX = /^```(\w*)$/;
const CODE_BLOCK_END_REGEX = /^```$/;

// Hoisted patterns array to reduce garbage collection pressure in the high-frequency render path.
const INLINE_PATTERNS = [
  { regex: BOLD_REGEX, type: 'bold' as const },
  { regex: CODE_REGEX, type: 'code' as const },
  { regex: LINK_REGEX, type: 'link' as const, urlGroup: 2 },
];

/**
 * Sanitizes URLs to prevent XSS (e.g., javascript: protocols) using a strict whitelist.
 */
function sanitizeUrl(url: string): string {
  if (!url) return 'about:blank';

  // Normalize by stripping whitespaces, control characters, percent encodings, and JS escape sequences
  let sanitized = url.trim().toLowerCase();

  // Remove actual control characters and whitespace
  sanitized = sanitized.replace(/[\x00-\x20\x7F-\x9F\s]/g, '');

  // Remove percent-encoded control characters and whitespaces (e.g. %00, %09, %0a, %0d, %20)
  sanitized = sanitized.replace(/%(00|09|0a|0d|20|7f)/gi, '');

  // Remove literal javascript escape sequences (e.g. \x00, \t, \n, \r)
  sanitized = sanitized.replace(/\\(x00|x09|x0a|x0d|x7f|t|n|r)/gi, '');

  // Remove HTML entity representations of control characters/whitespace
  sanitized = sanitized.replace(/&#(x00|x09|x0a|x0d|x7f|00|09|10|13|127);/gi, '');

  // Handle relative/anchor/local paths
  if (
    sanitized.startsWith('/') ||
    sanitized.startsWith('#') ||
    sanitized.startsWith('./') ||
    sanitized.startsWith('../')
  ) {
    return url;
  }

  // Use a strict whitelist of protocols: http, https, mailto, tel
  const match = sanitized.match(/^([a-z0-9+.-]+):/i);
  if (!match) {
    // If no protocol is specified but it's not a known relative path, default to safe
    return url;
  }

  const protocol = match[1];
  if (protocol === 'http' || protocol === 'https' || protocol === 'mailto' || protocol === 'tel') {
    return url;
  }

  return 'about:blank';
}

/**
 * Parse content into segments (code blocks and inline text with formatting)
 */
type Segment = 
  | { type: 'text'; content: string }
  | { type: 'bold'; content: string }
  | { type: 'code'; content: string }
  | { type: 'link'; content: string; url: string }
  | { type: 'codeblock'; language: string; content: string }
  | { type: 'linebreak' };

function pushInlineSegments(line: string, segments: Segment[]): void {
  let remaining = line;

  while (remaining.length > 0) {
    let earliestMatch: { match: RegExpExecArray; type: string; url?: string } | null = null;
    let earliestIndex = Infinity;

    for (const p of INLINE_PATTERNS) {
      p.regex.lastIndex = 0;
      const m = p.regex.exec(remaining);
      if (m && m.index < earliestIndex) {
        earliestIndex = m.index;
        earliestMatch = { match: m, type: p.type, url: 'urlGroup' in p ? m[p.urlGroup!] : undefined };
      }
    }

    if (earliestMatch && earliestIndex < Infinity) {
      if (earliestIndex > 0) {
        segments.push({ type: 'text', content: remaining.slice(0, earliestIndex) });
      }
      const segType = earliestMatch.type as 'bold' | 'code' | 'link';
      if (segType === 'link') {
        segments.push({ type: 'link', content: earliestMatch.match[1], url: earliestMatch.url! });
      } else {
        segments.push({ type: segType, content: earliestMatch.match[1] });
      }
      remaining = remaining.slice(earliestIndex + earliestMatch.match[0].length);
    } else {
      segments.push({ type: 'text', content: remaining });
      break;
    }
  }
}

// Bounded line-level cache for parsed inline segments (max 1000 items)
export const inlineLineCache = new Map<string, Segment[]>();

// 1-slot tokenizer cache for whole-text evaluations
let lastTokenizeInput: string | null = null;
let lastTokenizeResult: Segment[] | null = null;

// Helper function to clear caches during unit/performance testing
export function clearChatMarkdownCaches(): void {
  inlineLineCache.clear();
  lastTokenizeInput = null;
  lastTokenizeResult = null;
}

function getInlineSegments(line: string): Segment[] {
  const cached = inlineLineCache.get(line);
  if (cached) return cached;

  const segments: Segment[] = [];
  pushInlineSegments(line, segments);

  if (inlineLineCache.size >= 1000) {
    inlineLineCache.clear();
  }
  inlineLineCache.set(line, segments);
  return segments;
}

function tokenizeContent(input: string): Segment[] {
  if (input === lastTokenizeInput && lastTokenizeResult) {
    return lastTokenizeResult;
  }

  const segments: Segment[] = [];
  const lines = input.split('\n');
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const codeBlockMatch = line.match(CODE_BLOCK_START_REGEX);

    if (codeBlockMatch) {
      const language = codeBlockMatch[1] || 'text';
      const codeLines: string[] = [];
      i += 1;

      while (i < lines.length) {
        if (CODE_BLOCK_END_REGEX.test(lines[i])) {
          i += 1;
          break;
        }
        codeLines.push(lines[i]);
        i += 1;
      }

      segments.push({ type: 'codeblock', language, content: codeLines.join('\n') });
      if (i < lines.length) {
        segments.push({ type: 'linebreak' });
      }
      continue;
    }

    segments.push(...getInlineSegments(line));
    if (i < lines.length - 1) {
      segments.push({ type: 'linebreak' });
    }
    i += 1;
  }

  lastTokenizeInput = input;
  lastTokenizeResult = segments;
  return segments;
}

/**
 * Copy code to clipboard with feedback
 */
const CopyButton = React.memo(function CopyButton({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard not available
    }
  }, [code]);

  const label = copied ? 'Copied!' : 'Copy code';

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={label}
      title={label}
      style={{
        padding: '4px 8px',
        borderRadius: 4,
        background: copied ? '#34d39920' : '#232d3a',
        border: `1px solid ${copied ? '#34d39940' : '#232d3a'}`,
        color: copied ? '#34d399' : '#768390',
        fontSize: 11,
        cursor: 'pointer',
        transition: 'all 0.15s ease',
      }}
    >
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  );
});

/**
 * Code block with scroll and copy
 */
const CodeBlockView = React.memo(function CodeBlockView({ language, code }: { language: string; code: string }) {
  const ariaLabel = `Code block (${language})`;
  return (
    <div style={{ margin: '8px 0', borderRadius: 8, overflow: 'hidden', border: `1px solid ${C.border}` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 12px', background: C.codeBg, borderBottom: `1px solid ${C.border}` }}>
        <span
          style={{ fontSize: 11, color: C.textSub, fontFamily: 'monospace' }}
          title={`Language: ${language}`}
        >
          {language}
        </span>
        <CopyButton code={code} />
      </div>
      <pre
        tabIndex={0}
        role="region"
        aria-label={ariaLabel}
        style={{ margin: 0, padding: '12px', background: C.codeBg, overflowX: 'auto', fontSize: 12, fontFamily: 'monospace', color: C.text, lineHeight: 1.5, maxHeight: 300 }}
      >
        <code>{code}</code>
      </pre>
    </div>
  );
});

/**
 * Render a text segment with inline formatting
 */
const TextSegmentView = React.memo(function TextSegmentView({ seg }: { seg: Segment }) {
  switch (seg.type) {
    case 'bold':
      return <strong style={{ color: C.text, fontWeight: 600 }}>{seg.content}</strong>;
    case 'code':
      return (
        <code style={{ background: C.codeBg, padding: '2px 6px', borderRadius: 4, fontSize: '0.9em', color: C.accent, fontFamily: 'monospace' }}>
          {seg.content}
        </code>
      );
    case 'link':
      return (
        <a href={sanitizeUrl(seg.url)} target="_blank" rel="noopener noreferrer" style={{ color: C.accent, textDecoration: 'underline' }}>
          {seg.content}
        </a>
      );
    case 'text':
      return <span>{seg.content}</span>;
    case 'linebreak':
      return <br />;
    default:
      return null;
  }
});

/**
 * ChatMarkdown - main export
 */
export const ChatMarkdown = React.memo(function ChatMarkdown({ content }: ChatMarkdownProps) {
  if (typeof content !== 'string') {
    return <span>{String(content)}</span>;
  }

  const segments = useMemo(() => tokenizeContent(content), [content]);

  return (
    <div style={{ fontSize: 14, lineHeight: 1.6, color: C.text, wordBreak: 'break-word', overflowWrap: 'break-word' }}>
      {segments.map((seg, index) => {
        if (seg.type === 'codeblock') {
          return <CodeBlockView key={index} language={seg.language} code={seg.content} />;
        }
        return <TextSegmentView key={index} seg={seg} />;
      })}
    </div>
  );
});

export default ChatMarkdown;
