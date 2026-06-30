import React, { useEffect, useMemo, useState } from 'react';
import { ChatMarkdown } from './ChatMarkdown';
import {
  DEFAULT_ASSISTANT_RESPONSE_PACING,
  createAssistantResponsePacingState,
  initialAssistantResponseVisibleWords,
  nextAssistantResponseVisibleWords,
} from '../runtime/assistantResponsePacingRuntime';

export interface PacedChatTextProps {
  readonly content: string;
  readonly enabled?: boolean;
}

const CARET_STYLE: React.CSSProperties = {
  color: '#00d9b1',
  display: 'inline-block',
  marginLeft: 2,
  animation: 'sdc-typing-caret 0.9s steps(2, start) infinite',
};

export function PacedChatText({ content, enabled = true }: PacedChatTextProps) {
  const config = useMemo(() => ({ ...DEFAULT_ASSISTANT_RESPONSE_PACING, enabled }), [enabled]);
  const [visibleWords, setVisibleWords] = useState(() => initialAssistantResponseVisibleWords(content, config));

  useEffect(() => {
    setVisibleWords(initialAssistantResponseVisibleWords(content, config));

    const handle = window.setInterval(() => {
      setVisibleWords((current) => nextAssistantResponseVisibleWords(current, content, config));
    }, 55);

    return () => window.clearInterval(handle);
  }, [config, content]);

  const state = createAssistantResponsePacingState(content, visibleWords, config);

  return (
    <span aria-live={state.shouldPace ? 'polite' : undefined} data-testid="paced-chat-text">
      <ChatMarkdown content={state.visibleText} />
      {state.shouldPace && !state.complete ? <span aria-hidden="true" style={CARET_STYLE}>▍</span> : null}
    </span>
  );
}

export default PacedChatText;
