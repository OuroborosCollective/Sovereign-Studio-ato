/**
 * Predictive Layer UI Components
 *
 * Phase 4.4: Add UI feedback for predictions
 * Visual components for displaying predictive layer status and warnings.
 *
 * @module predictive/ui
 */

import React, { useMemo, useEffect } from 'react';
import type { PredictiveLayerSnapshot, PredictiveMetrics } from '../types';

// ============================================================================
// Types
// ============================================================================

export interface PredictiveConfidenceBarProps {
  confidence: number;
  thresholds?: {
    warning: number;
    danger: number;
  };
  height?: number;
  showText?: boolean;
  className?: string;
}

export interface PredictiveStatusBadgeProps {
  status: 'safe' | 'warning' | 'danger' | 'critical' | 'inactive';
  label?: string;
  size?: 'sm' | 'md' | 'lg';
}

export interface PredictiveHealthIndicatorProps {
  snapshot: PredictiveLayerSnapshot | null;
  metrics: PredictiveMetrics | null;
  detailed?: boolean;
}

export interface PredictiveWarningToastProps {
  message: string;
  confidence: number;
  errorRate: number;
  onDismiss?: () => void;
  autoDismissMs?: number;
}

export interface PredictiveDecisionOverlayProps {
  isChecking: boolean;
  result?: {
    safe: boolean;
    confidence: number;
    reason: string;
    suggestedAction: 'proceed' | 'warn' | 'block' | 'review';
  };
  action: string;
}

// ============================================================================
// Confidence Bar Component
// ============================================================================

