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

/**
 * Sanitizes URLs to prevent XSS (e.g., javascript: protocols)
 */
function sanitizeUrl(url: string): string {
  const trimmed = url.trim().toLowerCase();
  if (trimmed.startsWith('javascript:')) {
    return 'about:blank';
  }
  return url;
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
    const patterns = [
      { regex: /\*\*([^*\n]+)\*\*/, type: 'bold' as const },
      { regex: /`([^`\n]+)`/, type: 'code' as const },
      { regex: /\[([^\]\n]+)\]\(([^)\n]+)\)/, type: 'link' as const, urlGroup: 2 },
    ];

    let earliestMatch: { match: RegExpExecArray; type: string; url?: string } | null = null;
    let earliestIndex = Infinity;

    for (const p of patterns) {
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

function tokenizeContent(input: string): Segment[] {
  const segments: Segment[] = [];
  const lines = input.split('\n');
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const codeBlockMatch = line.match(/^```(\w*)$/);

    if (codeBlockMatch) {
      const language = codeBlockMatch[1] || 'text';
      const codeLines: string[] = [];
      i += 1;

      while (i < lines.length) {
        if (lines[i].match(/^```$/)) {
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

    pushInlineSegments(line, segments);
    if (i < lines.length - 1) {
      segments.push({ type: 'linebreak' });
    }
    i += 1;
  }

  return segments;
}

/**
 * Copy code to clipboard with feedback
 */
function CopyButton({ code }: { code: string }) {
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

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={copied ? 'Copied!' : 'Copy code'}
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
      {copied ? '✓ Kopiert' : 'Kopieren'}
    </button>
  );
}

/**
 * Code block with scroll and copy
 */
function CodeBlockView({ language, code }: { language: string; code: string }) {
  return (
    <div style={{ margin: '8px 0', borderRadius: 8, overflow: 'hidden', border: `1px solid ${C.border}` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 12px', background: C.codeBg, borderBottom: `1px solid ${C.border}` }}>
        <span style={{ fontSize: 11, color: C.textSub, fontFamily: 'monospace' }}>
          {language}
        </span>
        <CopyButton code={code} />
      </div>
      <pre style={{ margin: 0, padding: '12px', background: C.codeBg, overflowX: 'auto', fontSize: 12, fontFamily: 'monospace', color: C.text, lineHeight: 1.5, maxHeight: 300 }}>
        <code>{code}</code>
      </pre>
    </div>
  );
}

/**
 * Render a text segment with inline formatting
 */
function renderTextSegment(seg: Segment, key: number): React.ReactNode {
  switch (seg.type) {
    case 'bold':
      return <strong key={key} style={{ color: C.text, fontWeight: 600 }}>{seg.content}</strong>;
    case 'code':
      return (
        <code key={key} style={{ background: C.codeBg, padding: '2px 6px', borderRadius: 4, fontSize: '0.9em', color: C.accent, fontFamily: 'monospace' }}>
          {seg.content}
        </code>
      );
    case 'link':
      return (
        <a key={key} href={sanitizeUrl(seg.url)} target="_blank" rel="noopener noreferrer" style={{ color: C.accent, textDecoration: 'underline' }}>
          {seg.content}
        </a>
      );
    case 'text':
      return <span key={key}>{seg.content}</span>;
    case 'linebreak':
      return <br key={key} />;
    default:
      return null;
  }
}

/**
 * ChatMarkdown - main export
 */
export const ChatMarkdown: React.FC<ChatMarkdownProps> = ({ content }) => {
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
        return renderTextSegment(seg, index);
      })}
    </div>
  );
};

export default ChatMarkdown;
