import React, { useState, useCallback } from 'react';
import {
  type GitHubAccessSnapshot,
  validateGitHubTokenFormat,
  getGitHubAccessLabel,
  getGitHubAccessInstruction,
} from '../runtime/githubAccessRuntime';
import { attemptClearClipboard } from '../runtime/androidQuickInteractionRuntime';

export interface GitHubAccessCardProps {
  snapshot: GitHubAccessSnapshot;
  onProvideToken: (token: string) => void | Promise<void>;
  onDismiss?: () => void;
}

// Design tokens from BuilderContainer
const C = {
  bg: '#0e1116',
  surface: '#161c24',
  border: '#232d3a',
  borderHov: '#2e3d50',
  accent: '#00d9b1',
  accentDim: '#00d9b122',
  orange: '#f97316',
  text: '#cdd9e5',
  textSub: '#768390',
  textMuted: '#3d4f61',
  green: '#34d399',
  sky: '#22d3ee',
  amber: '#fbbf24',
  rose: '#fb7185',
};

export function GitHubAccessCard({ snapshot, onProvideToken, onDismiss }: GitHubAccessCardProps) {
  const [inputValue, setInputValue] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const [clipboardClearState, setClipboardClearState] = useState<'idle' | 'clearing' | 'cleared' | 'failed'>('idle');

  const handleOpenModal = useCallback(() => {
    setShowModal(true);
    setInputValue('');
    setInputError(null);
    setClipboardClearState('idle');
  }, []);

  const handleCloseModal = useCallback(() => {
    setShowModal(false);
    setInputValue('');
    setInputError(null);
  }, []);

  const handleSubmit = useCallback(() => {
    const validation = validateGitHubTokenFormat(inputValue);
    if (!validation.isValid) {
      setInputError(validation.error || 'Ungültiges Token');
      return;
    }
    void Promise.resolve(onProvideToken(inputValue)).catch(() => {
      setInputError('GitHub-Zugangsprüfung konnte nicht gestartet werden.');
    });
    setShowModal(false);
    setInputValue('');
    setInputError(null);
  }, [inputValue, onProvideToken]);

  const handleClearClipboard = useCallback(async () => {
    setClipboardClearState('clearing');
    const result = await attemptClearClipboard();
    if (result.cleared) {
      setClipboardClearState('cleared');
    } else {
      setClipboardClearState(result.available ? 'failed' : 'idle');
    }
  }, []);

  const getStateColor = () => {
    switch (snapshot.state) {
      case 'ready': return C.green;
      case 'validating': return C.sky;
      case 'invalid': return C.rose;
      case 'requested': return C.amber;
      default: return C.textMuted;
    }
  };

  const getIcon = () => {
    switch (snapshot.state) {
      case 'ready': return '✓';
      case 'validating': return '⟳';
      case 'invalid': return '✗';
      case 'requested': return '?';
      default: return '🔗';
    }
  };

  return (
    <>
      {/* Card - only shown when not ready */}
      {snapshot.state !== 'ready' && (
        <div
          style={{
            background: C.surface,
            border: `1px solid ${C.border}`,
            borderRadius: 12,
            padding: '12px 16px',
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          {/* Status Icon */}
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              background: `${getStateColor()}20`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 16,
              color: getStateColor(),
              flexShrink: 0,
            }}
          >
            {snapshot.state === 'validating' ? (
              <span style={{ animation: 'spin 1s linear infinite' }}>⟳</span>
            ) : getIcon()}
          </div>

          {/* Text Content */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontSize: 13,
                fontWeight: 500,
                color: C.text,
                marginBottom: 2,
              }}
            >
              {getGitHubAccessLabel(snapshot)}
            </div>
            <div
              style={{
                fontSize: 11,
                color: C.textSub,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {snapshot.state === 'validating' 
                ? `Prüfe ${snapshot.maskedToken}…`
                : getGitHubAccessInstruction(snapshot)
              }
            </div>
            {snapshot.state === 'invalid' && snapshot.errorMessage && (
              <div
                style={{
                  fontSize: 11,
                  color: C.rose,
                  marginTop: 4,
                }}
              >
                {snapshot.errorMessage}
              </div>
            )}
          </div>

          {/* Action Button */}
          {(snapshot.state === 'missing' || snapshot.state === 'invalid' || snapshot.state === 'requested') && (
            <button
              type="button"
              onClick={handleOpenModal}
              style={{
                padding: '6px 12px',
                borderRadius: 8,
                background: C.accent,
                color: C.bg,
                fontSize: 12,
                fontWeight: 500,
                border: 'none',
                cursor: 'pointer',
                flexShrink: 0,
              }}
            >
              Zugang eingeben
            </button>
          )}

          {/* Dismiss for invalid */}
          {snapshot.state === 'invalid' && onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              style={{
                padding: '6px 8px',
                borderRadius: 8,
                background: 'transparent',
                color: C.textMuted,
                fontSize: 12,
                border: `1px solid ${C.border}`,
                cursor: 'pointer',
                flexShrink: 0,
              }}
            >
              ✕
            </button>
          )}
        </div>
      )}

      {/* Success indicator - only shown when ready */}
      {snapshot.state === 'ready' && snapshot.maskedToken && (
        <div
          style={{
            background: C.surface,
            border: `1px solid ${C.border}`,
            borderRadius: 12,
            padding: '12px 16px',
            marginBottom: 12,
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 12,
              color: C.green,
              marginBottom: 8,
            }}
          >
            <span>✓</span>
            <span>GitHub {snapshot.maskedToken} nutzbar</span>
          </div>
          {/* Rotation guidance */}
          <div
            style={{
              fontSize: 11,
              color: C.textSub,
              marginBottom: 12,
            }}
          >
            Bitte den Token rotieren, falls er in einem Screen Recording oder Clipboard-Verlauf sichtbar war.
          </div>
          {/* Optional clipboard clear button */}
          <div style={{ display: 'flex', gap: 8 }}>
            {clipboardClearState === 'idle' && (
              <button
                type="button"
                onClick={handleClearClipboard}
                style={{
                  padding: '6px 12px',
                  borderRadius: 6,
                  background: 'transparent',
                  color: C.textSub,
                  fontSize: 11,
                  border: `1px solid ${C.border}`,
                  cursor: 'pointer',
                }}
              >
                Zwischenablage leeren
              </button>
            )}
            {clipboardClearState === 'clearing' && (
              <span style={{ fontSize: 11, color: C.textSub }}>
                Leere Zwischenablage…
              </span>
            )}
            {clipboardClearState === 'cleared' && (
              <span style={{ fontSize: 11, color: C.green }}>
                ✓ Zwischenablage geleert
              </span>
            )}
            {clipboardClearState === 'failed' && (
              <span style={{ fontSize: 11, color: C.amber }}>
                Zwischenablage kann hier nicht automatisch geleert werden. Bitte manuell leeren.
              </span>
            )}
          </div>
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div
          onClick={handleCloseModal}
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 100,
            background: 'rgba(14,17,22,0.88)',
            backdropFilter: 'blur(6px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: '100%',
              maxWidth: 400,
              background: C.surface,
              border: `1px solid ${C.border}`,
              borderRadius: 16,
              padding: 24,
            }}
          >
            {/* Header */}
            <div style={{ marginBottom: 20 }}>
              <h3
                style={{
                  margin: '0 0 8px 0',
                  fontSize: 16,
                  fontWeight: 600,
                  color: C.text,
                }}
              >
                GitHub-Zugang
              </h3>
              <p
                style={{
                  margin: 0,
                  fontSize: 12,
                  color: C.textSub,
                  lineHeight: 1.5,
                }}
              >
                Gib deinen GitHub Personal Access Token (PAT) ein. 
                Dieser wird nur für diesen Browser-Session gespeichert und nie in Chat-History, Logs oder Telemetry geschrieben.
              </p>
            </div>

            {/* Input */}
            <div style={{ marginBottom: 16 }}>
              <label
                htmlFor="github-pat-input"
                style={{
                  display: 'block',
                  fontSize: 12,
                  color: C.textSub,
                  marginBottom: 6,
                }}
              >
                GitHub Token (ghp_*, gho_*, ghs_*, ghu_*, ghr_*)
              </label>
              <input
                id="github-pat-input"
                type="password"
                value={inputValue}
                onChange={(e) => {
                  setInputValue(e.target.value);
                  setInputError(null);
                }}
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                autoComplete="off"
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: 8,
                  border: `1px solid ${inputError ? C.rose : C.border}`,
                  background: C.bg,
                  color: C.text,
                  fontSize: 13,
                  fontFamily: 'monospace',
                  boxSizing: 'border-box',
                }}
              />
              {inputError && (
                <p
                  style={{
                    margin: '6px 0 0 0',
                    fontSize: 11,
                    color: C.rose,
                  }}
                >
                  {inputError}
                </p>
              )}
            </div>

            {/* Buttons */}
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={handleCloseModal}
                style={{
                  padding: '8px 16px',
                  borderRadius: 8,
                  background: 'transparent',
                  color: C.textSub,
                  fontSize: 13,
                  border: `1px solid ${C.border}`,
                  cursor: 'pointer',
                }}
              >
                Abbrechen
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!inputValue.trim()}
                style={{
                  padding: '8px 16px',
                  borderRadius: 8,
                  background: inputValue.trim() ? C.accent : C.textMuted,
                  color: inputValue.trim() ? C.bg : C.textSub,
                  fontSize: 13,
                  fontWeight: 500,
                  border: 'none',
                  cursor: inputValue.trim() ? 'pointer' : 'not-allowed',
                }}
              >
                Übernehmen
              </button>
            </div>

            {/* Help text */}
            <p
              style={{
                margin: '16px 0 0 0',
                fontSize: 10,
                color: C.textMuted,
                lineHeight: 1.5,
              }}
            >
              Erstelle einen PAT in GitHub Settings → Developer settings → Personal access tokens.
              Benötigte Berechtigungen: repo (für private Repos), workflow (für Actions).
            </p>
          </div>
        </div>
      )}
    </>
  );
}

export default GitHubAccessCard;
