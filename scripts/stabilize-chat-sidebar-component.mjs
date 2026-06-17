#!/usr/bin/env node
import { readFileSync, writeFileSync } from 'node:fs';

const file = 'src/features/product/components/ChatSidebar.tsx';
let source = readFileSync(file, 'utf8');
let changed = false;

function once(from, to) {
  if (source.includes(to)) return;
  if (!source.includes(from)) throw new Error(`Expected block not found in ${file}`);
  source = source.replace(from, to);
  changed = true;
}

once(
  "import React, { useState, useRef, useEffect } from 'react';",
  "import React, { useMemo, useState, useRef, useEffect } from 'react';",
);

once(
  "import { ChatMessage, Suggestion } from '../types';",
  "import { ChatMessage, Suggestion } from '../types';\nimport {\n  CHAT_SIDEBAR_MAX_INPUT,\n  canSubmitChatMessage,\n  normalizeChatInput,\n  normalizeChatMessages,\n  normalizeSuggestions,\n} from '../runtime/chatSidebarRuntime';",
);

once(
  "  const [inputValue, setInputValue] = useState('');\n  const messagesEndRef = useRef<HTMLDivElement>(null);\n  const inputRef = useRef<HTMLInputElement>(null);",
  "  const [inputValue, setInputValue] = useState('');\n  const messagesEndRef = useRef<HTMLDivElement>(null);\n  const inputRef = useRef<HTMLInputElement>(null);\n  const safeMessages = useMemo(() => normalizeChatMessages(chatMessages), [chatMessages]);\n  const safeSuggestions = useMemo(() => normalizeSuggestions(suggestions), [suggestions]);\n  const normalizedInput = normalizeChatInput(inputValue);\n  const canSubmit = canSubmitChatMessage(inputValue);",
);

once("  }, [chatMessages]);", "  }, [safeMessages]);");

once(
  "    if (inputValue.trim()) {\n      onSendMessage(inputValue.trim());\n      setInputValue('');\n    }",
  "    if (!canSubmit) return;\n    onSendMessage(normalizedInput);\n    setInputValue('');",
);

once(
  "        {chatMessages.map((msg) => (",
  "        {safeMessages.map((msg) => (",
);

once("      {suggestions.length > 0 && (", "      {safeSuggestions.length > 0 && (");
once("            {suggestions.map((suggestion) => (", "            {safeSuggestions.map((suggestion) => (");

once(
  "            value={inputValue}\n            onChange={(e) => setInputValue(e.target.value)}\n            placeholder=\"Frage oder Feedback...\"",
  "            value={inputValue}\n            onChange={(e) => setInputValue(e.target.value)}\n            placeholder=\"Frage oder Feedback...\"\n            aria-label=\"Chat Nachricht\"\n            maxLength={CHAT_SIDEBAR_MAX_INPUT}",
);

once(
  "            type=\"submit\"\n            disabled={!inputValue.trim()}",
  "            type=\"submit\"\n            aria-label=\"Nachricht senden\"\n            disabled={!canSubmit}",
);

if (changed) writeFileSync(file, source);
console.log(`${file}: ${changed ? 'patched' : 'already patched'}`);
