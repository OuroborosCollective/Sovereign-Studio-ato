import React, { useState, useRef, useEffect, useMemo } from 'react';
import { 
  Download, Trash2, Send, Sparkles, CheckCircle, AlertTriangle, 
  Lightbulb, Loader2, CircleX, Bot, User, ChevronDown, Zap,
  Sparkle, Brain, Globe, Shield, Terminal, Layout, Columns
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

// Layout type enum
export type ChatLayoutType = 'terminal' | 'floating' | 'split-view';

// Layout configuration
export interface ChatLayoutConfig {
  id: ChatLayoutType;
  label: string;
  description: string;
  icon: React.ReactNode;
}

// Available layouts
export const CHAT_LAYOUTS: ChatLayoutConfig[] = [
  {
    id: 'terminal',
    label: 'Terminal',
    description: 'Minimal, command-oriented',
    icon: <Terminal size={14} />,
  },
  {
    id: 'floating',
    label: 'Floating',
    description: 'Classic chat with bubbles',
    icon: <Layout size={14} />,
  },
  {
    id: 'split-view',
    label: 'Split-View',
    description: 'Chat + Code side-by-side',
    icon: <Columns size={14} />,
  },
];

interface ChatLayoutTemplatesProps {
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
  /** Current layout type */
  layout?: ChatLayoutType;
  /** Callback when layout changes */
  onLayoutChange?: (layout: ChatLayoutType) => void;
}

// Kaomoji thinking states
const THINKING_FRAMES = ['( ^ω^)', '(^_^)', '(^‿^)', '(^o^)', '(^・ω・^)'];

/**
 * Terminal-style chat layout - minimal, command-like
 */
const TerminalChatLayout: React.FC<{
  messages: ChatMessage[];
  inputValue: string;
  onInputChange: (v: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  canSubmit: boolean;
  isAnalyzing: boolean;
  thinkingFrame: number;
}> = ({ messages, inputValue, onInputChange, onSubmit, canSubmit, isAnalyzing, thinkingFrame }) => (
  <div className="flex flex-col h-full bg-slate-950">
    {/* Terminal-style header */}
    <div className="px-4 py-2 border-b border-slate-800 bg-slate-900/50 flex items-center gap-2">
      <span className="text-[10px] text-slate-500 font-mono">sovereign-chat</span>
      {isAnalyzing && (
        <span className="text-cyan-400 font-mono text-[10px]">
          ··· {THINKING_FRAMES[thinkingFrame]}
        </span>
      )}
    </div>
    
    {/* Messages in terminal style */}
    <div className="flex-1 overflow-y-auto p-4 font-mono text-sm">
      {messages.map((msg, i) => (
        <div key={msg.id} className="mb-3">
          <span className={msg.role === 'user' ? 'text-emerald-400' : 'text-cyan-400'}>
            {msg.role === 'user' ? '> ' : '$ '}
          </span>
          <span className="text-slate-300">{msg.content}</span>
        </div>
      ))}
      {isAnalyzing && (
        <div className="text-cyan-400">
          <span>$ </span>
          <span className="animate-pulse">{THINKING_FRAMES[thinkingFrame]}</span>
        </div>
      )}
    </div>
    
    {/* Terminal input */}
    <form onSubmit={onSubmit} className="p-4 border-t border-slate-800">
      <div className="flex items-center gap-2">
        <span className="text-cyan-400 font-mono">$</span>
        <input
          type="text"
          value={inputValue}
          onChange={(e) => onInputChange(e.target.value)}
          className="flex-1 bg-transparent border-0 text-slate-200 font-mono text-sm outline-none placeholder-slate-600"
          placeholder="Enter command..."
        />
        <button
          type="submit"
          disabled={!canSubmit}
          className="text-cyan-400 disabled:opacity-30"
          aria-label="Send"
          title="Send"
        >
          <Send size={16} />
        </button>
      </div>
    </form>
  </div>
);

/**
 * Floating chat layout - classic bubble style
 */
const FloatingChatLayout: React.FC<{
  messages: ChatMessage[];
  suggestions: Suggestion[];
  inputValue: string;
  onInputChange: (v: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  onClear: () => void;
  canSubmit: boolean;
  isAnalyzing: boolean;
  thinkingFrame: number;
  availableModels: LlmModelInfo[];
  selectedModel?: string;
  onModelChange?: (modelId: string) => void;
  onAcceptSuggestion?: (suggestionId: string) => void;
}> = ({ messages, suggestions, inputValue, onInputChange, onSubmit, onClear, canSubmit, isAnalyzing, thinkingFrame, availableModels, selectedModel, onModelChange, onAcceptSuggestion }) => {
  const [showModelPicker, setShowModelPicker] = useState(false);
  const modelPickerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messagesEndRef.current) {
      const node = messagesEndRef.current;
      if (typeof node.scrollIntoView === 'function') {
        node.scrollIntoView({ behavior: 'smooth' });
      }
    }
  }, [messages, isAnalyzing]);

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

  const safeMessages = useMemo(() => normalizeChatMessages(messages), [messages]);
  const safeSuggestions = useMemo(() => normalizeSuggestions(suggestions), [suggestions]);
  const currentModel = availableModels.find(m => m.id === selectedModel) || availableModels[0];

  return (
    <div className="flex flex-col h-full">
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
                <div className="absolute right-0 top-full mt-2 w-64 bg-slate-900 border border-cyan-500/30 rounded-xl shadow-2xl z-50 overflow-hidden">
                  <div className="px-3 py-2 border-b border-cyan-500/15">
                    <span className="text-[10px] text-cyan-400 uppercase tracking-widest font-bold">Models</span>
                  </div>
                  <div className="py-1 max-h-48 overflow-y-auto">
                    {availableModels.map((model) => (
                      <button
                        key={model.id}
                        type="button"
                        onClick={() => { onModelChange?.(model.id); setShowModelPicker(false); }}
                        className={`w-full px-3 py-2 flex items-center gap-2 hover:bg-slate-800/80 ${model.id === selectedModel ? 'bg-cyan-500/10' : ''}`}
                      >
                        <span className="text-xs text-slate-200">{model.label}</span>
                        {model.id === selectedModel && <CheckCircle size={12} className="text-cyan-400 ml-auto" />}
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
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {safeMessages.length === 0 && !isAnalyzing && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-cyan-500/10 to-indigo-500/10 border border-cyan-500/20 flex items-center justify-center mb-4">
              <Sparkles size={24} className="text-cyan-400/60" />
            </div>
            <h3 className="text-sm font-semibold text-slate-300 mb-2">Ask me anything</h3>
            <p className="text-[11px] text-slate-500 max-w-[200px]">
              Tell me what you want to build, fix, or improve.
            </p>
          </div>
        )}

        {safeMessages.map((msg) => (
          <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
            <div className={`w-7 h-7 rounded-xl shrink-0 flex items-center justify-center ${
              msg.role === 'user' ? 'bg-indigo-500/20 border border-indigo-500/30' : 'bg-cyan-500/20 border border-cyan-500/30'
            }`}>
              {msg.role === 'user' ? <User size={14} className="text-indigo-400" /> : <Bot size={14} className="text-cyan-400" />}
            </div>
            <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
              msg.role === 'user' ? 'bg-indigo-600 text-white rounded-tr-sm' : 'bg-slate-800/80 text-slate-200 border border-cyan-500/10 rounded-tl-sm'
            }`}>
              {msg.content}
            </div>
          </div>
        ))}

        {isAnalyzing && (
          <div className="flex gap-3">
            <div className="w-7 h-7 rounded-xl bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center">
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
        <div className="border-t border-cyan-500/15 px-4 py-3 bg-slate-900/30">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles size={12} className="text-cyan-400" />
            <span className="text-[10px] text-cyan-400 uppercase tracking-widest font-bold">Quick Actions</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {safeSuggestions.map((suggestion) => (
              <button
                key={suggestion.id}
                type="button"
                onClick={() => !suggestion.accepted && onAcceptSuggestion(suggestion.id)}
                disabled={suggestion.accepted}
                className={`px-3 py-1.5 rounded-full text-[11px] font-medium ${
                  suggestion.accepted ? 'bg-emerald-500/20 text-emerald-400 opacity-60' : 'bg-slate-800/80 text-slate-300 border border-cyan-500/20 hover:border-cyan-500/50'
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
        <form onSubmit={onSubmit} className="flex gap-2">
          <div className="flex-1 relative">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => onInputChange(e.target.value)}
              placeholder="Ask or describe what you need..."
              className="w-full px-4 py-3 pr-10 bg-slate-800/80 border border-cyan-500/20 rounded-2xl text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50"
            />
            {inputValue && (
              <button
                type="button"
                onClick={() => onInputChange('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                aria-label="Clear input"
                title="Clear input"
              >
                <CircleX size={16} />
              </button>
            )}
          </div>
          <button
            type="submit"
            disabled={!canSubmit}
            className="px-4 py-3 bg-cyan-500/20 border border-cyan-500/30 rounded-2xl text-cyan-400 hover:bg-cyan-500/30 disabled:opacity-30"
            aria-label="Send"
            title="Send"
          >
            <Send size={18} />
          </button>
        </form>
        <button onClick={onClear} className="w-full mt-2 py-2 text-[11px] text-slate-500 hover:text-slate-400 flex items-center justify-center gap-2">
          <Trash2 size={12} />
          Clear conversation
        </button>
      </div>
    </div>
  );
};

/**
 * Split-View layout - chat + code side by side
 */
const SplitViewLayout: React.FC<{
  messages: ChatMessage[];
  inputValue: string;
  onInputChange: (v: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  canSubmit: boolean;
  isAnalyzing: boolean;
  thinkingFrame: number;
}> = ({ messages, inputValue, onInputChange, onSubmit, canSubmit, isAnalyzing, thinkingFrame }) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messagesEndRef.current) {
      const node = messagesEndRef.current;
      if (typeof node.scrollIntoView === 'function') {
        node.scrollIntoView({ behavior: 'smooth' });
      }
    }
  }, [messages, isAnalyzing]);

  return (
    <div className="flex h-full">
      {/* Chat side */}
      <div className="w-1/2 border-r border-slate-800 flex flex-col">
        <div className="px-4 py-2 border-b border-slate-800 bg-slate-900/50">
          <span className="text-xs text-cyan-400 font-bold">Chat</span>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.map((msg) => (
            <div key={msg.id} className={`text-sm ${msg.role === 'user' ? 'text-indigo-300' : 'text-slate-300'}`}>
              <span className="font-bold">{msg.role === 'user' ? 'You: ' : 'AI: '}</span>
              {msg.content}
            </div>
          ))}
          {isAnalyzing && (
            <div className="text-cyan-400 text-sm animate-pulse">
              {THINKING_FRAMES[thinkingFrame]}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
        <form onSubmit={onSubmit} className="p-3 border-t border-slate-800">
          <div className="flex gap-2">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => onInputChange(e.target.value)}
              className="flex-1 px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-lg text-sm text-slate-200 outline-none focus:border-cyan-500/50"
              placeholder="Type a message..."
            />
            <button
              type="submit"
              disabled={!canSubmit}
              className="px-3 py-2 bg-cyan-500/20 border border-cyan-500/30 rounded-lg text-cyan-400 disabled:opacity-30"
              aria-label="Send"
              title="Send"
            >
              <Send size={16} />
            </button>
          </div>
        </form>
      </div>
      
      {/* Code side - placeholder for now */}
      <div className="w-1/2 flex flex-col bg-slate-950">
        <div className="px-4 py-2 border-b border-slate-800 bg-slate-900/50">
          <span className="text-xs text-purple-400 font-bold">Code Output</span>
        </div>
        <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
          Code changes will appear here
        </div>
      </div>
    </div>
  );
};

/**
 * Main ChatLayoutTemplates component
 */
export const ChatLayoutTemplates: React.FC<ChatLayoutTemplatesProps> = ({
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
  layout = 'floating',
  onLayoutChange,
}) => {
  const [inputValue, setInputValue] = useState('');
  const [thinkingFrame, setThinkingFrame] = useState(0);

  const normalizedInput = normalizeChatInput(inputValue);
  const canSubmit = canSubmitChatMessage(inputValue);

  // Animate thinking frames
  useEffect(() => {
    if (!isAnalyzing) {
      setThinkingFrame(0);
      return;
    }
    const interval = setInterval(() => {
      setThinkingFrame((f) => (f + 1) % THINKING_FRAMES.length);
    }, 800);
    return () => clearInterval(interval);
  }, [isAnalyzing]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (canSubmit) {
      onSendMessage(normalizedInput);
      setInputValue('');
    }
  };

  const renderLayout = () => {
    const baseProps = {
      messages: chatMessages,
      inputValue,
      onInputChange: setInputValue,
      onSubmit: handleSubmit,
      canSubmit,
      isAnalyzing,
      thinkingFrame,
    };

    switch (layout) {
      case 'terminal':
        return <TerminalChatLayout {...baseProps} />;
      case 'split-view':
        return <SplitViewLayout {...baseProps} />;
      case 'floating':
      default:
        return (
          <FloatingChatLayout
            {...baseProps}
            suggestions={suggestions}
            onAcceptSuggestion={onAcceptSuggestion}
            onClear={onClearChat}
            availableModels={availableModels}
            selectedModel={selectedModel}
            onModelChange={onModelChange}
          />
        );
    }
  };

  return (
    <div className="w-full h-full flex flex-col" data-layout={layout}>
      {/* Layout selector toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-slate-800 bg-slate-900/30 shrink-0">
        <span className="text-[10px] text-slate-500 uppercase tracking-widest mr-2">Layout:</span>
        {CHAT_LAYOUTS.map((l) => (
          <button
            key={l.id}
            type="button"
            onClick={() => onLayoutChange?.(l.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              layout === l.id
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                : 'bg-slate-800/50 text-slate-400 border border-transparent hover:bg-slate-700/50'
            }`}
            aria-label={l.label}
            title={l.description}
          >
            {l.icon}
            <span>{l.label}</span>
          </button>
        ))}
      </div>
      
      {/* Layout content */}
      <div className="flex-1 overflow-hidden">
        {renderLayout()}
      </div>
    </div>
  );
};

export default ChatLayoutTemplates;