import React, { ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { maskSecrets } from '../shared/utils/crypto';

interface Props {
  children?: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

function toMaskedError(error: unknown): Error {
  const rawMessage = error instanceof Error ? error.message : String(error);
  const masked = new Error(maskSecrets(rawMessage));
  masked.name = error instanceof Error ? error.name : 'Error';
  return masked;
}

export class ErrorBoundary extends React.Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: unknown): State {
    const maskedError = toMaskedError(error);
    console.error('[GHOST_PILOT_FAILURE] UI_CRASH_DETECTED:', maskedError.message);
    return { hasError: true, error: maskedError, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    const maskedError = toMaskedError(error);
    console.error('[GHOST_PILOT_FAILURE] CAUGHT_EXCEPTION:', maskedError.message);

    this.setState({ errorInfo });

    const logError = async () => {
      try {
        const { storageService } = await import('../shared/api/storageService');
        const logsJson = await storageService.get('ss_error_log');

        let currentLogs: Array<{time: string, context: string, message: string}> = [];
        try {
          currentLogs = JSON.parse(String(logsJson || '[]'));
        } catch {
          currentLogs = [];
        }

        currentLogs.push({
          time: new Date().toISOString(),
          context: 'ErrorBoundary',
          message: maskedError.message
        });

        await storageService.set('ss_error_log', JSON.stringify(currentLogs.slice(-50)));
      } catch {
        // Silently fail logging if storage service is unavailable
      }
    };
    logError();
  }

  private handleReload = () => {
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-screen bg-stone-50 flex items-center justify-center p-4">
          <div className="max-w-md w-full bg-white rounded-xl shadow-xl overflow-hidden border border-stone-200">
            <div className="p-6">
              <div className="flex items-center justify-center w-12 h-12 rounded-full bg-rose-100 mb-4">
                <AlertTriangle className="text-rose-600" size={24} />
              </div>
              <h2 className="text-xl font-bold text-stone-900 mb-2">Something went wrong</h2>
              <p className="text-sm text-stone-600 mb-4">
                An unexpected error occurred in the application UI. The team has been notified.
              </p>

              {this.state.error && (
                <div className="mt-4 p-3 bg-stone-100 rounded text-xs font-mono text-stone-800 break-words overflow-x-auto max-h-40 border border-stone-200">
                  {this.state.error.message || String(this.state.error)}
                </div>
              )}
            </div>
            <div className="px-6 py-4 bg-stone-50 border-t border-stone-200 flex justify-end">
              <button
                onClick={this.handleReload}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded text-sm font-medium hover:bg-indigo-700 transition-colors"
              >
                <RefreshCw size={14} />
                Reload Application
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children || null;
  }
}
