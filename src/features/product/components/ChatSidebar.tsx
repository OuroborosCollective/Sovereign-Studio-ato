import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Download, Trash2, Send, Sparkles, CheckCircle, AlertTriangle, Lightbulb, Loader2 } from 'lucide-react';
import { ChatMessage, Suggestion } from '../types';
import {
  canSubmitChatMessage,
  chatSidebarSummary,
  describeSuggestionAction,
  normalizeChatInput,
  normalizeChatMessages,
  normalizeSuggestions,
} from '../runtime/chatSidebarRuntime';

interface ChatSidebarProps {
  chatMessages: ChatMessage[];
  suggestions: Suggestion[];
  isAnalyzing: boolean;
  onSendMessage: (message: string) => void;
  onAcceptSuggestion: (suggestionId: string) => void;
  onDownloadPackage: () => void;
  onClearChat: () => void;
}

export const ChatSidebar: React.FC<ChatSidebarProps> = ({
  chatMessages,
  suggestions,
  isAnalyzing,
  onSendMessage,
  onAcceptSuggestion,
  onDownloadPackage,
  onClearChat
}) => {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Performance: Memoize normalization to prevent redundant processing on every keystroke
  const safeMessages = useMemo(() => normalizeChatMessages(chatMessages), [chatMessages]);
  const safeSuggestions = useMemo(() => normalizeSuggestions(suggestions), [suggestions]);
  const summary = useMemo(() => chatSidebarSummary(safeMessages, safeSuggestions), [safeMessages, safeSuggestions]);

  const normalizedInput = normalizeChatInput(inputValue);
  const canSubmit = canSubmitChatMessage(inputValue);

  useEffect(() => {
    try {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    } catch {
      // scrollIntoView not supported in test environment
    }
  }, [safeMessages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (canSubmit) {
      onSendMessage(normalizedInput);
      setInputValue('');
    }
  };

  const handleSuggestionClick = (suggestion: Suggestion) => {
    if (!suggestion.accepted) {
      onAcceptSuggestion(suggestion.id);
    }
  };

  const getSuggestionIcon = (type: string) => {
    switch (type) {
      case 'error': return <AlertTriangle size={14} className="text-red-500" aria-hidden="true" />;
      case 'feature': return <Sparkles size={14} className="text-indigo-500" aria-hidden="true" />;
      case 'improvement': return <Lightbulb size={14} className="text-yellow-500" aria-hidden="true" />;
      default: return <Sparkles size={14} className="text-indigo-500" aria-hidden="true" />;
    }
  };

  const getSuggestionStyle = (type: string, accepted: boolean | undefined) => {
    if (accepted) return 'bg-emerald-50 border-emerald-200 opacity-60';
    switch (type) {
      case 'error': return 'bg-red-50 border-red-300 hover:bg-red-100';
      case 'feature': return 'bg-indigo-50 border-indigo-300 hover:bg-indigo-100';
      case 'improvement': return 'bg-yellow-50 border-yellow-300 hover:bg-yellow-100';
      default: return 'bg-stone-50 border-stone-300 hover:bg-stone-100';
    }
  };

  const getPriorityBadge = (priority: string) => {
    switch (priority) {
      case 'high': return <span className="text-[8px] px-1 py-0.5 bg-red-500 text-white rounded">WICHTIG</span>;
      case 'medium': return <span className="text-[8px] px-1 py-0.5 bg-yellow-500 text-white rounded">MEDIUM</span>;
      default: return null;
    }
  };

  return (
    <section className="w-full md:w-[380px] shrink-0 border-l border-stone-200 bg-white flex flex-col" aria-label="Chat und Vorschläge" data-testid="chat-sidebar" data-summary={summary}>
      <div className="p-3 bg-stone-50 border-b border-stone-200 text-[11px] font-bold text-stone-800 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-indigo-600" aria-hidden="true" />
          <span>Chat & Vorschläge</span>
          {isAnalyzing && <Loader2 size={12} className="animate-spin text-indigo-600" aria-label="Analyse läuft" />}
        </div>
        <button type="button" onClick={onClearChat} aria-label="Chat leeren" className="text-[9px] text-stone-400 hover:text-stone-600 flex items-center gap-1">
          <Trash2 size={12} aria-hidden="true" /> Leeren
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-gradient-to-b from-stone-50 to-white" aria-label="Chat Nachrichten">
        {safeMessages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-[11px] leading-relaxed whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-indigo-600 text-white rounded-tr-sm'
                  : msg.role === 'system'
                  ? 'bg-stone-100 text-stone-500 italic border border-stone-200'
                  : 'bg-white text-stone-800 border border-stone-200 rounded-tl-sm shadow-sm'
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {safeSuggestions.length > 0 && (
        <div className="border-t border-stone-200 bg-stone-50 p-3 max-h-[200px] overflow-y-auto" aria-label="Vorschläge" data-testid="chat-suggestions">
          <div className="text-[10px] font-bold text-stone-600 uppercase mb-2 flex items-center gap-1">
            <Sparkles size={12} className="text-indigo-600" aria-hidden="true" />
            Vorschläge
          </div>
          <div className="space-y-2">
            {safeSuggestions.map((suggestion) => (
              <button
                key={suggestion.id}
                type="button"
                onClick={() => handleSuggestionClick(suggestion)}
                disabled={suggestion.accepted}
                aria-label={describeSuggestionAction(suggestion)}
                aria-pressed={Boolean(suggestion.accepted)}
                className={`w-full text-left p-3 rounded-xl border transition-all duration-200 ${getSuggestionStyle(suggestion.type, suggestion.accepted)} ${!suggestion.accepted ? 'cursor-pointer active:scale-[0.98]' : 'cursor-default'}`}
              >
                <div className="flex items-start gap-2">
                  {getSuggestionIcon(suggestion.type)}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[11px] font-bold text-stone-800 truncate">
                        {suggestion.accepted ? '✓ ' : ''}{suggestion.title}
                      </span>
                      {getPriorityBadge(suggestion.priority)}
                    </div>
                    <p className="text-[10px] text-stone-600 line-clamp-2">{suggestion.description}</p>
                  </div>
                  {!suggestion.accepted && (
                    <CheckCircle size={16} className="text-emerald-600 shrink-0 opacity-0 group-hover:opacity-100" aria-hidden="true" />
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="border-t border-stone-200 p-3 bg-white shrink-0">
        <form onSubmit={handleSubmit} className="flex gap-2" aria-label="Chat Nachricht senden">
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Frage oder Feedback..."
            aria-label="Chat Nachricht"
            className="flex-1 text-[11px] p-2 border border-stone-300 rounded-lg focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-200"
          />
          <button
            type="submit"
            aria-label="Nachricht senden"
            disabled={!canSubmit}
            className="px-3 py-2 bg-indigo-600 disabled:bg-stone-300 text-white rounded-lg hover:bg-indigo-700 transition-colors"
          >
            <Send size={14} aria-hidden="true" />
          </button>
        </form>
        <button
          type="button"
          onClick={onDownloadPackage}
          aria-label="Verlauf sichern"
          className="w-full mt-2 bg-stone-900 text-white py-2 rounded-lg text-[10px] font-black uppercase flex items-center justify-center gap-2 hover:bg-black transition-colors"
        >
          <Download size={13} aria-hidden="true" /> Verlauf sichern
        </button>
      </div>
    </section>
  );
};
