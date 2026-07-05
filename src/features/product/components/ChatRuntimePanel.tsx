/**
 * Chat Runtime Panel - Central Chat Interface with Runtime Intelligence
 * 
 * Entry → Process → Exit flow with Error Boundaries
 * Connected to RuntimeIntelligence for health checks and telemetry
 */

import React, { useState, useCallback, useMemo, useEffect, Component, ReactNode, useRef } from 'react';
import { 
  Send, 
  RefreshCw, 
  AlertTriangle, 
  CheckCircle, 
  Bot, 
  User, 
  Loader2,
  Wifi,
  WifiOff,
  Shield,
  CircleX,
} from 'lucide-react';
import {
  validateChatEntry,
  checkChatEntryGuard,
  executeChatRuntime,
  buildChatExitState,
  assertChatRuntimeHealthy,
  type ChatMessage,
  type ChatExitState,
  ChatRuntimeError,
} from '../runtime/chatRuntime';
import { useRuntimeModelHealth } from '../hooks/useRuntimeModelHealth';
import { useAllLlmAdapters } from '../contexts/LlmAdapterContext';
import type { LlmAdapter } from '../llm/llmAdapter';

// ============================================================================
// Error Boundary Component
// ============================================================================

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: string;
}

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, info: string) => void;
}

class ChatErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { 
      hasError: false, 
      error: null,
      errorInfo: '',
    };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { 
      hasError: true, 
      error,
      errorInfo: error instanceof ChatRuntimeError 
        ? `[${error.stage}] ${error.message}` 
        : error.message,
    };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('ChatErrorBoundary caught:', error, errorInfo);
    this.props.onError?.(error, errorInfo.componentStack || '');
  }

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      
      const error = this.state.error as ChatRuntimeError | null;
      const recoverable = error?.recoverable ?? false;
      
      return (
        <div className="flex flex-col items-center justify-center p-6 bg-red-950/30 rounded-xl border border-red-500/30">
          <AlertTriangle className="w-8 h-8 text-red-400 mb-3" />
          <h3 className="text-red-300 font-bold mb-2">Chat Error</h3>
          <p className="text-red-200/70 text-sm text-center mb-4">
            {this.state.errorInfo}
          </p>
          {recoverable && (
            <button
              onClick={() => this.setState({ hasError: false, error: null, errorInfo: '' })}
              className="flex items-center gap-2 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 border border-red-500/40 rounded-lg text-red-200 text-sm transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Retry
            </button>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}

// ============================================================================
// Status Indicator Component
// ============================================================================

interface ChatStatusIndicatorProps {
  modelHealth: ChatExitState['modelHealth'];
  isChecking: boolean;
}

function ChatStatusIndicator({ modelHealth, isChecking }: ChatStatusIndicatorProps) {
  const statusColor = modelHealth.status === 'healthy' 
    ? 'text-emerald-400' 
    : modelHealth.status === 'degraded'
      ? 'text-amber-400'
      : 'text-slate-400';
      
  const statusIcon = modelHealth.status === 'healthy' 
    ? <Wifi className="w-4 h-4" />
    : modelHealth.status === 'degraded'
      ? <Wifi className="w-4 h-4 animate-pulse" />
      : <WifiOff className="w-4 h-4" />;

  return (
    <div className={`flex items-center gap-2 ${statusColor}`}>
      {isChecking ? (
        <Loader2 className="w-4 h-4 animate-spin" />
      ) : (
        statusIcon
      )}
      <span className="text-xs font-medium">
        {modelHealth.status === 'healthy' 
          ? `Model: ${modelHealth.modelId ?? 'OK'}`
          : modelHealth.status === 'degraded'
            ? 'Model degraded'
            : 'No model'}
      </span>
      {modelHealth.latencyMs !== null && (
        <span className="text-xs opacity-60">
          · {modelHealth.latencyMs.toFixed(0)}ms
        </span>
      )}
    </div>
  );
}

// ============================================================================
// Main Chat Runtime Panel
// ============================================================================

export interface ChatRuntimePanelProps {
  /** LLM adapters for health monitoring (optional - uses context if not provided) */
  adapters?: LlmAdapter[];
  /** Initial messages */
  initialMessages?: ChatMessage[];
  /** Callback when message is sent */
  onMessageSent?: (message: string) => void;
  /** Callback when error occurs */
  onError?: (error: Error) => void;
}

export function ChatRuntimePanel({
  adapters: propAdapters,
  initialMessages = [],
  onMessageSent,
  onError,
}: ChatRuntimePanelProps) {
  // Get adapters from context if not provided as prop
  const contextAdapters = useAllLlmAdapters();
  const adapters = propAdapters ?? contextAdapters;
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [inputValue, setInputValue] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [exitState, setExitState] = useState<ChatExitState | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      const node = scrollRef.current;
      if (typeof node.scrollTo === 'function') {
        node.scrollTo({
          top: node.scrollHeight,
          behavior: 'smooth'
        });
      } else {
        node.scrollTop = node.scrollHeight;
      }
    }
  }, [messages, isProcessing]);

  // Connect to Runtime Model Health
  const {
    isChecking,
    lastCheck,
    refresh,
    fallbackResult,
  } = useRuntimeModelHealth({
    adapters,
    autoStart: true,
  });

  // Build initial exit state
  useEffect(() => {
    if (!exitState && messages.length > 0) {
      const state = buildChatExitState(messages, { success: true });
      setExitState(state);
    }
  }, [messages]);

  // Handle error from error boundary
  const handleError = useCallback((error: Error, _info: string) => {
    console.error('Chat error:', error);
    onError?.(error);
  }, [onError]);

  // Submit handler
  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    
    const input = inputValue.trim();
    if (!input || isProcessing) return;

    // === ENTRY: Validate ===
    const validation = validateChatEntry(input);
    if (!validation.valid) {
      const error = new ChatRuntimeError(
        validation.errors.join(', '),
        'entry',
        true
      );
      handleError(error, '');
      return;
    }

    // Add user message
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: validation.normalizedInput,
      timestamp: Date.now(),
    };
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    onMessageSent?.(input);

    setIsProcessing(true);

    try {
      // === ENTRY: Guard Check ===
      const guardResult = await checkChatEntryGuard(input);
      if (!guardResult.pass) {
        throw new ChatRuntimeError(
          guardResult.reason ?? 'Guard check failed',
          'entry',
          true
        );
      }

      // === PROCESS: Execute Chat Runtime ===
      const result = await executeChatRuntime(input, messages);

      if (result.error) {
        throw result.error;
      }

      if (result.exitState) {
        // === EXIT: Update State ===
        setExitState(result.exitState);
        
        // Add assistant message
        const assistantMessage: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: result.exitState.suggestions[0]?.title ?? 'Message processed',
          timestamp: Date.now(),
          metadata: {
            modelId: result.exitState.modelHealth.modelId,
            latencyMs: result.exitState.modelHealth.latencyMs,
          },
        };
        setMessages(prev => [...prev, assistantMessage]);
      }

    } catch (error) {
      const runtimeError = error instanceof ChatRuntimeError 
        ? error 
        : new ChatRuntimeError(
            error instanceof Error ? error.message : 'Unknown error',
            'process',
            true
          );
      handleError(runtimeError, '');
    } finally {
      setIsProcessing(false);
    }
  }, [inputValue, isProcessing, messages, onMessageSent, handleError]);

  // Error boundary fallback
  const errorFallback = useMemo(() => (
    <div className="flex flex-col items-center justify-center p-6 bg-red-950/30 rounded-xl border border-red-500/30">
      <AlertTriangle className="w-8 h-8 text-red-400 mb-3" />
      <h3 className="text-red-300 font-bold mb-2">Runtime Error</h3>
      <p className="text-red-200/70 text-sm text-center">
        The chat system encountered an error. Please try again.
      </p>
    </div>
  ), []);

  return (
    <ChatErrorBoundary fallback={errorFallback} onError={handleError}>
      <div className="flex flex-col h-full bg-slate-950 rounded-xl border border-slate-800 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 bg-slate-900/50">
          <div className="flex items-center gap-3">
            <Bot className="w-5 h-5 text-cyan-400" />
            <h2 className="font-bold text-slate-100">Sovereign Chat</h2>
          </div>
          <div className="flex items-center gap-3">
            {exitState && (
              <ChatStatusIndicator 
                modelHealth={exitState.modelHealth}
                isChecking={isChecking}
              />
            )}
            <button
              onClick={() => refresh()}
              disabled={isChecking}
              className="p-2 hover:bg-slate-800 rounded-lg transition-colors disabled:opacity-50"
              title="Refresh health"
              aria-label="Refresh health"
            >
              <RefreshCw className={`w-4 h-4 text-slate-400 ${isChecking ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Runtime Health Bar */}
        <div className="flex items-center gap-2 px-4 py-2 bg-slate-900/30 border-b border-slate-800/50 text-xs">
          <Shield className="w-3 h-3 text-cyan-500" />
          <span className="text-slate-400">Runtime:</span>
          <span className={`font-medium ${
            fallbackResult.proceed ? 'text-emerald-400' : 'text-amber-400'
          }`}>
            {fallbackResult.proceed ? 'Ready' : 'Degraded'}
          </span>
          <span className="text-slate-600">·</span>
          <span className="text-slate-500">
            Strategy: {fallbackResult.strategy}
          </span>
          {fallbackResult.selectedModel && (
            <>
              <span className="text-slate-600">·</span>
              <span className="text-slate-400">
                Model: {fallbackResult.selectedModel.adapterName}
              </span>
            </>
          )}
        </div>

        {/* Messages */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-4 space-y-4"
        >
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <Bot className="w-12 h-12 text-slate-600 mb-4" />
              <p className="text-slate-400 mb-2">Start a conversation</p>
              <p className="text-slate-500 text-sm">
                Your messages are processed through the Runtime Intelligence layer
              </p>
            </div>
          ) : (
            messages.map((message) => (
              <div
                key={message.id}
                className={`flex gap-3 ${
                  message.role === 'user' ? 'flex-row-reverse' : ''
                }`}
              >
                <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                  message.role === 'user' 
                    ? 'bg-cyan-500/20' 
                    : 'bg-slate-800'
                }`}>
                  {message.role === 'user' 
                    ? <User className="w-4 h-4 text-cyan-400" />
                    : <Bot className="w-4 h-4 text-slate-400" />
                  }
                </div>
                <div className={`flex-1 max-w-[80%] ${
                  message.role === 'user' 
                    ? 'text-right' 
                    : ''
                }`}>
                  <div className={`inline-block px-4 py-2 rounded-2xl ${
                    message.role === 'user'
                      ? 'bg-cyan-500/20 text-cyan-100 rounded-tr-sm'
                      : 'bg-slate-800 text-slate-200 rounded-tl-sm'
                  }`}>
                    <p className="whitespace-pre-wrap">{message.content}</p>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    {new Date(message.timestamp).toLocaleTimeString()}
                    {message.metadata?.modelId && (
                      <span className="ml-2 text-slate-600">
                        · {message.metadata.modelId as string}
                      </span>
                    )}
                  </p>
                </div>
              </div>
            ))
          )}
          
          {isProcessing && (
            <div className="flex gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center">
                <Bot className="w-4 h-4 text-slate-400" />
              </div>
              <div className="flex-1">
                <div className="inline-block px-4 py-3 bg-slate-800 rounded-2xl rounded-tl-sm">
                  <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <form onSubmit={handleSubmit} className="p-4 border-t border-slate-800">
          <div className="flex gap-3">
            <div className="flex-1 relative">
              <input
                ref={inputRef}
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder="Type your message..."
                disabled={isProcessing}
                className="w-full px-4 py-3 pr-10 bg-slate-800/80 border border-slate-700 rounded-2xl text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 disabled:opacity-50 transition-colors"
                aria-label="Chat message"
              />
              {inputValue && !isProcessing && (
                <button
                  type="button"
                  onClick={() => { setInputValue(''); inputRef.current?.focus(); }}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors p-1"
                  aria-label="Clear input"
                  title="Clear input"
                >
                  <CircleX size={16} />
                </button>
              )}
            </div>
            <button
              type="submit"
              disabled={!inputValue.trim() || isProcessing}
              className="px-4 py-3 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-2xl text-cyan-400 disabled:opacity-30 transition-colors"
              aria-label="Send message"
              title="Send message"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </form>
      </div>
    </ChatErrorBoundary>
  );
}
