/**
 * Sovereign Studio V3 - Chat Layout Templates
 * 
 * Collection of template layouts for no-code chat interfaces
 * Optimized for Android tablet (768px+) with touch-friendly interactions
 * 
 * Usage: Import desired template and adapt to your needs
 */

import React, { useState, useRef, useEffect, useMemo, ReactNode } from 'react';
import { 
  Send, Sparkles, Bot, User, Loader2, CircleX, ChevronDown,
  FileText, Code, Image, Mic, Paperclip, MoreHorizontal,
  Check, CheckCheck, Clock, AlertCircle, Zap, Moon, Sun,
  MessageSquare, Workflow, GitBranch, Box, Layers, Cpu,
  Play, Pause, RotateCcw, Settings, Maximize2, Minimize2,
  Search, Filter, SortAsc, Download, Trash2, Copy, Edit3,
  Plus, Minus, X, ArrowLeft, ArrowRight, ChevronRight,
  Eye, EyeOff, Lock, Unlock, Shield, Globe, Wifi, WifiOff,
  Terminal, Database, Server, Cloud, Smartphone, Tablet
} from 'lucide-react';

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

export type ChatBubbleStyle = 'modern' | 'compact' | 'bubble' | 'card' | 'terminal';
export type ChatLayout = 'sidebar' | 'fullscreen' | 'split' | 'drawer' | 'floating';
export type ChatTheme = 'dark' | 'light' | 'cyberpunk' | 'minimal';
export type InputStyle = 'minimal' | 'rich' | 'voice' | 'command';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  status?: 'sending' | 'sent' | 'delivered' | 'error';
  reactions?: { emoji: string; count: number }[];
  attachments?: { name: string; type: string; url: string }[];
}

export interface ChatTemplateProps {
  messages: ChatMessage[];
  onSendMessage: (message: string) => void;
  onTypingStart?: () => void;
  onTypingEnd?: () => void;
  isTyping?: boolean;
  placeholder?: string;
  theme?: ChatTheme;
  bubbleStyle?: ChatBubbleStyle;
  showTimestamps?: boolean;
  showAvatars?: boolean;
  showReadStatus?: boolean;
  maxWidth?: string;
  children?: ReactNode;
}

// ============================================================================
// UTILITY COMPONENTS
// ============================================================================

const ThinkingIndicator: React.FC<{ frames?: string[] }> = ({ 
  frames = ['( ^ω^)', '(^_^)', '(^‿^)', '(^o^)', '(^・ω・^)'] 
}) => {
  const [frame, setFrame] = useState(0);
  
  useEffect(() => {
    const interval = setInterval(() => {
      setFrame(f => (f + 1) % frames.length);
    }, 800);
    return () => clearInterval(interval);
  }, [frames]);

  return (
    <div className="flex items-center gap-2 text-cyan-400">
      <Loader2 size={14} className="animate-spin" />
      <span className="text-sm font-mono">{frames[frame]}</span>
    </div>
  );
};

const TypingDots: React.FC = () => (
  <div className="flex items-center gap-1">
    {[0, 1, 2].map(i => (
      <div
        key={i}
        className="w-2 h-2 rounded-full bg-cyan-400 animate-bounce"
        style={{ animationDelay: `${i * 150}ms` }}
      />
    ))}
  </div>
);

const StatusBadge: React.FC<{ status: ChatMessage['status'] }> = ({ status }) => {
  const config = {
    sending: { icon: Clock, color: 'text-slate-400', label: 'Sending' },
    sent: { icon: Check, color: 'text-slate-500', label: 'Sent' },
    delivered: { icon: CheckCheck, color: 'text-cyan-400', label: 'Delivered' },
    error: { icon: AlertCircle, color: 'text-red-400', label: 'Error' },
  };
  const { icon: Icon, color, label } = config[status || 'sent'];
  return <Icon size={12} className={color} title={label} />;
};

// ============================================================================
// TEMPLATE 1: MODERN SIDEBAR CHAT (Sovereign Style)
// ============================================================================

