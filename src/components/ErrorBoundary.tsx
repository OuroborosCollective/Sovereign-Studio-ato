import React, { ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children?: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: unknown): State {
    const errorInstance = error instanceof Error ? error : new Error(String(error));
    return { hasError: true, error: errorInstance, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
    this.setState({ errorInfo });
    
    const logError = async () => {
      try {
        const { storageService } = await import('../services/storageService');
        const logsJson = await storageService.get('ss_error_log');
        const currentLogs = JSON.parse(logsJson || '[]');
        
        // Ensure message is a string by checking instance or converting
        const errorMessage = error instanceof Error ? error.message : String(error);
        
        currentLogs.push({ 
          time: new Date().toISOString(), 
          context: 'ErrorBoundary', 
          message: errorMessage
        });
        await storageService.set('ss_error_log', JSON.stringify(currentLogs.slice(-50)));
      } catch (e) {
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
                  {this.state.error instanceof Error ? this.state.error.message : String(this.state.error)}
                </div>
              )}
            </div>
            <div className="px-6 py-4 bg-stone-50 border-t border-stone-200 flex justify-end">
              <button
                type="button"
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