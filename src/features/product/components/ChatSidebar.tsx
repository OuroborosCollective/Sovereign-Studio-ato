import React, { useState, useRef, useEffect, useMemo } from 'react';
import { 
  Download, Trash2, Send, Sparkles, CheckCircle, AlertTriangle, 
  Lightbulb, Loader2, CircleX, Bot, User, ChevronDown, Zap,
  Sparkle, Brain, Globe, Shield
} from 'lucide-react';
import { ChatMessage, Suggestion } from '../types';
import {
  canSubmitChatMessage,
  chatSidebarSummary,
  describeSuggestionAction,
  normalizeChatInput,
  normalizeChatMessages,
  normalizeSuggestions,
} from '../runtime/chatSidebarRuntime';

// Model info interface
export interface LlmModelInfo {
  id: string;
  label: string;
  provider: string;
  kind: string;
  icon?: React.ReactNode;
}

interface ChatSidebarProps {
  chatMessages: ChatMessage[];
  suggestions: Suggestion[];
  isAnalyzing: boolean;
  onSendMessage: (message: string) => void;
  onAcceptSuggestion: (suggestionId: string) => void;
  onDownloadPackage: () => void;
  onClearChat: () => void;
  /** Auto-detected available models from LLM adapters */
  availableModels?: LlmModelInfo[];
  /** Currently selected model ID */
  selectedModel?: string;
  /** Callback when user selects a model */
  onModelChange?: (modelId: string) => void;
}

// Kaomoji thinking states
const THINKING_FRAMES = ['( ^ω^)', '(^_^)', '(^‿^)', '(^o^)', '(^・ω・^)'];