export interface ModernSidebarChatProps extends ChatTemplateProps {
  headerContent?: ReactNode;
  footerContent?: ReactNode;
  suggestions?: string[];
  onAcceptSuggestion?: (suggestion: string) => void;
}

export const ModernSidebarChatTemplate: React.FC<ModernSidebarChatProps> = ({
  messages,
  onSendMessage,
  isTyping,
  placeholder = "Ask me anything...",
  headerContent,
  footerContent,
  suggestions = [],
  onAcceptSuggestion,
  theme = 'dark',
  showTimestamps = true,
  showAvatars = true,
}) => {
  const [inputValue, setInputValue] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  const themeClasses = {
    dark: {
      bg: 'bg-slate-950',
      border: 'border-cyan-500/20',
      text: 'text-slate-100',
      input: 'bg-slate-800/80 border-cyan-500/20',
    },
    light: {
      bg: 'bg-white',
      border: 'border-slate-200',
      text: 'text-slate-900',
      input: 'bg-slate-100 border-slate-300',
    },
    cyberpunk: {
      bg: 'bg-black',
      border: 'border-pink-500/30',
      text: 'text-pink-100',
      input: 'bg-zinc-900 border-pink-500/30',
    },
    minimal: {
      bg: 'bg-transparent',
      border: 'border-transparent',
      text: 'text-slate-900 dark:text-slate-100',
      input: 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700',
    },
  };

  const t = themeClasses[theme];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputValue.trim()) {
      onSendMessage(inputValue);
      setInputValue('');
    }
  };

  return (
    <div className={`flex flex-col h-full ${t.bg} ${t.border} border-x`}>
      {/* Header */}
      <header className="px-4 py-3 border-b bg-slate-900/50 shrink-0">
        {headerContent || (
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500/20 to-indigo-500/20 border border-cyan-500/30 flex items-center justify-center">
              <Bot size={20} className="text-cyan-400" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-100">AI Assistant</h2>
              <p className="text-xs text-slate-500">Powered by Sovereign</p>
            </div>
          </div>
        )}
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && !isTyping && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-cyan-500/10 to-indigo-500/10 border border-cyan-500/20 flex items-center justify-center mb-4">
              <Sparkles size={32} className="text-cyan-400/60" />
            </div>
            <h3 className="text-lg font-semibold text-slate-300 mb-2">Welcome to Sovereign</h3>
            <p className="text-sm text-slate-500 max-w-xs">
              Tell me what you want to build, fix, or improve in your repository.
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
          >
            {showAvatars && (
              <div className={`w-8 h-8 rounded-xl shrink-0 flex items-center justify-center ${
                msg.role === 'user' 
                  ? 'bg-indigo-500/20 border border-indigo-500/30' 
                  : 'bg-cyan-500/20 border border-cyan-500/30'
              }`}>
                {msg.role === 'user' 
                  ? <User size={16} className="text-indigo-400" />
                  : <Bot size={16} className="text-cyan-400" />
                }
              </div>
            )}
            
            <div className={`max-w-[80%] rounded-2xl px-4 py-3 ${
              msg.role === 'user'
                ? 'bg-indigo-600 text-white rounded-tr-sm'
                : 'bg-slate-800/80 text-slate-200 border border-cyan-500/10 rounded-tl-sm'
            }`}>
              <p className="whitespace-pre-wrap">{msg.content}</p>
              {showTimestamps && (
                <div className="mt-2 flex items-center gap-2">
                  <span className={`text-[10px] ${msg.role === 'user' ? 'text-indigo-200' : 'text-slate-500'}`}>
                    {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                  {msg.status && msg.role === 'user' && <StatusBadge status={msg.status} />}
                </div>
              )}
            </div>
          </div>
        ))}

        {isTyping && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-xl bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center shrink-0">
              <Bot size={16} className="text-cyan-400" />
            </div>
            <div className="bg-slate-800/80 border border-cyan-500/10 rounded-2xl rounded-tl-sm px-4 py-3">
              <ThinkingIndicator />
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Suggestions */}
      {suggestions.length > 0 && showSuggestions && (
        <div className="border-t border-cyan-500/15 px-4 py-3 bg-slate-900/30">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Sparkles size={12} className="text-cyan-400" />
              <span className="text-xs text-cyan-400 uppercase tracking-widest font-bold">Quick Actions</span>
            </div>
            <button 
              onClick={() => setShowSuggestions(false)}
              className="text-slate-500 hover:text-slate-400"
            >
              <X size={14} />
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((suggestion, i) => (
              <button
                key={i}
                onClick={() => onAcceptSuggestion?.(suggestion)}
                className="px-3 py-2 rounded-full text-xs font-medium bg-slate-800/80 text-slate-300 border border-cyan-500/20 hover:border-cyan-500/50 hover:bg-slate-700/80 transition-all active:scale-95"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="p-4 border-t bg-slate-900/50 shrink-0">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <div className="flex-1 relative">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={placeholder}
              className={`w-full px-4 py-3 pr-10 ${t.input} rounded-2xl text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition-all`}
            />
            {inputValue && (
              <button
                type="button"
                onClick={() => setInputValue('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
              >
                <CircleX size={16} />
              </button>
            )}
          </div>
          <button
            type="submit"
            disabled={!inputValue.trim()}
            className="px-4 py-3 bg-cyan-500/20 border border-cyan-500/30 rounded-2xl text-cyan-400 hover:bg-cyan-500/30 disabled:opacity-30 disabled:cursor-not-allowed transition-all active:scale-95"
          >
            <Send size={18} />
          </button>
        </form>
        {footerContent}
      </div>
    </div>
  );
};

// ============================================================================
// TEMPLATE 2: COMPACT CARD CHAT (For Tablet)
// ============================================================================

export interface CompactCardChatProps extends ChatTemplateProps {
  cards?: { title: string; description: string; icon?: ReactNode; action?: () => void }[];
  onCardClick?: (card: { title: string }) => void;
}

export const CompactCardChatTemplate: React.FC<CompactCardChatProps> = ({
  messages,
  onSendMessage,
  isTyping,
  cards = [],
  onCardClick,
  maxWidth = 'max-w-2xl',
}) => {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-slate-900 to-slate-950">
      {/* Card Actions */}
      {cards.length > 0 && (
        <div className="px-4 py-3 border-b border-slate-800 overflow-x-auto">
          <div className="flex gap-3 min-w-max">
            {cards.map((card, i) => (
              <button
                key={i}
                onClick={() => onCardClick?.(card)}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-800/50 border border-slate-700/50 hover:border-cyan-500/30 hover:bg-slate-800 transition-all"
              >
                {card.icon || <Box size={16} className="text-cyan-400" />}
                <span className="text-sm text-slate-300 whitespace-nowrap">{card.title}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div className={`${maxWidth} rounded-2xl px-5 py-4 ${
              msg.role === 'user'
                ? 'bg-gradient-to-r from-indigo-600 to-indigo-500 text-white shadow-lg shadow-indigo-500/20'
                : 'bg-slate-800/80 text-slate-200 border border-slate-700/50'
            }`}>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
              <div className="mt-2 text-[10px] opacity-60">
                {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          </div>
        ))}

        {isTyping && (
          <div className="flex justify-start">
            <div className={`${maxWidth} bg-slate-800/80 rounded-2xl px-5 py-4`}>
              <TypingDots />
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 bg-slate-900/80 border-t border-slate-800/50 backdrop-blur-sm">
        <form onSubmit={(e) => { e.preventDefault(); if (inputValue.trim()) { onSendMessage(inputValue); setInputValue(''); }}} className="flex gap-3">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Type your message..."
            className="flex-1 px-4 py-3 bg-slate-800/50 border border-slate-700/50 rounded-2xl text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/30"
          />
          <button
            type="submit"
            disabled={!inputValue.trim()}
            className="px-5 py-3 bg-cyan-500/20 border border-cyan-500/30 rounded-2xl text-cyan-400 hover:bg-cyan-500/30 disabled:opacity-30 transition-all"
          >
            <Send size={18} />
          </button>
        </form>
      </div>
    </div>
  );
};

// ============================================================================
// TEMPLATE 3: TERMINAL STYLE CHAT
// ============================================================================

export interface TerminalChatProps extends ChatTemplateProps {
  prompt?: string;
  terminalPrefix?: string;
}

export const TerminalChatTemplate: React.FC<TerminalChatProps> = ({
  messages,
  onSendMessage,
  isTyping,
  prompt = 'sovereign>',
  terminalPrefix = 'sovereign@studio',
  maxWidth = 'max-w-3xl',
}) => {
  const [inputValue, setInputValue] = useState('');
  const [commandHistory, setCommandHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputValue.trim()) {
      setCommandHistory(prev => [...prev, inputValue]);
      setHistoryIndex(-1);
      onSendMessage(inputValue);
      setInputValue('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (commandHistory.length > 0) {
        const newIndex = historyIndex === -1 ? commandHistory.length - 1 : Math.max(0, historyIndex - 1);
        setHistoryIndex(newIndex);
        setInputValue(commandHistory[newIndex]);
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIndex !== -1) {
        const newIndex = historyIndex + 1;
        if (newIndex >= commandHistory.length) {
          setHistoryIndex(-1);
          setInputValue('');
        } else {
          setHistoryIndex(newIndex);
          setInputValue(commandHistory[newIndex]);
        }
      }
    }
  };

  return (
    <div className="flex flex-col h-full bg-black font-mono" onClick={() => inputRef.current?.focus()}>
      {/* Terminal Header */}
      <div className="px-4 py-2 bg-zinc-900 border-b border-zinc-800 flex items-center gap-2">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-red-500/80" />
          <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
          <div className="w-3 h-3 rounded-full bg-green-500/80" />
        </div>
        <span className="ml-4 text-xs text-zinc-500">{terminalPrefix}</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="text-xs text-zinc-500 mb-4">
          <p>Sovereign Studio Terminal v3.0.0</p>
          <p>Type 'help' for available commands</p>
          <p className="mt-2 border-t border-zinc-800 pt-2">─────────────────────────────────</p>
        </div>

        {messages.map((msg) => (
          <div key={msg.id} className="space-y-1">
            {msg.role === 'user' && (
              <div className="flex items-center gap-2">
                <span className="text-cyan-400">{prompt}</span>
                <span className="text-zinc-300">{msg.content}</span>
              </div>
            )}
            {msg.role === 'assistant' && (
              <pre className="text-zinc-400 whitespace-pre-wrap text-xs leading-relaxed bg-zinc-900/50 p-3 rounded border border-zinc-800/50">
                {msg.content}
              </pre>
            )}
          </div>
        ))}

        {isTyping && (
          <div className="flex items-center gap-2">
            <span className="text-cyan-400">{prompt}</span>
            <span className="text-zinc-500 animate-pulse">Processing...</span>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 bg-zinc-900/50 border-t border-zinc-800 flex items-center gap-2">
        <span className="text-cyan-400 shrink-0">{prompt}</span>
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          className="flex-1 bg-transparent text-zinc-300 text-sm focus:outline-none"
          autoFocus
        />
        <span className="w-2 h-4 bg-zinc-500 animate-pulse" />
      </form>
    </div>
  );
};

// ============================================================================
// TEMPLATE 4: SPLIT VIEW CHAT (For Large Tablets)
// ============================================================================

export interface SplitViewChatProps extends ChatTemplateProps {
  leftPanel?: ReactNode;
  rightPanel?: ReactNode;
  leftPanelWidth?: string;
}

export const SplitViewChatTemplate: React.FC<SplitViewChatProps> = ({
  messages,
  onSendMessage,
  isTyping,
  leftPanel,
  rightPanel,
  leftPanelWidth = 'w-80',
  maxWidth,
}) => {
  const [inputValue, setInputValue] = useState('');
  const [leftPanelOpen, setLeftPanelOpen] = useState(true);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex h-full bg-slate-950">
      {/* Left Panel - File Tree / Context */}
      {leftPanel && leftPanelOpen && (
        <aside className={`${leftPanelWidth} border-r border-cyan-500/20 bg-slate-900/50 flex flex-col`}>
          <div className="p-3 border-b border-cyan-500/15 flex items-center justify-between">
            <span className="text-xs text-cyan-400 uppercase tracking-widest font-bold">Explorer</span>
            <button onClick={() => setLeftPanelOpen(false)} className="text-slate-500 hover:text-slate-300">
              <ChevronRight size={16} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {leftPanel}
          </div>
        </aside>
      )}

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
            >
              <div className={`w-8 h-8 rounded-xl shrink-0 flex items-center justify-center ${
                msg.role === 'user' ? 'bg-indigo-500/20' : 'bg-cyan-500/20'
              }`}>
                {msg.role === 'user' 
                  ? <User size={16} className="text-indigo-400" />
                  : <Bot size={16} className="text-cyan-400" />
                }
              </div>
              <div className={`max-w-[70%] rounded-2xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-800/80 text-slate-200 border border-cyan-500/10'
              }`}>
                {msg.content}
              </div>
            </div>
          ))}
          {isTyping && <ThinkingIndicator />}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="p-4 border-t border-cyan-500/15 bg-slate-900/50">
          <form onSubmit={(e) => { e.preventDefault(); if (inputValue.trim()) { onSendMessage(inputValue); setInputValue(''); }}} className="flex gap-2">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Message AI..."
              className="flex-1 px-4 py-3 bg-slate-800/80 border border-cyan-500/20 rounded-2xl text-sm text-slate-200 focus:outline-none"
            />
            <button type="submit" className="px-4 py-3 bg-cyan-500/20 border border-cyan-500/30 rounded-2xl text-cyan-400">
              <Send size={18} />
            </button>
          </form>
        </div>
      </main>

      {/* Right Panel - Output / Preview */}
      {rightPanel && rightPanelOpen && (
        <aside className="w-80 border-l border-cyan-500/20 bg-slate-900/50 flex flex-col">
          <div className="p-3 border-b border-cyan-500/15 flex items-center justify-between">
            <span className="text-xs text-cyan-400 uppercase tracking-widest font-bold">Output</span>
            <button onClick={() => setRightPanelOpen(false)} className="text-slate-500 hover:text-slate-300">
              <ChevronRight size={16} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {rightPanel}
          </div>
        </aside>
      )}
    </div>
  );
};

// ============================================================================
// TEMPLATE 5: FLOATING CHAT (Overlay)
// ============================================================================

export interface FloatingChatProps extends ChatTemplateProps {
  position?: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left';
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export const FloatingChatTemplate: React.FC<FloatingChatProps> = ({
  messages,
  onSendMessage,
  isTyping,
  position = 'bottom-right',
  collapsed = false,
  onToggleCollapse,
}) => {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const positionClasses = {
    'bottom-right': 'bottom-6 right-6',
    'bottom-left': 'bottom-6 left-6',
    'top-right': 'top-6 right-6',
    'top-left': 'top-6 left-6',
  };

  useEffect(() => {
    if (!collapsed) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, collapsed]);

  if (collapsed) {
    return (
      <button
        onClick={onToggleCollapse}
        className={`fixed ${positionClasses[position]} w-16 h-16 rounded-full bg-gradient-to-br from-cyan-500 to-indigo-500 shadow-lg shadow-cyan-500/30 flex items-center justify-center text-white hover:scale-105 transition-transform z-50`}
      >
        <MessageSquare size={24} />
      </button>
    );
  }

  return (
    <div className={`fixed ${positionClasses[position]} w-96 h-[500px] rounded-3xl bg-slate-900/95 backdrop-blur-xl border border-cyan-500/20 shadow-2xl shadow-cyan-950/50 flex flex-col overflow-hidden z-50`}>
      {/* Header */}
      <div className="px-4 py-3 border-b border-cyan-500/15 flex items-center justify-between bg-slate-900/80">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-cyan-500/20 to-indigo-500/20 flex items-center justify-center">
            <Bot size={16} className="text-cyan-400" />
          </div>
          <span className="text-sm font-bold text-slate-100">AI Assistant</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onToggleCollapse} className="text-slate-500 hover:text-slate-300 p-1">
            <Minimize2 size={16} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-2 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
          >
            <div className={`w-6 h-6 rounded-lg shrink-0 flex items-center justify-center ${
              msg.role === 'user' ? 'bg-indigo-500/20' : 'bg-cyan-500/20'
            }`}>
              {msg.role === 'user' 
                ? <User size={12} className="text-indigo-400" />
                : <Bot size={12} className="text-cyan-400" />
              }
            </div>
            <div className={`max-w-[75%] rounded-2xl px-3 py-2 text-xs ${
              msg.role === 'user'
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-800 text-slate-200'
            }`}>
              {msg.content}
            </div>
          </div>
        ))}
        {isTyping && (
          <div className="flex gap-2">
            <div className="w-6 h-6 rounded-lg bg-cyan-500/20 flex items-center justify-center">
              <Bot size={12} className="text-cyan-400" />
            </div>
            <div className="bg-slate-800 rounded-2xl px-3 py-2">
              <TypingDots />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-cyan-500/15 bg-slate-900/80">
        <form onSubmit={(e) => { e.preventDefault(); if (inputValue.trim()) { onSendMessage(inputValue); setInputValue(''); }}} className="flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Ask..."
            className="flex-1 px-3 py-2 bg-slate-800/80 border border-cyan-500/20 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none"
          />
          <button type="submit" className="px-3 py-2 bg-cyan-500/20 border border-cyan-500/30 rounded-xl text-cyan-400">
            <Send size={14} />
          </button>
        </form>
      </div>
    </div>
  );
};

// ============================================================================
// TEMPLATE 6: VOICE-FIRST CHAT (For Mobile/Tablet)
// ============================================================================

export interface VoiceFirstChatProps extends ChatTemplateProps {
  onVoiceInput?: () => void;
  isListening?: boolean;
}

export const VoiceFirstChatTemplate: React.FC<VoiceFirstChatProps> = ({
  messages,
  onSendMessage,
  isTyping,
  onVoiceInput,
  isListening = false,
}) => {
  const [inputValue, setInputValue] = useState('');
  const [isExpanded, setIsExpanded] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-slate-900 to-slate-950">
      {/* Collapsed Voice Button */}
      {!isExpanded && (
        <div className="flex-1 flex items-center justify-center">
          <button
            onClick={() => setIsExpanded(true)}
            className={`w-32 h-32 rounded-full flex items-center justify-center transition-all ${
              isListening 
                ? 'bg-red-500/20 border-2 border-red-500 animate-pulse' 
                : 'bg-cyan-500/20 border-2 border-cyan-500'
            }`}
          >
            <Mic size={48} className={isListening ? 'text-red-400' : 'text-cyan-400'} />
          </button>
        </div>
      )}

      {/* Expanded View */}
      {isExpanded && (
        <>
          <div className="p-4 border-b border-slate-800 flex items-center justify-between">
            <button onClick={() => setIsExpanded(false)} className="text-slate-400">
              <ArrowLeft size={20} />
            </button>
            <span className="text-sm text-slate-300">Voice Assistant</span>
            <div className="w-5" />
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                  msg.role === 'user'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-800 text-slate-200'
                }`}>
                  <p className="text-sm">{msg.content}</p>
                </div>
              </div>
            ))}
            {isTyping && <TypingDots />}
            <div ref={messagesEndRef} />
          </div>

          {/* Voice + Text Input */}
          <div className="p-4 bg-slate-900/50 border-t border-slate-800">
            <div className="flex gap-3">
              <button
                onClick={onVoiceInput}
                className={`w-12 h-12 rounded-full flex items-center justify-center transition-all ${
                  isListening 
                    ? 'bg-red-500 text-white animate-pulse' 
                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                }`}
              >
                <Mic size={20} />
              </button>
              <form onSubmit={(e) => { e.preventDefault(); if (inputValue.trim()) { onSendMessage(inputValue); setInputValue(''); }}} className="flex-1 flex gap-2">
                <input
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder="Or type a message..."
                  className="flex-1 px-4 bg-slate-800 border border-slate-700 rounded-xl text-sm text-slate-200 focus:outline-none"
                />
                <button type="submit" className="px-4 bg-cyan-500/20 border border-cyan-500/30 rounded-xl text-cyan-400">
                  <Send size={18} />
                </button>
              </form>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

// ============================================================================
// TEMPLATE 7: WORKFLOW CHAT (With Step Indicators)
// ============================================================================

export interface WorkflowChatProps extends ChatTemplateProps {
  steps?: { label: string; status: 'pending' | 'active' | 'done' | 'error' }[];
  currentStep?: number;
}

export const WorkflowChatTemplate: React.FC<WorkflowChatProps> = ({
  messages,
  onSendMessage,
  isTyping,
  steps = [],
  currentStep = 0,
}) => {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const stepColors = {
    pending: 'bg-slate-700 text-slate-500',
    active: 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50',
    done: 'bg-emerald-500/20 text-emerald-400',
    error: 'bg-red-500/20 text-red-400',
  };

  return (
    <div className="flex flex-col h-full bg-slate-950">
      {/* Workflow Steps */}
      {steps.length > 0 && (
        <div className="px-4 py-3 border-b border-cyan-500/15 overflow-x-auto">
          <div className="flex items-center gap-2 min-w-max">
            {steps.map((step, i) => (
              <React.Fragment key={i}>
                <div className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${stepColors[step.status]}`}>
                  {step.status === 'done' && <Check size={12} className="inline mr-1" />}
                  {step.status === 'active' && <Loader2 size={12} className="inline mr-1 animate-spin" />}
                  {step.label}
                </div>
                {i < steps.length - 1 && (
                  <ChevronRight size={14} className="text-slate-600" />
                )}
              </React.Fragment>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[75%] rounded-2xl px-4 py-3 ${
              msg.role === 'user'
                ? 'bg-indigo-600 text-white'
                : msg.role === 'system'
                ? 'bg-amber-500/10 text-amber-300 border border-amber-500/20'
                : 'bg-slate-800/80 text-slate-200 border border-cyan-500/10'
            }`}>
              {msg.content}
            </div>
          </div>
        ))}
        {isTyping && (
          <div className="flex justify-start">
            <div className="bg-slate-800/80 rounded-2xl px-4 py-3 border border-cyan-500/10">
              <TypingDots />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-cyan-500/15 bg-slate-900/50">
        <form onSubmit={(e) => { e.preventDefault(); if (inputValue.trim()) { onSendMessage(inputValue); setInputValue(''); }}} className="flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Describe what you need..."
            className="flex-1 px-4 py-3 bg-slate-800/80 border border-cyan-500/20 rounded-2xl text-sm text-slate-200 focus:outline-none"
          />
          <button type="submit" className="px-4 py-3 bg-cyan-500/20 border border-cyan-500/30 rounded-2xl text-cyan-400">
            <Send size={18} />
          </button>
        </form>
      </div>
    </div>
  );
};

// ============================================================================
// EXPORTS
// ============================================================================

export const ChatTemplates = {
  ModernSidebar: ModernSidebarChatTemplate,
  CompactCard: CompactCardChatTemplate,
  Terminal: TerminalChatTemplate,
  SplitView: SplitViewChatTemplate,
  Floating: FloatingChatTemplate,
  VoiceFirst: VoiceFirstChatTemplate,
  Workflow: WorkflowChatTemplate,
};

export default ChatTemplates;
