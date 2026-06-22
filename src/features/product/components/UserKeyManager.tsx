import React, { useState, useEffect } from 'react';
import '../styles/UserKeyManager.css';

export interface UserApiKeys {
  pollinations?: string;
  groq?: string;
  huggingface?: string;
  together?: string;
  openrouter?: string;
  gemini?: string;
}

export interface LlmProviderInfo {
  id: string;
  name: string;
  description: string;
  docsUrl: string;
  keyPlaceholder: string;
  freeTier: string;
  icon: string;
}

export const LLM_PROVIDERS: LlmProviderInfo[] = [
  {
    id: 'pollinations',
    name: 'Pollinations AI',
    description: 'Kostenlose Basis-Nutzung, optional mit API-Key für Priority-Access',
    docsUrl: 'https://pollinations.ai/dashboard',
    keyPlaceholder: 'pollinations_xxx...',
    freeTier: 'Unbegrenzte kostenlose Anfragen',
    icon: '🌸',
  },
  {
    id: 'mlvoca',
    name: 'MLVOCA',
    description: 'Komplett kostenlos, keine Anmeldung erforderlich',
    docsUrl: 'https://mlvoca.com',
    keyPlaceholder: 'Nicht erforderlich',
    freeTier: 'Immer kostenlos',
    icon: '🚀',
  },
  {
    id: 'groq',
    name: 'Groq',
    description: 'Schnelle Inference mit kostenlosem Kontingent',
    docsUrl: 'https://console.groq.com/keys',
    keyPlaceholder: 'gsk_xxx...',
    freeTier: '14.000 Anfragen/Minute gratis',
    icon: '⚡',
  },
  {
    id: 'huggingface',
    name: 'HuggingFace',
    description: 'Inference API mit gratis Kontingent',
    docsUrl: 'https://huggingface.co/settings/tokens',
    keyPlaceholder: 'hf_xxx...',
    freeTier: 'Gratis-Tier verfügbar',
    icon: '🤗',
  },
  {
    id: 'together',
    name: 'Together AI',
    description: 'Open Source Models, Pay-per-Use',
    docsUrl: 'https://api.together.xyz/settings/api-keys',
    keyPlaceholder: 'together_xxx...',
    freeTier: '$5 Gratis-Credit bei Anmeldung',
    icon: '🎯',
  },
  {
    id: 'openrouter',
    name: 'OpenRouter',
    description: 'Zugriff auf 100+ Models über eine API',
    docsUrl: 'https://openrouter.ai/keys',
    keyPlaceholder: 'sk-or-v1-xxx...',
    freeTier: 'Kostenlose Models verfügbar',
    icon: '🛤️',
  },
  {
    id: 'gemini',
    name: 'Google Gemini',
    description: 'Google\'s leistungsstarke AI Modelle',
    docsUrl: 'https://aistudio.google.com/app/apikey',
    keyPlaceholder: 'AIzaxxx...',
    freeTier: '15 Anfragen/Minute, 1500/Tag gratis',
    icon: '✨',
  },
];

interface UserKeyManagerProps {
  onKeysChange?: (keys: UserApiKeys) => void;
  storedKeys?: UserApiKeys;
}

export function UserKeyManager({ onKeysChange, storedKeys }: UserKeyManagerProps) {
  const [keys, setKeys] = useState<UserApiKeys>(storedKeys || {});
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  useEffect(() => {
    // Load keys from localStorage
    const saved = localStorage.getItem('sovereign-user-api-keys');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setKeys(parsed);
        onKeysChange?.(parsed);
      } catch {
        // Ignore parse errors
      }
    }
  }, []);

  const handleSaveKeys = () => {
    localStorage.setItem('sovereign-user-api-keys', JSON.stringify(keys));
    onKeysChange?.(keys);
    setSavedMessage('✅ API-Keys gespeichert!');
    setTimeout(() => setSavedMessage(null), 3000);
  };

  const handleKeyChange = (providerId: string, value: string) => {
    const newKeys = { ...keys, [providerId]: value || undefined };
    setKeys(newKeys);
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
  };

  const getStatusBadge = (providerId: string, hasFreeTier: boolean) => {
    const hasKey = !!keys[providerId as keyof UserApiKeys];
    
    if (hasKey) {
      return (
        <span className="status-badge status-active">
          🔑 Eigener Key aktiv
        </span>
      );
    }
    
    if (hasFreeTier) {
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
    <div className="user-key-manager">
      <div className="key-manager-header">
        <h3>🔐 API-Keys verwalten</h3>
        <p className="key-manager-description">
          Falls die kostenlosen Routen an ihr Limit kommen, kannst du hier deine eigenen API-Keys hinterlegen.
          Deine Keys werden nur lokal gespeichert und nie an externe Server übertragen.
        </p>
      </div>

      <div className="provider-list">
        {LLM_PROVIDERS.map((provider) => (
          <div key={provider.id} className="provider-card">
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
                    placeholder={provider.keyPlaceholder}
                    value={keys[provider.id as keyof UserApiKeys] || ''}
                    onChange={(e) => handleKeyChange(provider.id, e.target.value)}
                    className="key-input"
                  />
                  <button
                    type="button"
                    onClick={() => toggleShowKey(provider.id)}
                    className="btn-icon"
                    title={showKeys[provider.id] ? 'Verbergen' : 'Anzeigen'}
                  >
                    {showKeys[provider.id] ? '🙈' : '👁️'}
                  </button>
                  {(keys[provider.id as keyof UserApiKeys]) && (
                    <button
                      type="button"
                      onClick={() => clearKey(provider.id)}
                      className="btn-icon btn-clear"
                      title="Key löschen"
                    >
                      🗑️
                    </button>
                  )}
                </div>

                <button
                  type="button"
                  onClick={() => openDocs(provider.docsUrl)}
                  className="btn-docs"
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
          💾 Keys speichern
        </button>
      </div>

      <div className="key-manager-warning">
        <p>
          ⚠️ <strong>Sicherheitshinweis:</strong> API-Keys werden nur in deinem Browser (localStorage) gespeichert.
          Teile deine Keys niemals mit anderen.
        </p>
      </div>
    </div>
  );
}

export function getStoredUserKeys(): UserApiKeys {
  try {
    const saved = localStorage.getItem('sovereign-user-api-keys');
    if (saved) {
      return JSON.parse(saved);
    }
  } catch {
    // Ignore
  }
  return {};
}

export function clearStoredUserKeys(): void {
  localStorage.removeItem('sovereign-user-api-keys');
}