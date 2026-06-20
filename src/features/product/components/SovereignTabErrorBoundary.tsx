import React, { ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, X, RefreshCw } from 'lucide-react';
import { maskSecrets } from '../../../shared/utils/crypto';
import {
  DEFAULT_SOVEREIGN_CIRCUIT_POLICY,
  canAttemptSovereignCircuit,
  createSovereignCircuitState,
  recordSovereignCircuitAttempt,
  recordSovereignCircuitFailure,
  refreshSovereignCircuitState,
  summarizeSovereignCircuit,
  type SovereignCircuitPolicy,
  type SovereignCircuitState,
} from '../runtime/sovereignCircuitLifecycle';

interface Props {
  tabId: string;
  tabLabel: string;
  children?: ReactNode;
  onDismiss?: () => void;
  policy?: Partial<SovereignCircuitPolicy>;
  nowMs?: () => number;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  circuit: SovereignCircuitState;
  renderNonce: number;
}

function toMaskedError(error: unknown): Error {
  const rawMessage = error instanceof Error ? error.message : String(error);
  const masked = new Error(maskSecrets(rawMessage));
  masked.name = error instanceof Error ? error.name : 'Error';
  return masked;
}

function emitCoachSignal(tabId: string, tabLabel: string, circuit: SovereignCircuitState, error: Error | null): void {
  if (typeof window === 'undefined') return;

  const message = error?.message ?? summarizeSovereignCircuit(circuit);
  const phase = circuit.phase;

  window.dispatchEvent(new CustomEvent('sovereign:tab-boundary-state', {
    detail: {
      tabId,
      tabLabel,
      phase,
      failures: circuit.failures,
      message,
      summary: summarizeSovereignCircuit(circuit),
    },
  }));

  window.dispatchEvent(new CustomEvent('sovereign:runtime-coach-state', {
    detail: {
      lamp: phase === 'open' ? 'red' : 'yellow',
      title: phase === 'open' ? `${tabLabel} pausiert` : `${tabLabel} gesichert`,
      message: phase === 'open'
        ? `${tabLabel} ist mehrfach fehlgeschlagen. Der restliche Ablauf bleibt nutzbar.`
        : `${tabLabel} wurde isoliert: ${message}`,
      action: phase === 'open' ? 'Kurz warten oder Tab wechseln.' : 'Retry oder Tab wechseln.',
      thinking: false,
      source: 'runtime-library',
      updatedAt: Date.now(),
    },
  }));
}

export class SovereignTabErrorBoundary extends React.Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
    circuit: createSovereignCircuitState(`tab:${this.props.tabId}`),
    renderNonce: 0,
  };

  public static getDerivedStateFromError(error: unknown): Partial<State> {
    const maskedError = toMaskedError(error);
    console.error(`[TAB_ERROR] ${maskedError.message}`);
    return { hasError: true, error: maskedError };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    const maskedError = toMaskedError(error);
    const transition = recordSovereignCircuitFailure(this.state.circuit, this.policy(), this.now());

    console.error(`[TAB_CAUGHT] ${this.props.tabId}: ${maskedError.message}`, maskSecrets(errorInfo.componentStack ?? ''));
    this.setState({ error: maskedError, errorInfo, circuit: transition.state });
    emitCoachSignal(this.props.tabId, this.props.tabLabel, transition.state, maskedError);
  }

  public componentDidUpdate(prevProps: Props): void {
    if (prevProps.tabId !== this.props.tabId) {
      this.setState({
        hasError: false,
        error: null,
        errorInfo: null,
        circuit: createSovereignCircuitState(`tab:${this.props.tabId}`),
        renderNonce: 0,
      });
    }
  }

  private now(): number {
    return this.props.nowMs?.() ?? Date.now();
  }

  private policy(): SovereignCircuitPolicy {
    return {
      ...DEFAULT_SOVEREIGN_CIRCUIT_POLICY,
      ...this.props.policy,
    };
  }

  private handleDismiss = () => {
    this.props.onDismiss?.();
  };

  private handleRetry = () => {
    const refreshed = refreshSovereignCircuitState(this.state.circuit, this.policy(), this.now()).state;

    if (!canAttemptSovereignCircuit(refreshed, this.policy(), this.now())) {
      this.setState({ circuit: refreshed });
      emitCoachSignal(this.props.tabId, this.props.tabLabel, refreshed, this.state.error);
      return;
    }

    const attempted = recordSovereignCircuitAttempt(refreshed, this.policy(), this.now()).state;
    this.setState((state) => ({
      hasError: false,
      error: null,
      errorInfo: null,
      circuit: attempted,
      renderNonce: state.renderNonce + 1,
    }));
  };

  public render() {
    const refreshed = refreshSovereignCircuitState(this.state.circuit, this.policy(), this.now()).state;

    if (refreshed !== this.state.circuit) {
      window.setTimeout(() => this.setState({ circuit: refreshed }), 0);
    }

    if (this.state.hasError || refreshed.phase === 'open') {
      const retryAllowed = canAttemptSovereignCircuit(refreshed, this.policy(), this.now());
      const title = refreshed.phase === 'open'
        ? `${this.props.tabLabel} tab paused`
        : `${this.props.tabLabel} tab crashed`;

      return (
        <div
          className="p-4 m-2 bg-stone-900/80 rounded-lg border border-stone-700"
          data-testid="sovereign-tab-error-boundary"
          data-tab-id={this.props.tabId}
          data-circuit-phase={refreshed.phase}
        >
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2 text-amber-400">
              <AlertTriangle size={16} />
              <span className="text-sm font-medium">{title}</span>
            </div>
            {this.props.onDismiss && (
              <button
                onClick={this.handleDismiss}
                className="p-1 hover:bg-stone-700 rounded transition-colors"
                aria-label="Dismiss error"
                type="button"
              >
                <X size={14} className="text-stone-400" />
              </button>
            )}
          </div>

          {this.state.error && (
            <div className="mt-2 text-xs font-mono text-stone-400 truncate">
              {this.state.error.message}
            </div>
          )}

          <div className="mt-2 text-[11px] font-mono text-stone-500">
            {summarizeSovereignCircuit(refreshed)}
          </div>

          <button
            type="button"
            aria-label="Retry tab"
            disabled={!retryAllowed}
            onClick={this.handleRetry}
            className="mt-3 inline-flex items-center gap-2 rounded border border-amber-500/40 px-3 py-1 text-xs text-amber-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw size={13} />
            Retry tab
          </button>
        </div>
      );
    }

    return <React.Fragment key={this.state.renderNonce}>{this.props.children || null}</React.Fragment>;
  }
}
