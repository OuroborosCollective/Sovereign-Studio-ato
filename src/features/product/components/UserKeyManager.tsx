import React, { useState, useEffect } from 'react';
import { Eye, EyeOff, Trash2 } from 'lucide-react';
import '../styles/UserKeyManager.css';
import { SettingsErrorBoundary } from './SettingsErrorBoundary';
import type { UserApiKeys } from '../runtime/userApiKeysContract';

export type { UserApiKeys } from '../runtime/userApiKeysContract';

export interface LlmProviderInfo {
  id: string;
  name: string;
  description: string;
  docsUrl: string;
  keyPlaceholder: string;
  freeTier: string;
  icon: string;
}

export const LLM_PROVIDERS: LlmProviderInfo[] = [];

interface UserKeyManagerProps {
  onKeysChange?: (keys: UserApiKeys) => void;
  storedKeys?: UserApiKeys;
}

export function UserKeyManager({ onKeysChange }: UserKeyManagerProps) {
  const [keys, setKeys] = useState<UserApiKeys>({});
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [invalidKeys, setInvalidKeys] = useState<Record<string, string>>({});

  useEffect(() => {
    setKeys({});
    onKeysChange?.({});
  }, []);

  const handleSaveKeys = () => {
    setKeys({});
    setInvalidKeys({});
    onKeysChange?.({});
    setSavedMessage('Provider-Zugangsdaten werden ausschließlich serverseitig verwaltet.');
    setTimeout(() => setSavedMessage(null), 3000);
  };

  const handleKeyChange = (providerId: string, value: string) => {
    const newKeys = { ...keys, [providerId]: value || undefined };
    setKeys(newKeys);
    
    // Clear invalid state when user types
    if (invalidKeys[providerId]) {
      const newInvalid = { ...invalidKeys };
      delete newInvalid[providerId];
      setInvalidKeys(newInvalid);
    }
  };

  const toggleShowKey = (providerId: string) => {
    setShowKeys((prev) => ({ ...prev, [providerId]: !prev[providerId] }));
  };

  const openDocs = (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const clearKey = (providerId: string) => {
    const newKeys = { ...keys };
    delete newKeys[providerId as keyof UserApiKeys];
    setKeys(newKeys);
    if (invalidKeys[providerId]) {
      const newInvalid = { ...invalidKeys };
      delete newInvalid[providerId];
      setInvalidKeys(newInvalid);
    }
  };

  const getStatusBadge = (providerId: string, hasFreeTier: boolean) => {
    const hasKey = !!keys[providerId as keyof UserApiKeys];
    const isInvalid = !!invalidKeys[providerId];
    
    if (isInvalid) {
      return (
        <span className="status-badge status-required">
          ⚠️ Ungültiges Format
        </span>
      );
    }
    
    if (hasKey) {
      return (
        <span className="status-badge status-active">
          🔑 Eigener Key aktiv
        </span>
      );
    }
    
    if (hasFreeTier || providerId === 'mlvoca') {
      return (
        <span className="status-badge status-free">
          🌐 Free-Tier
        </span>
      );
    }
    
    return (
      <span className="status-badge status-required">
        ⚠️ Key erforderlich
      </span>
    );
  };

  return (
    <SettingsErrorBoundary>
      <div className="user-key-manager">
        <div className="key-manager-header">
          <h3>🔐 API-Keys verwalten</h3>
          <p className="key-manager-description">
            Provider-Zugangsdaten werden nicht in Browser, WebView oder APK angenommen.
            Neue Provider werden ausschließlich unter /admin → LLM Routes vorbereitet und über die geschützte Owner-Eingabe an den passenden Direkttransport übergeben: OpenRouter für Paid, FreeLLM für Free. LiteLLM ist nur noch Legacy.
          </p>
        </div>

        <div className="provider-list">
          {LLM_PROVIDERS.map((provider) => (
            <div key={provider.id} className={`provider-card ${invalidKeys[provider.id] ? 'provider-invalid' : ''}`}>
              <div className="provider-header">
                <div className="provider-info">
                  <span className="provider-icon">{provider.icon}</span>
                  <div>
                    <h4>{provider.name}</h4>
                    <p>{provider.description}</p>
                  </div>
                </div>
                {getStatusBadge(provider.id, provider.freeTier !== 'Nicht erforderlich')}
              </div>

              <div className="provider-details">
                <div className="free-tier-info">
                  <span className="free-tier-label">Free-Tier:</span>
                  <span className="free-tier-value">{provider.freeTier}</span>
                </div>

                <div className="key-input-section">
                  <div className="key-input-row">
                    <input
                      type={showKeys[provider.id] ? 'text' : 'password'}
                      placeholder="Serverseitig verwaltet"
                      value=""
                      disabled
                      onChange={(e) => handleKeyChange(provider.id, e.target.value)}
                      className={`key-input ${invalidKeys[provider.id] ? 'key-input-invalid' : ''}`}
                      aria-label={`${provider.name} API-Key`}
                    />
                    <button
                      type="button"
                      onClick={() => toggleShowKey(provider.id)}
                      className="btn-icon"
                      title={showKeys[provider.id] ? 'Key verbergen' : 'Key anzeigen'}
                      aria-label={showKeys[provider.id] ? 'Key verbergen' : 'Key anzeigen'}
                    >
                      {showKeys[provider.id] ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                    {(keys[provider.id as keyof UserApiKeys]) && (
                      <button
                        type="button"
                        onClick={() => clearKey(provider.id)}
                        className="btn-icon btn-clear"
                        title="Key löschen"
                        aria-label="Key löschen"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>

                  {invalidKeys[provider.id] && (
                    <p className="key-error">{invalidKeys[provider.id]}</p>
                  )}

                  <button
                    type="button"
                    onClick={() => openDocs(provider.docsUrl)}
                    className="btn-docs"
                    title={`API-Key Dokumentation für ${provider.name} in neuem Tab öffnen`}
                  >
                    🔗 API-Key erstellen → {provider.name}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="key-manager-footer">
          {savedMessage && (
            <span className="save-message">{savedMessage}</span>
          )}
          <button
            type="button"
            onClick={handleSaveKeys}
            className="btn-save"
          >
            🔒 Provider nur im Admin-Backend verwalten
          </button>
        </div>

        <div className="key-manager-warning">
          <p>
            🔒 <strong>Sicherheitshinweis:</strong> API-Keys werden weder im Browser noch in der APK gespeichert.
            Die App nutzt ausschließlich serverseitig freigegebene Provider-Routen.
          </p>
        </div>
      </div>
    </SettingsErrorBoundary>
  );
}

export function getStoredUserKeys(): UserApiKeys {
  return {};
}

export function clearStoredUserKeys(): void {
  // Provider secrets are never persisted in the browser.
}
