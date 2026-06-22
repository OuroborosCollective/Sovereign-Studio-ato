import React from 'react';

export type LlmFlowStep = 
  | 'idle'
  | 'memory_search'
  | 'llm_provider_connecting'
  | 'llm_provider_trying'
  | 'llm_provider_success'
  | 'llm_provider_failed'
  | 'llm_parse_result'
  | 'guard_validation'
  | 'guard_passed'
  | 'guard_failed'
  | 'package_build'
  | 'pattern_learning'
  | 'complete'
  | 'error';

export interface LlmFlowStepInfo {
  step: LlmFlowStep;
  label: string;
  description: string;
  icon: string;
  status: 'pending' | 'active' | 'success' | 'error';
  provider?: string;
  error?: string;
}

export interface LlmFlowState {
  isActive: boolean;
  currentStep: LlmFlowStep;
  steps: LlmFlowStepInfo[];
  attempts: Array<{
    provider: string;
    status: 'trying' | 'success' | 'failed';
    timestamp: number;
  }>;
  startedAt: number | null;
  completedAt: number | null;
  error: string | null;
}

const FLOW_STEPS: LlmFlowStepInfo[] = [
  {
    step: 'memory_search',
    label: 'Remote Memory',
    description: 'Suche nach ähnlichen Patterns...',
    icon: '🧠',
    status: 'pending',
  },
  {
    step: 'llm_provider_connecting',
    label: 'Provider verbinden',
    description: 'Verbinde mit LLM-Anbieter...',
    icon: '🔗',
    status: 'pending',
  },
  {
    step: 'llm_provider_trying',
    label: 'LLM-Anfrage',
    description: 'Sende Anfrage an LLM...',
    icon: '🤖',
    status: 'pending',
  },
  {
    step: 'llm_parse_result',
    label: 'Ergebnis analysieren',
    description: 'Parse LLM-Antwort...',
    icon: '📝',
    status: 'pending',
  },
  {
    step: 'guard_validation',
    label: 'Guard-Validierung',
    description: 'Prüfe Brain-Validierung...',
    icon: '🛡️',
    status: 'pending',
  },
  {
    step: 'guard_passed',
    label: 'Guards bestanden',
    description: 'Alle Guards erfolgreich...',
    icon: '✅',
    status: 'pending',
  },
  {
    step: 'package_build',
    label: 'Package erstellen',
    description: 'Baue Implementation...',
    icon: '📦',
    status: 'pending',
  },
  {
    step: 'pattern_learning',
    label: 'Pattern lernen',
    description: 'Speichere für zukünftige Nutzung...',
    icon: '💡',
    status: 'pending',
  },
  {
    step: 'complete',
    label: 'Abgeschlossen',
    description: 'Package erfolgreich erstellt!',
    icon: '🎉',
    status: 'pending',
  },
];

export function createInitialLlmFlowState(): LlmFlowState {
  return {
    isActive: false,
    currentStep: 'idle',
    steps: FLOW_STEPS.map(s => ({ ...s })),
    attempts: [],
    startedAt: null,
    completedAt: null,
    error: null,
  };
}

export function updateLlmFlowStep(state: LlmFlowState, step: LlmFlowStep, data?: Partial<LlmFlowStepInfo>): LlmFlowState {
  const newSteps = state.steps.map(s => {
    if (s.step === step) {
      return { ...s, ...data, status: 'active' as const };
    }
    return s;
  });

  return {
    ...state,
    currentStep: step,
    steps: newSteps,
    isActive: step !== 'idle' && step !== 'complete' && step !== 'error',
  };
}

export function completeLlmFlowStep(state: LlmFlowState, step: LlmFlowStep, success: boolean): LlmFlowState {
  const newSteps = state.steps.map(s => {
    if (s.step === step) {
      return { ...s, status: success ? 'success' : 'error' as const };
    }
    return s;
  });

  return {
    ...state,
    steps: newSteps,
  };
}

export function addLlmAttempt(state: LlmFlowState, provider: string, status: 'trying' | 'success' | 'failed'): LlmFlowState {
  return {
    ...state,
    attempts: [...state.attempts, { provider, status, timestamp: Date.now() }],
  };
}

