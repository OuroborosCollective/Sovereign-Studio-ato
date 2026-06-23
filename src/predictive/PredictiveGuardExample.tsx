/**
 * Predictive Guard Integration Examples
 *
 * Shows how to integrate the predictive guard with real UI components.
 *
 * @module predictive/examples
 */

import React, { useState, useCallback } from 'react';
import { usePredictiveGuard, usePredictiveLayer } from './index';

// ============================================================================
// Example 1: Build Button with Safety Check
// ============================================================================

/**
 * Build button that checks prediction safety before executing.
 */
export function PredictiveBuildButton() {
  const { checkSafety, isChecking, isLowConfidence, snapshot } = usePredictiveGuard();
  const [buildStatus, setBuildStatus] = useState<'idle' | 'checking' | 'blocked' | 'warning' | 'building'>('idle');

  const handleBuild = useCallback(async () => {
    setBuildStatus('checking');
    
    const result = await checkSafety('build', {
      action: 'build',
      nodeId: 'runtime.container.build',
      metadata: { context: 'user-initiated' },
    });

    if (result.suggestedAction === 'block') {
      setBuildStatus('blocked');
      alert(`🚫 Build Blocked\n\n${result.reason}\n\nConfidence: ${(result.confidence * 100).toFixed(0)}%`);
      return;
    }

    if (result.suggestedAction === 'warn') {
      setBuildStatus('warning');
      const confirmed = confirm(`⚠️ Build Warning\n\n${result.reason}\n\nConfidence: ${(result.confidence * 100).toFixed(0)}%\n\nProceed anyway?`);
      if (!confirmed) {
        setBuildStatus('idle');
        return;
      }
    }

    // Proceed with build
    setBuildStatus('building');
    console.log('Build proceeding...');
    
    // Simulate build
    setTimeout(() => {
      setBuildStatus('idle');
    }, 2000);
  }, [checkSafety]);

  return (
    <div className="predictive-build-button">
      {/* Confidence indicator */}
      <div className="confidence-bar" style={{ width: `${snapshot.avgConfidence * 100}%` }} />
      
      
      <button 
        onClick={handleBuild}
        disabled={isChecking || buildStatus === 'checking'}
        className={`build-button ${buildStatus}`}
      >
        {isChecking || buildStatus === 'checking' ? '🔮 Checking...' : '🚀 Build'}
      </button>
      
      {/* Status badge */}
      {buildStatus === 'blocked' && <span className="badge danger">Blocked</span>}
      {buildStatus === 'warning' && <span className="badge warning">Warning</span>}
      {buildStatus === 'building' && <span className="badge info">Building...</span>}
    </div>
  );
}

// ============================================================================
// Example 2: Publish Flow with Safety Gate
// ============================================================================

/**
 * Publish button that gates on prediction confidence.
 */
export function PredictivePublishButton() {
  const { canProceed, checkSafety, snapshot } = usePredictiveGuard();
  const [publishing, setPublishing] = useState(false);

  const handlePublish = useCallback(async () => {
    setPublishing(true);
    
    try {
      const result = await checkSafety('publish', {
        action: 'publish',
        nodeId: 'runtime.container.publish',
        metadata: { type: 'draft-pr' },
      });

      if (!result.safe) {
        alert(`Publish not recommended:\n${result.reason}`);
        return;
      }

      // Proceed with publish
      console.log('Publishing...', result);
    } finally {
      setPublishing(false);
    }
  }, [checkSafety]);

  return (
    <button onClick={handlePublish} disabled={publishing}>
      {snapshot.avgConfidence < 0.5 ? '⚠️ Publish (Low Confidence)' : '📤 Publish'}
    </button>
  );
}

// ============================================================================
// Example 3: Runtime Health Dashboard Widget
// ============================================================================

/**
 * Widget showing predictive layer health status.
 */
