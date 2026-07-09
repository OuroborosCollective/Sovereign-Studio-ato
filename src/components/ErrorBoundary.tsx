import React, { ErrorInfo, ReactNode } from 'react';
import { maskSecrets } from '../shared/utils/crypto';

interface Props {
  children?: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  errorKind: 'partial_hydration' | 'runtime_crash' | 'unknown';
}

function toMaskedError(error: unknown): Error {
  const rawMessage = error instanceof Error ? error.message : String(error);
  const masked = new Error(maskSecrets(rawMessage));
  masked.name = error instanceof Error ? error.name : 'Error';
  return masked;
}

/**
 * Detects whether an error likely originated from a partial hydration / stale-state
 * mismatch rather than a hard logic crash. Used to show a more specific recovery hint.
 */
function classifyError(error: Error): State['errorKind'] {
  const msg = error.message.toLowerCase();
  const name = error.name.toLowerCase();
  if (
    msg.includes('hydrat') ||
    msg.includes('snapshot') ||
    msg.includes('cannot read properties of null') ||
    msg.includes('undefined is not an object') ||
    msg.includes('reading \'branch\'') ||
    msg.includes('reading \'owner\'') ||
    msg.includes('reading \'repo\'') ||
    msg.includes('reading \'remoteur') ||
    name.includes('typeerror')
  ) {
    return 'partial_hydration';
  }
  if (msg.includes('chunk') || msg.includes('loading') || msg.includes('import')) {
    return 'unknown';
  }
  return 'runtime_crash';
}

const STYLES = {
  overlay: {
    minHeight: '100dvh',
    background: '#0e1116',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '16px',
    fontFamily: 'system-ui, sans-serif',
  } satisfies React.CSSProperties,
  card: {
    maxWidth: 420,
    width: '100%',
    background: '#161c24',
    border: '1px solid #232d3a',
    borderRadius: 16,
    overflow: 'hidden',
  } satisfies React.CSSProperties,
  body: {
    padding: '24px 24px 20px',
  } satisfies React.CSSProperties,
  icon: {
    fontSize: 28,
    marginBottom: 12,
  } satisfies React.CSSProperties,
  title: {
    fontSize: 16,
    fontWeight: 700,
    color: '#cdd9e5',
    marginBottom: 8,
  } satisfies React.CSSProperties,
  subtitle: {
    fontSize: 13,
    color: '#768390',
    lineHeight: 1.5,
    marginBottom: 0,
  } satisfies React.CSSProperties,
  errorBox: {
    marginTop: 16,
    padding: '10px 12px',
    background: '#0e1116',
    border: '1px solid #232d3a',
    borderRadius: 8,
    fontSize: 11,
    fontFamily: 'monospace',
    color: '#fb7185',
    wordBreak: 'break-word' as const,
    maxHeight: 100,
    overflowY: 'auto' as const,
  } satisfies React.CSSProperties,
  footer: {
    padding: '14px 24px',
    background: '#0e1116',
    borderTop: '1px solid #232d3a',
    display: 'flex',
    justifyContent: 'flex-end',
    gap: 8,
  } satisfies React.CSSProperties,
  btn: (accent: string) => ({
    padding: '8px 16px',
    borderRadius: 8,
    background: `${accent}20`,
    border: `1px solid ${accent}50`,
    color: accent,
    fontSize: 13,
    fontWeight: 500,
    cursor: 'pointer',
  }) satisfies React.CSSProperties,
};

export class ErrorBoundary extends React.Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
    errorKind: 'unknown',
  };

  public static getDerivedStateFromError(error: unknown): Partial<State> {
    const maskedError = toMaskedError(error);
    return {
      hasError: true,
      error: maskedError,
      errorInfo: null,
      errorKind: classifyError(maskedError),
    };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    const maskedError = toMaskedError(error);
    console.error('[GHOST_PILOT_FAILURE] UI_CRASH_DETECTED:', maskedError.message);
    this.setState({ errorInfo });

    const logError = async () => {
      try {
        const { storageService } = await import('../shared/api/storageService');
        const logsJson = await storageService.get('ss_error_log');
        let currentLogs: Array<{ time: string; context: string; message: string }> = [];
        try { currentLogs = JSON.parse(String(logsJson || '[]')); } catch { currentLogs = []; }
        currentLogs.push({ time: new Date().toISOString(), context: 'ErrorBoundary', message: maskedError.message });
        await storageService.set('ss_error_log', JSON.stringify(currentLogs.slice(-50)));
      } catch {
        // Storage nicht verfügbar — Logging überspringen
      }
    };
    logError();
  }

  private handleReload = () => { window.location.reload(); };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      const { errorKind, error } = this.state;
      const isPartial = errorKind === 'partial_hydration';

      const title = isPartial
        ? 'Unvollständiger Zustand erkannt'
        : 'Unerwarteter Fehler';

      const subtitle = isPartial
        ? 'Ein Repo-Snapshot oder ein anderer Runtime-Zustand wurde nur teilweise geladen. Die Anzeige würde erfundenen State zeigen. Bitte Seite neu laden — es werden keine Daten gelöscht.'
        : 'Ein Fehler ist in der UI aufgetreten. Die Runtime-Wahrheit ist intakt. Bitte Seite neu laden.';

      const icon = isPartial ? '⚠️' : '🛑';
      const accentColor = isPartial ? '#fbbf24' : '#fb7185';

      return (
        <div style={STYLES.overlay}>
          <div style={STYLES.card}>
            <div style={STYLES.body}>
              <div style={STYLES.icon}>{icon}</div>
              <div style={STYLES.title}>{title}</div>
              <p style={STYLES.subtitle}>{subtitle}</p>
              {error && (
                <div style={STYLES.errorBox}>
                  {error.name}: {error.message}
                </div>
              )}
            </div>
            <div style={STYLES.footer}>
              <button
                type="button"
                onClick={this.handleReload}
                style={STYLES.btn(accentColor)}
              >
                Seite neu laden
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children ?? null;
  }
}