export function LlmFlowVisualizer({ state }: { state: LlmFlowState }) {
  const getStatusColor = (status: LlmFlowStepInfo['status']) => {
    switch (status) {
      case 'success': return 'text-emerald-500';
      case 'error': return 'text-red-500';
      case 'active': return 'text-blue-500 animate-pulse';
      default: return 'text-stone-500';
    }
  };

  const getStatusBg = (status: LlmFlowStepInfo['status']) => {
    switch (status) {
      case 'success': return 'bg-emerald-500/20';
      case 'error': return 'bg-red-500/20';
      case 'active': return 'bg-blue-500/20';
      default: return 'bg-stone-800/50';
    }
  };

  const formatDuration = (start: number | null, end: number | null) => {
    if (!start) return '';
    const duration = (end || Date.now()) - start;
    return `${(duration / 1000).toFixed(1)}s`;
  };

  if (!state.isActive && state.currentStep === 'idle') {
    return (
      <div className="llm-flow-visualizer p-4 bg-stone-900/50 rounded-xl border border-stone-700">
        <p className="text-stone-500 text-sm">Warte auf Package-Build...</p>
      </div>
    );
  }

  return (
    <div className="llm-flow-visualizer p-4 bg-stone-900/80 rounded-xl border border-stone-600">
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-sm font-bold text-stone-300 flex items-center gap-2">
          <span className="text-lg">🔄</span>
          LLM Runtime Flow
          {state.startedAt && (
            <span className="text-xs text-stone-500">
              {formatDuration(state.startedAt, state.completedAt)}
            </span>
          )}
        </h4>
        {state.error && (
          <span className="text-xs text-red-400 bg-red-500/20 px-2 py-1 rounded">
            ⚠️ {state.error}
          </span>
        )}
      </div>

      {/* Provider Attempts */}
      {state.attempts.length > 0 && (
        <div className="mb-4 p-2 bg-stone-800/50 rounded-lg">
          <p className="text-xs text-stone-400 mb-2">Provider-Versuche:</p>
          <div className="flex flex-wrap gap-2">
            {state.attempts.map((attempt, i) => (
              <span
                key={i}
                className={`text-xs px-2 py-1 rounded ${
                  attempt.status === 'success' ? 'bg-emerald-500/30 text-emerald-400' :
                  attempt.status === 'failed' ? 'bg-red-500/30 text-red-400' :
                  'bg-blue-500/30 text-blue-400'
                }`}
              >
                {attempt.status === 'trying' ? '⏳' : attempt.status === 'success' ? '✅' : '❌'}
                {' '}{attempt.provider}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Steps */}
      <div className="space-y-2">
        {state.steps.map((step, i) => (
          <div
            key={step.step}
            className={`flex items-center gap-3 p-2 rounded-lg transition-all ${getStatusBg(step.status)}`}
          >
            <span className={`text-lg ${getStatusColor(step.status)}`}>{step.icon}</span>
            <div className="flex-1">
              <p className={`text-sm font-medium ${getStatusColor(step.status)}`}>
                {step.label}
              </p>
              <p className="text-xs text-stone-500">{step.description}</p>
            </div>
            {step.status === 'success' && <span className="text-emerald-500">✓</span>}
            {step.status === 'error' && <span className="text-red-500">✗</span>}
            {step.status === 'active' && (
              <span className="inline-block w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            )}
          </div>
        ))}
      </div>

      {/* Error State */}
      {state.currentStep === 'error' && state.error && (
        <div className="mt-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg">
          <p className="text-sm text-red-300">
            <strong>Fehler:</strong> {state.error}
          </p>
          <p className="text-xs text-stone-400 mt-2">
            Das System fällt automatisch auf local-safe zurück.
          </p>
        </div>
      )}

      {/* Complete State */}
      {state.currentStep === 'complete' && (
        <div className="mt-4 p-3 bg-emerald-500/20 border border-emerald-500/50 rounded-lg">
          <p className="text-sm text-emerald-300">
            ✅ Package erfolgreich erstellt und Pattern gespeichert!
          </p>
          {state.completedAt && state.startedAt && (
            <p className="text-xs text-stone-400 mt-1">
              Gesamtdauer: {((state.completedAt - state.startedAt) / 1000).toFixed(1)}s
            </p>
          )}
        </div>
      )}
    </div>
  );
}