import React, { ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { maskSecrets } from '../../../shared/utils/crypto';
import {
  DEFAULT_SOVEREIGN_CIRCUIT_POLICY,
  canAttemptSovereignCircuit,
  createSovereignCircuitState,
  recordSovereignCircuitAttempt,
  recordSovereignCircuitFailure,
  recordSovereignCircuitSuccess,
  refreshSovereignCircuitState,
  summarizeSovereignCircuit,
  type SovereignCircuitPhase,
  type SovereignCircuitPolicy,
  type SovereignCircuitState,
} from '../runtime/sovereignCircuitLifecycle';

export interface SovereignTabBoundaryEvent {
  tabId: string;
  tabLabel: string;
  phase: SovereignCircuitPhase;
  failures: number;
  message: string;
  summary: string;
}

interface Props {
  tabId: string;
  tabLabel?: string;
  children: ReactNode;
  policy?: Partial<SovereignCircuitPolicy>;
  nowMs?: () => number;
  onRuntimeEvent?: (event: SovereignTabBoundaryEvent) => void;
  onOpenTelemetry?: () => void;
}

interface State {
  hasError: boolean;
  errorMessage: string;
  circuit: SovereignCircuitState;
  renderNonce: number;
}

function eventMessage(tabLabel: string, message: string): string {
  return `${tabLabel} Tab wurde isoliert: ${message}`.slice(0, 500);
}

function normalizeErrorMessage(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  const masked = maskSecrets(raw);
  return masked.trim() || 'Unbekannter Tab-Fehler.';
}

function publishRuntimeCoachEvent(event: SovereignTabBoundaryEvent): void {
  if (typeof window === 'undefined') return;

  window.dispatchEvent(new CustomEvent('sovereign:tab-boundary-state', { detail: event }));
  window.dispatchEvent(new CustomEvent('sovereign:runtime-coach-state', {
    detail: {
      lamp: event.phase === 'open' ? 'red' : 'yellow',
      title: event.phase === 'open' ? `${event.tabLabel} pausiert` : `${event.tabLabel} gesichert`,
      message: event.message,
      action: event.phase === 'open' ? 'Telemetry pruefen oder spaeter Retry.' : 'Tab neu versuchen oder Telemetry oeffnen.',
      thinking: false,
      source: 'runtime-library',
      updatedAt: Date.now(),
    },
  }));
}

export class SovereignTabErrorBoundary extends React.Component<Props, State> {
  public state: State = {
    hasError: false,
    errorMessage: '',
    circuit: createSovereignCircuitState(`tab:${this.props.tabId}`),
    renderNonce: 0,
  };

  public static getDerivedStateFromError(error: unknown): Partial<State> {
    return {
      hasError: true,
      errorMessage: normalizeErrorMessage(error),
    };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    const message = normalizeErrorMessage(error);
    const now = this.now();
    const transition = recordSovereignCircuitFailure(this.state.circuit, this.props.policy, now);

    this.setState({ circuit: transition.state, errorMessage: message });
    this.emitBoundaryEvent(transition.state, message);

    console.error('[SOVEREIGN_TAB_BOUNDARY]', this.props.tabId, message, maskSecrets(errorInfo.componentStack ?? ''));
  }

  public componentDidUpdate(prevProps: Props, prevState: State): void {
    if (prevProps.tabId !== this.props.tabId) {
      this.setState({
        hasError: false,
        errorMessage: '',
        circuit: createSovereignCircuitState(`tab:${this.props.tabId}`),
        renderNonce: 0,
      });
      return;
    }

    if (!this.state.hasError && prevState.hasError) {
      const transition = recordSovereignCircuitSuccess(this.state.circuit);
      if (transition.changed) {
        this.setState({ circuit: transition.state });
        this.emitBoundaryEvent(transition.state, transition.reason);
      }
    }
  }

  private now(): number {
    return this.props.nowMs?.() ?? Date.now();
  }

  private tabLabel(): string {
    return this.props.tabLabel?.trim() || this.props.tabId;
  }

  private policy(): SovereignCircuitPolicy {
    return {
      ...DEFAULT_SOVEREIGN_CIRCUIT_POLICY,
      ...this.props.policy,
    };
  }

  private emitBoundaryEvent(circuit: SovereignCircuitState, message: string): void {
    const event: SovereignTabBoundaryEvent = {
      tabId: this.props.tabId,
      tabLabel: this.tabLabel(),
      phase: circuit.phase,
      failures: circuit.failures,
      message: eventMessage(this.tabLabel(), message),
      summary: summarizeSovereignCircuit(circuit),
    };

    this.props.onRuntimeEvent?.(event);
    publishRuntimeCoachEvent(event);
  }

  private handleRetry = (): void => {
    const refreshed = refreshSovereignCircuitState(this.state.circuit, this.policy(), this.now()).state;

    if (!canAttemptSovereignCircuit(refreshed, this.policy(), this.now())) {
      this.setState({ circuit: refreshed });
      this.emitBoundaryEvent(refreshed, 'Circuit cooldown ist noch aktiv.');
      return;
    }

    const attempted = recordSovereignCircuitAttempt(refreshed, this.policy(), this.now()).state;
    this.setState((state) => ({
      hasError: false,
      errorMessage: '',
      circuit: attempted,
      renderNonce: state.renderNonce + 1,
    }));
  };

  private renderFallback(circuit: SovereignCircuitState): React.ReactElement {
    const tabLabel = this.tabLabel();
    const canRetry = canAttemptSovereignCircuit(circuit, this.policy(), this.now());
    const title = circuit.phase === 'open'
      ? `${tabLabel} ist kurz pausiert`
      : `${tabLabel} wurde abgesichert`;
    const body = circuit.phase === 'open'
      ? 'Der Bereich ist mehrfach fehlgeschlagen. Der Circuit bleibt kurz offen, damit der restliche Ablauf stabil bleibt.'
      : 'Nur dieser Bereich ist abgestuerzt. Repo, Builder, Workflow und Coach bleiben weiter nutzbar.';

    return (
      <section
        className="mt-4 rounded border border-amber-500/50 bg-amber-950/20 p-4 text-sm text-amber-100"
        data-testid="sovereign-tab-error-boundary"
        data-tab-id={this.props.tabId}
        data-circuit-phase={circuit.phase}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 font-bold text-amber-200">
              <AlertTriangle size={16} />
              <span>{title}</span>
            </div>
            <p className="mt-2 text-xs text-amber-100/80">{body}</p>
          </div>
          <div className="rounded bg-black/30 px-2 py-1 text-[11px] uppercase tracking-wide text-amber-200">
            {circuit.phase} · {circuit.failures} failure(s)
          </div>
        </div>

        {this.state.errorMessage ? (
          <pre className="mt-3 max-h-32 overflow-auto rounded border border-amber-500/30 bg-black/40 p-3 text-xs text-amber-50 whitespace-pre-wrap">
            {this.state.errorMessage}
          </pre>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            className="inline-flex items-center gap-2 rounded border border-amber-300/50 bg-amber-400/10 px-3 py-2 text-xs font-bold text-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!canRetry}
            onClick={this.handleRetry}
            type="button"
          >
            <RefreshCw size={14} />
            Tab neu versuchen
          </button>
          <button
            className="rounded border border-slate-400/40 bg-slate-900/60 px-3 py-2 text-xs font-bold text-slate-100"
            onClick={this.props.onOpenTelemetry}
            type="button"
          >
            Telemetry oeffnen
          </button>
        </div>
      </section>
    );
  }

  public render(): React.ReactNode {
    const refreshed = refreshSovereignCircuitState(this.state.circuit, this.policy(), this.now()).state;

    if (refreshed !== this.state.circuit) {
      window.setTimeout(() => this.setState({ circuit: refreshed }), 0);
    }

    if (this.state.hasError || refreshed.phase === 'open') {
      return this.renderFallback(refreshed);
    }

    return <React.Fragment key={this.state.renderNonce}>{this.props.children}</React.Fragment>;
  }
}