export function PredictiveHealthWidget() {
  const { snapshot, stats, isActive, confidence, errorRate } = usePredictiveLayer();

  const getStatusColor = () => {
    if (errorRate > 0.2) return 'red';
    if (confidence < 0.3) return 'orange';
    if (confidence > 0.7) return 'green';
    return 'yellow';
  };

  const getStatusText = () => {
    if (!isActive) return 'Inactive';
    if (errorRate > 0.2) return 'High Error Rate';
    if (confidence < 0.3) return 'Learning';
    if (confidence > 0.7) return 'Confident';
    return 'Monitoring';
  };

  return (
    <div className="predictive-health-widget">
      <div className="health-header">
        <span className="health-icon">{isActive ? '🧠' : '💤'}</span>
        <span>Predictive Layer</span>
        <span className={`status-badge ${getStatusColor()}`}>
          {getStatusText()}
        </span>
      </div>

      <div className="health-metrics">
        <div className="metric">
          <label>Confidence</label>
          <div className="metric-bar">
            <div 
              className="metric-fill" 
              style={{ width: `${confidence * 100}%` }}
            />
          </div>
          <span>{(confidence * 100).toFixed(0)}%</span>
        </div>

        <div className="metric">
          <label>Error Rate</label>
          <div className="metric-bar">
            <div 
              className={`metric-fill ${errorRate > 0.1 ? 'error' : ''}`}
              style={{ width: `${Math.min(errorRate * 100, 100)}%` }}
            />
          </div>
          <span>{(errorRate * 100).toFixed(1)}%</span>
        </div>

        <div className="metric">
          <label>Patterns</label>
          <span>{snapshot.patternCount}</span>
        </div>

        <div className="metric">
          <label>Synapses</label>
          <span>{snapshot.synapseCount}</span>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Example 4: Guard Decision Feedback
// ============================================================================

/**
 * Component that shows recent guard decisions and learning.
 */
export function GuardDecisionLog() {
  const { stats, lastResult } = usePredictiveGuard();

  if (!lastResult) {
    return (
      <div className="guard-log empty">
        <p>No recent guard decisions.</p>
      </div>
    );
  }

  return (
    <div className="guard-log">
      <h4>Latest Decision</h4>
      
      <div className={`decision-card ${lastResult.riskLevel}`}>
        <div className="decision-header">
          <span className={`badge ${lastResult.riskLevel}`}>
            {lastResult.suggestedAction.toUpperCase()}
          </span>
          <span>{lastResult.confidence.toFixed(2)} confidence</span>
        </div>
        
        <p className="decision-reason">{lastResult.reason}</p>
        
        <div className="decision-details">
          <span>Success prob: {(lastResult.successProbability * 100).toFixed(0)}%</span>
          <span>Similar patterns: {lastResult.similarPatterns.length}</span>
        </div>
      </div>

      {stats && (
        <div className="guard-stats">
          <h4>Guard Statistics</h4>
          <ul>
            <li>Total decisions: {stats.totalDecisions}</li>
            <li>Blocked: {stats.blockedCount}</li>
            <li>Warnings: {stats.warnedCount}</li>
            <li>Accuracy: {(stats.accuracy * 100).toFixed(0)}%</li>
          </ul>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Example 5: Error Prevention Warning
// ============================================================================

/**
 * Warning banner when predictive layer detects potential issues.
 */
export function PredictiveWarningBanner() {
  const { snapshot, isLowConfidence, isHighErrorRate } = usePredictiveLayer();

  if (!isLowConfidence && !isHighErrorRate) {
    return null;
  }

  return (
    <div className={`predictive-warning ${isHighErrorRate ? 'critical' : 'warning'}`}>
      <span className="warning-icon">⚠️</span>
      
      <div className="warning-content">
        <strong>Predictive Layer Alert</strong>
        
        {isHighErrorRate && (
          <p>
            High error rate detected ({snapshot.errorRate.toFixed(2)}).
            The system is learning from recent failures.
          </p>
        )}
        
        {isLowConfidence && (
          <p>
            Low prediction confidence ({snapshot.avgConfidence.toFixed(2)}).
            More data needed for accurate predictions.
          </p>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Default Export: All Examples
// ============================================================================

export const PredictiveExamples = {
  PredictiveBuildButton,
  PredictivePublishButton,
  PredictiveHealthWidget,
  GuardDecisionLog,
  PredictiveWarningBanner,
};
