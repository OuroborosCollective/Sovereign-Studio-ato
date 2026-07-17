import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface SettingsErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

interface SettingsErrorBoundaryProps {
  children: React.ReactNode;
  onReset?: () => void;
}

/**
 * Error Boundary for Settings Modal
 * Catches errors in the settings panel and provides a safe fallback UI
 */
export class SettingsErrorBoundary extends React.Component<SettingsErrorBoundaryProps, SettingsErrorBoundaryState> {
  constructor(props: SettingsErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<SettingsErrorBoundaryState> {
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    this.setState({
      error,
      errorInfo,
    });

    // Log error for debugging
    console.error('[SettingsErrorBoundary] Caught error:', error, errorInfo);
  }

  handleReset = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
    this.props.onReset?.();
  };

  render(): React.ReactNode {
    if (this.state.hasError) {
      return (
        <div className="settings-error-boundary p-6 bg-red-50 border border-red-200 rounded-xl">
          <div className="flex items-center gap-3 mb-4">
            <AlertTriangle className="text-red-500" size={24} />
            <h3 className="text-lg font-bold text-red-700">Einstellungen konnten nicht geladen werden</h3>
          </div>
          
          <p className="text-sm text-red-600 mb-4">
            Es ist ein Fehler aufgetreten. Provider-Zugänge werden grundsätzlich nicht in dieser Oberfläche gespeichert.
          </p>

          <details className="mb-4 p-3 bg-red-100 rounded-lg">
            <summary className="text-sm font-medium text-red-700 cursor-pointer">
              Fehlerdetails (für Entwickler)
            </summary>
            <pre className="mt-2 text-xs text-red-800 overflow-auto max-h-32">
              {this.state.error?.message}
              {'\n\n'}
              {this.state.errorInfo?.componentStack}
            </pre>
          </details>

          <div className="flex gap-3">
            <button
              onClick={this.handleReset}
              className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
            >
              <RefreshCw size={16} />
              Erneut versuchen
            </button>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-stone-200 hover:bg-stone-300 text-stone-700 rounded-lg transition-colors"
            >
              Seite neu laden
            </button>
          </div>

          <div className="mt-4 p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
            <p className="text-sm text-emerald-700">
              <strong>💡 Hinweis:</strong> Online-Modelle laufen ausschließlich über das Sovereign Backend und das private LiteLLM.
            </p>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

/**
 * Safe wrapper for settings that gracefully handles errors
 */
export function withSettingsErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  fallbackProps?: Partial<P>
): React.FC<P> {
  const WrappedComponent: React.FC<P> = (props) => {
    return (
      <SettingsErrorBoundary>
        <Component {...props} {...fallbackProps} />
      </SettingsErrorBoundary>
    );
  };

  WrappedComponent.displayName = `withSettingsErrorBoundary(${Component.displayName || Component.name})`;

  return WrappedComponent;
}