export function PredictiveConfidenceBar({
  confidence,
  thresholds = { warning: 0.5, danger: 0.3 },
  height = 8,
  showText = true,
  className = '',
}: PredictiveConfidenceBarProps) {
  const color = useMemo(() => {
    if (confidence < thresholds.danger) return 'var(--color-danger, #dc3545)';
    if (confidence < thresholds.warning) return 'var(--color-warning, #ffc107)';
    return 'var(--color-success, #28a745)';
  }, [confidence, thresholds]);

  const bgColor = useMemo(() => {
    if (confidence < thresholds.danger) return 'rgba(220, 53, 69, 0.2)';
    if (confidence < thresholds.warning) return 'rgba(255, 193, 7, 0.2)';
    return 'rgba(40, 167, 69, 0.2)';
  }, [confidence, thresholds]);

  return (
    <div
      className={`predictive-confidence-bar ${className}`}
      style={{
        height: `${height}px`,
        backgroundColor: bgColor,
        borderRadius: '4px',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      <div
        style={{
          height: '100%',
          width: `${Math.max(0, Math.min(100, confidence * 100))}%`,
          backgroundColor: color,
          transition: 'width 0.3s ease, background-color 0.3s ease',
        }}
      />
      {showText && (
        <span
          style={{
            position: 'absolute',
            right: '4px',
            top: '50%',
            transform: 'translateY(-50%)',
            fontSize: '10px',
            fontWeight: 600,
            color: color,
          }}
        >
          {(confidence * 100).toFixed(0)}%
        </span>
      )}
    </div>
  );
}

// ============================================================================
// Status Badge Component
// ============================================================================

export function PredictiveStatusBadge({
  status,
  label,
  size = 'md',
}: PredictiveStatusBadgeProps) {
  const sizes = {
    sm: { padding: '2px 6px', fontSize: '10px' },
    md: { padding: '4px 10px', fontSize: '12px' },
    lg: { padding: '6px 14px', fontSize: '14px' },
  };

  const statusConfig = {
    safe: { color: '#28a745', bg: 'rgba(40, 167, 69, 0.15)', icon: '✓' },
    warning: { color: '#ffc107', bg: 'rgba(255, 193, 7, 0.15)', icon: '⚠' },
    danger: { color: '#dc3545', bg: 'rgba(220, 53, 69, 0.15)', icon: '✕' },
    critical: { color: '#6f42c1', bg: 'rgba(111, 66, 193, 0.15)', icon: '⚡' },
    inactive: { color: '#6c757d', bg: 'rgba(108, 117, 125, 0.15)', icon: '○' },
  };

  const config = statusConfig[status];
  const sizeStyle = sizes[size];

  return (
    <span
      className={`predictive-status-badge status-${status}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: sizeStyle.padding,
        fontSize: sizeStyle.fontSize,
        fontWeight: 600,
        borderRadius: '12px',
        backgroundColor: config.bg,
        color: config.color,
      }}
    >
      {config.icon} {label ?? status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

// ============================================================================
// Health Indicator Component
// ============================================================================

export function PredictiveHealthIndicator({
  snapshot,
  metrics,
  detailed = false,
}: PredictiveHealthIndicatorProps) {
  const confidence = useMemo(() => {
    if (!snapshot || snapshot.nodes.length === 0) return 0;
    return snapshot.avgConfidence ?? 0;
  }, [snapshot]);

  const errorRate = useMemo(() => {
    if (!metrics || metrics.totalPredictions === 0) return 0;
    return metrics.failedPredictions / metrics.totalPredictions;
  }, [metrics]);

  const status = useMemo(() => {
    if (!snapshot || snapshot.nodes.length === 0) return 'inactive';
    if (confidence < 0.2 || errorRate > 0.35) return 'critical';
    if (confidence < 0.35 || errorRate > 0.2) return 'danger';
    if (confidence < 0.5 || errorRate > 0.1) return 'warning';
    return 'safe';
  }, [confidence, errorRate, snapshot]);

  return (
    <div className="predictive-health-indicator">
      <div className="health-header">
        <PredictiveStatusBadge status={status} label="Predictive" />
      </div>

      <PredictiveConfidenceBar confidence={confidence} className="health-confidence" />

      {detailed && snapshot && (
        <div className="health-metrics">
          <div className="metric-row">
            <span className="metric-label">Error Rate</span>
            <span className="metric-value">{(errorRate * 100).toFixed(1)}%</span>
          </div>
          <div className="metric-row">
            <span className="metric-label">Patterns</span>
            <span className="metric-value">{snapshot.patternCount}</span>
          </div>
          <div className="metric-row">
            <span className="metric-label">Synapses</span>
            <span className="metric-value">{snapshot.synapseCount}</span>
          </div>
          <div className="metric-row">
            <span className="metric-label">Nodes</span>
            <span className="metric-value">{snapshot.nodeCount}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Warning Toast Component
// ============================================================================

export function PredictiveWarningToast({
  message,
  confidence,
  errorRate,
  onDismiss,
  autoDismissMs = 0,
}: PredictiveWarningToastProps) {
  useEffect(() => {
    if (autoDismissMs > 0 && onDismiss) {
      const timer = setTimeout(onDismiss, autoDismissMs);
      return () => clearTimeout(timer);
    }
  }, [autoDismissMs, onDismiss]);

  return (
    <div className="predictive-warning-toast">
      <div className="toast-icon">⚠️</div>
      <div className="toast-content">
        <div className="toast-message">{message}</div>
        <div className="toast-meta">
          Confidence: {(confidence * 100).toFixed(0)}% | Error Rate: {(errorRate * 100).toFixed(1)}%
        </div>
      </div>
      {onDismiss && (
        <button className="toast-dismiss" onClick={onDismiss} aria-label="Dismiss">
          ✕
        </button>
      )}
    </div>
  );
}

// ============================================================================
// Decision Overlay Component
// ============================================================================

export function PredictiveDecisionOverlay({
  isChecking,
  result,
  action,
}: PredictiveDecisionOverlayProps) {
  if (!isChecking && !result) return null;

  const getStatusIcon = () => {
    if (isChecking) return '🔮';
    if (!result) return '';
    switch (result.suggestedAction) {
      case 'block': return '🚫';
      case 'warn': return '⚠️';
      case 'review': return '👀';
      case 'proceed':
      default:
        return '✓';
    }
  };

  const getStatusColor = () => {
    if (!result) return 'var(--color-info, #17a2b8)';
    switch (result.suggestedAction) {
      case 'block': return 'var(--color-danger, #dc3545)';
      case 'warn': return 'var(--color-warning, #ffc107)';
      case 'review': return 'var(--color-info, #17a2b8)';
      case 'proceed':
      default:
        return 'var(--color-success, #28a745)';
    }
  };

  return (
    <div className="predictive-decision-overlay">
      <div className="overlay-content" style={{ borderColor: getStatusColor() }}>
        <div className="overlay-icon" style={{ color: getStatusColor() }}>
          {getStatusIcon()}
        </div>
        <div className="overlay-title">
          {isChecking ? 'Analyzing...' : `Checking ${action}...`}
        </div>
        {result && (
          <div className="overlay-details">
            <div className="detail-row">
              <span>Confidence:</span>
              <span>{(result.confidence * 100).toFixed(0)}%</span>
            </div>
            <div className="detail-row">
              <span>Recommendation:</span>
              <span>{result.suggestedAction}</span>
            </div>
            <div className="detail-reason">{result.reason}</div>
          </div>
        )}
        {isChecking && (
          <div className="overlay-progress">
            <div className="progress-bar">
              <div className="progress-fill" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Main Export
// ============================================================================

export const PredictiveUI = {
  ConfidenceBar: PredictiveConfidenceBar,
  StatusBadge: PredictiveStatusBadge,
  HealthIndicator: PredictiveHealthIndicator,
  WarningToast: PredictiveWarningToast,
  DecisionOverlay: PredictiveDecisionOverlay,
};
