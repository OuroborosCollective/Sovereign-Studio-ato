import React, { ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { maskSecrets } from '../../../shared/utils/crypto';

interface Props {
  tabId: string;
  tabLabel: string;
  children?: ReactNode;
  onDismiss?: () => void;
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

export class SovereignTabErrorBoundary extends React.Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: unknown): State {
    const maskedError = toMaskedError(error);
    console.error(`[TAB_ERROR] ${maskedError.message}`);
    return { hasError: true, error: maskedError, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    const maskedError = toMaskedError(error);
    console.error(`[TAB_CAUGHT] ${maskedError.message}`, errorInfo);
    this.setState({ errorInfo });
  }

  private handleDismiss = () => {
    this.props.onDismiss?.();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 m-2 bg-stone-900/80 rounded-lg border border-stone-700">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2 text-amber-400">
              <AlertTriangle size={16} />
              <span className="text-sm font-medium">
                {this.props.tabLabel} tab crashed
              </span>
            </div>
            {this.props.onDismiss && (
              <button
                onClick={this.handleDismiss}
                className="p-1 hover:bg-stone-700 rounded transition-colors"
                aria-label="Dismiss error"
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
        </div>
      );
    }

    return this.props.children || null;
  }
}