/**
 * ChatMarkdown - Lightweight markdown/code rendering for assistant chat bubbles
 * 
 * Renders assistant messages with:
 * - Fenced code sections as scrollable monospace blocks with copy control
 * - Simple bold text
 * - Inline technical terms
 * - Handles malformed input without crashing
 * 
 * No large formatting dependencies, no raw HTML rendering.
 */

import React, { useCallback, useState } from 'react';

export interface ChatMarkdownProps {
  content: string;
}

const C = {
  text:      '#cdd9e5',
  textSub:   '#768390',
  border:    '#232d3a',
  surface:   '#161c24',
  accent:    '#00d9b1',
  codeBg:    '#0e1116',
};

interface CodeBlock {
  language: string;
  code: string;
  startIndex: number;
  endIndex: number;
}

/**
 * Parse content into code blocks and text segments
 */
function parseContent(content: string): Array<{ type: 'text' | 'code'; content: string; language?: string }> {
  const segments: Array<{ type: 'text' | 'code'; content: string; language?: string }> = [];
  
  // Match fenced code blocks: ```language\ncode\n```
  const codeBlockRegex = /```(\w*)\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    // Add text before code block
    if (match.index > lastIndex) {
      const text = content.slice(lastIndex, match.index);
      if (text.trim()) {
        segments.push({ type: 'text', content: text });
      }
    }
    
    // Add code block
    segments.push({
      type: 'code',
      language: match[1] || 'text',
      content: match[2].trim(),
    });
    
    lastIndex = match.index + match[0].length;
  }

  // Add remaining text
  if (lastIndex < content.length) {
    const text = content.slice(lastIndex);
    if (text.trim()) {
      segments.push({ type: 'text', content: text });
    }
  }

  // If no segments, treat entire content as text
  if (segments.length === 0 && content.trim()) {
    segments.push({ type: 'text', content: content });
  }

  return segments;
}

/**
 * Render inline markdown: bold and inline code
 */
function renderInlineText(text: string): React.ReactNode {
  // Handle bold: **text**
  const boldRegex = /\*\*([^*\n]+)\*\*/g;
  // Handle inline code: `code`
  const inlineCodeRegex = /`([^`\n]+)`/g;
  
  // Process in order
  let result: React.ReactNode[] = [];
  let lastIndex = 0;
  
  // Combine patterns and sort by index
  const patterns: Array<{ regex: RegExp; type: 'bold' | 'inline-code'; handler: (match: RegExpExecArray) => React.ReactNode }> = [
    {
      regex: /\*\*([^*\n]+)\*\*/g,
      type: 'bold',
      handler: (m) => <strong key={`bold-${m.index}`} style={{ color: C.text, fontWeight: 600 }}>{m[1]}</strong>,
    },
    {
      regex: /`([^`\n]+)`/g,
      type: 'inline-code',
      handler: (m) => (
        <code
          key={`code-${m.index}`}
          style={{
            background: C.codeBg,
            padding: '2px 6px',
            borderRadius: 4,
            fontSize: '0.9em',
            color: C.accent,
            fontFamily: 'monospace',
          }}
        >
          {m[1]}
        </code>
      ),
    },
  ];

  // Simple approach: iterate and replace
  let processed = text;
  const replacements: Array<{ index: number; length: number; node: React.ReactNode }> = [];

  for (const pattern of patterns) {
    pattern.regex.lastIndex = 0;
    let match;
    while ((match = pattern.regex.exec(text)) !== null) {
      replacements.push({
        index: match.index,
        length: match[0].length,
        node: pattern.handler(match),
      });
    }
  }

  // Sort by index descending to process from end to start
  replacements.sort((a, b) => b.index - a.index);

  // Build result
  let finalText = text;
  for (const rep of replacements) {
    const before = finalText.slice(0, rep.index);
    const after = finalText.slice(rep.index + rep.length);
    finalText = before + '___PLACEHOLDER_' + (result.length) + '___' + after;
  }

  // Replace placeholders
  for (let i = replacements.length - 1; i >= 0; i--) {
    finalText = finalText.replace(`___PLACEHOLDER_${i}___`, '');
  }

  // Split remaining text by newlines and add
  const parts = finalText.split('\n');
  const textResult: React.ReactNode[] = [];
  for (const part of parts) {
    if (part.trim()) textResult.push(part);
  }
  
  return [...textResult, ...result];
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
      // Clipboard not available, silently fail
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
    <div
      style={{
        margin: '8px 0',
        borderRadius: 8,
        overflow: 'hidden',
        border: `1px solid ${C.border}`,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '6px 12px',
          background: C.codeBg,
          borderBottom: `1px solid ${C.border}`,
        }}
      >
        <span
          style={{
            fontSize: 11,
            color: C.textSub,
            fontFamily: 'monospace',
          }}
        >
          {language || 'code'}
        </span>
        <CopyButton code={code} />
      </div>
      
      {/* Code content */}
      <pre
        style={{
          margin: 0,
          padding: '12px',
          background: C.codeBg,
          overflowX: 'auto',
          fontSize: 12,
          fontFamily: 'monospace',
          color: C.text,
          lineHeight: 1.5,
          maxHeight: 300,
        }}
      >
        <code>{code}</code>
      </pre>
    </div>
  );
}

/**
 * ChatMarkdown - main export
 */
export const ChatMarkdown: React.FC<ChatMarkdownProps> = ({ content }) => {
  // Guard against non-string input
  if (typeof content !== 'string') {
    return <span>{String(content)}</span>;
  }

  const segments = parseContent(content);

  return (
    <div
      style={{
        fontSize: 14,
        lineHeight: 1.6,
        color: C.text,
        wordBreak: 'break-word',
        overflowWrap: 'break-word',
      }}
    >
      {segments.map((segment, index) => {
        if (segment.type === 'code') {
          return (
            <CodeBlockView
              key={index}
              language={segment.language || 'text'}
              code={segment.content}
            />
          );
        }
        
        return (
          <span
            key={index}
            style={{ whiteSpace: 'pre-wrap' }}
          >
            {renderInlineText(segment.content)}
          </span>
        );
      })}
    </div>
  );
};

export default ChatMarkdown;