export const ChatSidebar: React.FC<ChatSidebarProps> = ({
  chatMessages,
  suggestions,
  isAnalyzing,
  onSendMessage,
  onAcceptSuggestion,
  onDownloadPackage,
  onClearChat,
  availableModels = [],
  selectedModel,
  onModelChange,
}) => {
  const [inputValue, setInputValue] = useState('');
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [thinkingFrame, setThinkingFrame] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const modelPickerRef = useRef<HTMLDivElement>(null);

  // Memoize derived state
  const safeMessages = useMemo(() => normalizeChatMessages(chatMessages), [chatMessages]);
  const safeSuggestions = useMemo(() => normalizeSuggestions(suggestions), [suggestions]);
  const summary = useMemo(() => chatSidebarSummary(safeMessages, safeSuggestions), [safeMessages, safeSuggestions]);

  const normalizedInput = normalizeChatInput(inputValue);
  const canSubmit = canSubmitChatMessage(inputValue);

  // Animate thinking frames
  useEffect(() => {
    if (!isAnalyzing) {
      setThinkingFrame(0);
      return;
    }
    const interval = setInterval(() => {
      setThinkingFrame(f => (f + 1) % THINKING_FRAMES.length);
    }, 800);
    return () => clearInterval(interval);
  }, [isAnalyzing]);

  // Auto-scroll to bottom
  useEffect(() => {
    try {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    } catch {
      // scrollIntoView not supported in test environment
    }
  }, [safeMessages, isAnalyzing]);

  // Close model picker on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (modelPickerRef.current && !modelPickerRef.current.contains(e.target as Node)) {
        setShowModelPicker(false);
      }
    };
    if (showModelPicker) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showModelPicker]);

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

  const getModelIcon = (kind: string) => {
    switch (kind) {
      case 'user-key': return <Shield size={12} className="text-emerald-400" />;
      case 'no-key': return <Zap size={12} className="text-amber-400" />;
      case 'opt-in': return <Sparkle size={12} className="text-purple-400" />;
      default: return <Brain size={12} className="text-slate-400" />;
    }
  };

  const currentModel = availableModels.find(m => m.id === selectedModel) || availableModels[0];

  return (
    <section 
      className="w-full md:w-[420px] shrink-0 flex flex-col bg-slate-950 border-l border-cyan-500/20" 
      aria-label="AI Chat" 
      data-testid="chat-sidebar" 
      data-summary={summary}
    >
      {/* Header */}
      <header className="px-4 py-3 border-b border-cyan-500/15 bg-slate-900/50 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-cyan-500/20 to-indigo-500/20 border border-cyan-500/30 flex items-center justify-center">
              <Bot size={16} className="text-cyan-400" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-100">AI Assistant</h2>
              <p className="text-[10px] text-slate-500">Natural Language Interface</p>
            </div>
          </div>
          
          {/* Model Selector */}
          {availableModels.length > 0 && (
            <div className="relative" ref={modelPickerRef}>
              <button
                type="button"
                onClick={() => setShowModelPicker(!showModelPicker)}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-800/80 border border-cyan-500/20 hover:border-cyan-500/40 transition-colors text-xs"
              >
                <Globe size={12} className="text-cyan-400" />
                <span className="text-slate-300 max-w-[100px] truncate">
                  {currentModel?.label || 'Select Model'}
                </span>
                <ChevronDown size={12} className="text-slate-500" />
              </button>
              
              {showModelPicker && (
                <div className="absolute right-0 top-full mt-2 w-64 bg-slate-900 border border-cyan-500/30 rounded-xl shadow-2xl shadow-cyan-950/50 z-50 overflow-hidden">
                  <div className="px-3 py-2 border-b border-cyan-500/15">
                    <span className="text-[10px] text-cyan-400 uppercase tracking-widest font-bold">
                      Available Models
                    </span>
                  </div>
                  <div className="py-1 max-h-64 overflow-y-auto">
                    {availableModels.map((model) => (
                      <button
                        key={model.id}
                        type="button"
                        onClick={() => {
                          onModelChange?.(model.id);
                          setShowModelPicker(false);
                        }}
                        className={`w-full px-3 py-2.5 flex items-center gap-3 hover:bg-slate-800/80 transition-colors ${
                          model.id === selectedModel ? 'bg-cyan-500/10' : ''
                        }`}
                      >
                        <div className="w-7 h-7 rounded-lg bg-slate-800 flex items-center justify-center">
                          {getModelIcon(model.kind)}
                        </div>
                        <div className="flex-1 text-left">
                          <div className="text-xs font-medium text-slate-200">{model.label}</div>
                          <div className="text-[10px] text-slate-500">{model.provider}</div>
                        </div>
                        {model.id === selectedModel && (
                          <CheckCircle size={14} className="text-cyan-400" />
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4" aria-label="Chat Messages">
        {safeMessages.length === 0 && !isAnalyzing && (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-cyan-500/10 to-indigo-500/10 border border-cyan-500/20 flex items-center justify-center mb-4">
              <Sparkles size={24} className="text-cyan-400/60" />
            </div>
            <h3 className="text-sm font-semibold text-slate-300 mb-2">Ask me anything</h3>
            <p className="text-[11px] text-slate-500 max-w-[200px]">
              Tell me what you want to build, fix, or improve in your repository.
            </p>
          </div>
        )}

        {safeMessages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
          >
            {/* Avatar */}
            <div className={`w-7 h-7 rounded-xl shrink-0 flex items-center justify-center ${
              msg.role === 'user' 
                ? 'bg-indigo-500/20 border border-indigo-500/30' 
                : msg.role === 'system'
                ? 'bg-amber-500/20 border border-amber-500/30'
                : 'bg-cyan-500/20 border border-cyan-500/30'
            }`}>
              {msg.role === 'user' ? (
                <User size={14} className="text-indigo-400" />
              ) : msg.role === 'system' ? (
                <AlertTriangle size={14} className="text-amber-400" />
              ) : (
                <Bot size={14} className="text-cyan-400" />
              )}
            </div>
            
            {/* Bubble */}
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-indigo-600 text-white rounded-tr-sm'
                  : msg.role === 'system'
                  ? 'bg-amber-500/10 text-amber-300 border border-amber-500/20 rounded-tl-sm'
                  : 'bg-slate-800/80 text-slate-200 border border-cyan-500/10 rounded-tl-sm'
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}

        {/* Thinking Indicator */}
        {isAnalyzing && (
          <div className="flex gap-3">
            <div className="w-7 h-7 rounded-xl bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center shrink-0">
              <Bot size={14} className="text-cyan-400" />
            </div>
            <div className="bg-slate-800/80 border border-cyan-500/10 rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex items-center gap-2 text-cyan-400">
                <Loader2 size={14} className="animate-spin" />
                <span className="text-sm font-mono">{THINKING_FRAMES[thinkingFrame]}</span>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Suggestions */}
      {safeSuggestions.length > 0 && (
        <div className="border-t border-cyan-500/15 px-4 py-3 bg-slate-900/30" aria-label="Suggestions" data-testid="chat-suggestions">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles size={12} className="text-cyan-400" />
            <span className="text-[10px] text-cyan-400 uppercase tracking-widest font-bold">Quick Actions</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {safeSuggestions.map((suggestion) => (
              <button
                key={suggestion.id}
                type="button"
                onClick={() => handleSuggestionClick(suggestion)}
                disabled={suggestion.accepted}
                aria-label={describeSuggestionAction(suggestion)}
                aria-pressed={Boolean(suggestion.accepted)}
                className={`px-3 py-1.5 rounded-full text-[11px] font-medium transition-all ${
                  suggestion.accepted 
                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 opacity-60'
                    : 'bg-slate-800/80 text-slate-300 border border-cyan-500/20 hover:border-cyan-500/50 hover:bg-slate-700/80 active:scale-95'
                }`}
              >
                {suggestion.accepted ? '✓ ' : ''}{suggestion.title}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="p-4 border-t border-cyan-500/15 bg-slate-900/50 shrink-0">
        <form onSubmit={handleSubmit} className="flex gap-2" aria-label="Send Message">
          <div className="flex-1 relative">
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Ask or describe what you need..."
              aria-label="Chat message"
              className="w-full px-4 py-3 pr-10 bg-slate-800/80 border border-cyan-500/20 rounded-2xl text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 focus:ring-2 focus:ring-cyan-500/20 transition-all"
            />
            {inputValue && (
              <button
                type="button"
                onClick={() => { setInputValue(''); inputRef.current?.focus(); }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors p-1"
                aria-label="Clear input"
              >
                <CircleX size={16} />
              </button>
            )}
          </div>
          <button
            type="submit"
            disabled={!canSubmit}
            className="px-4 py-3 bg-cyan-500/20 border border-cyan-500/30 rounded-2xl text-cyan-400 hover:bg-cyan-500/30 disabled:opacity-30 disabled:cursor-not-allowed transition-all active:scale-95"
            aria-label="Send"
          >
            <Send size={18} />
          </button>
        </form>
        
        <button
          type="button"
          onClick={onClearChat}
          className="w-full mt-2 py-2 text-[11px] text-slate-500 hover:text-slate-400 flex items-center justify-center gap-2 transition-colors"
        >
          <Trash2 size={12} />
          Clear conversation
        </button>
      </div>
    </section>
  );
};
