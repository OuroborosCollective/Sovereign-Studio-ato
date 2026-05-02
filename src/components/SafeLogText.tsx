import React from 'react';

interface SafeLogTextProps {
  text: string;
}

/**
 * Safely renders log text by escaping all HTML except for a specific whitelist:
 * <b>, <br>, <code>
 */
export const SafeLogText: React.FC<SafeLogTextProps> = ({ text }) => {
  if (!text) return null;

  // This regex matches our whitelisted tags and captures them.
  // It specifically looks for <b>, </b>, <br>, <br/>, <code>, </code>
  const parts = text.split(/(<\/?[b]>|<br\s*\/?>|<\/?code>)/gi);

  const stack: { type: 'root' | 'b' | 'code', children: React.ReactNode[] }[] = [
    { type: 'root', children: [] }
  ];

  parts.forEach((part, index) => {
    if (!part) return;
    const lowerPart = part.toLowerCase();
    const current = stack[stack.length - 1];

    if (lowerPart === '<b>') {
      stack.push({ type: 'b', children: [] });
    } else if (lowerPart === '</b>') {
      if (stack.length > 1 && stack[stack.length - 1].type === 'b') {
        const closed = stack.pop()!;
        stack[stack.length - 1].children.push(<b key={index}>{closed.children}</b>);
      } else {
        current.children.push(part); // Treat as text if mismatched
      }
    } else if (lowerPart === '<code>') {
      stack.push({ type: 'code', children: [] });
    } else if (lowerPart === '</code>') {
      if (stack.length > 1 && stack[stack.length - 1].type === 'code') {
        const closed = stack.pop()!;
        stack[stack.length - 1].children.push(<code key={index}>{closed.children}</code>);
      } else {
        current.children.push(part);
      }
    } else if (lowerPart.startsWith('<br')) {
      current.children.push(<br key={index} />);
    } else {
      // Plain text - React will escape this automatically
      current.children.push(part);
    }
  });

  // Close remaining tags safely
  while (stack.length > 1) {
    const closed = stack.pop()!;
    const Tag = closed.type as 'b' | 'code';
    stack[stack.length - 1].children.push(React.createElement(Tag, { key: `unclosed-${stack.length}` }, closed.children));
  }

  return <>{stack[0].children}</>;
};
