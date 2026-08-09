# GitHub OAuth Setup Guide

> ⚠️ **SICHERHEIT**: Client Secrets NIE in Chat, Docs, Issues oder Commits posten!
> Secrets nur über sichere Kanäle teilen.

## Übersicht

Dieses Dokument beschreibt, wie du GitHub OAuth Login in Sovereign Studio einrichtest.

## Aktueller Vertrag

- Der Login-Button bezieht die OAuth-Authorize-URL ausschließlich vom Backend über `/api/auth/github/init`.
- Canonical bevorzugt Sovereign ein vollständiges `GITHUB_APP_CLIENT_ID`/`GITHUB_APP_CLIENT_SECRET`-Paar und fällt nur auf ein vollständiges Legacy-`GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET`-Paar zurück.
- GitHub App ID und GitHub App Client ID sind verschiedene Identitäten und dürfen nicht verwechselt werden.
- Der produktive Callback ist `https://chat.arelorian.de/auth/github/callback.html`.
- `/api/auth/github/configured` liefert nur secret-sichere Konfigurations-Evidence/Fingerprints, niemals Credentials.

## Security Status: 🟡 IN PROGRESS

| Check | Status | Beweis |
|-------|--------|--------|
| Token NICHT im Frontend | ✅ | `useUserStore.ts` |
| Token-Verschlüsselung | ✅ | Contract Test ✓ |
| Scopes minimal | ✅ | `read:user`, `user:email` |
| State Validierung | ✅ | `_get_oauth_state()` |
| PKCE Backend | ✅ | `_validate_pkce()` |
| PKCE Frontend | ✅ | Vorbereitet in `githubOAuthLogin.ts` |
| Contract Tests | ✅ | 13/13 bestanden |
| E2E Security Test | ⏳ | Test vorhanden, muss manuell laufen |

**Backend deployed mit allen Security-Features.**

## Schritt 1: GitHub-Identität konfigurieren

Bevorzugt wird die bestehende GitHub App. In deren Einstellungen muss die Callback URL exakt `https://chat.arelorian.de/auth/github/callback.html` enthalten. Verwende für den Login die **Client ID** der GitHub App, niemals die numerische App ID.

Ein separates Legacy-OAuth-App-Paar bleibt nur als expliziter Fallback unterstützt. Der Browser bzw. die APK enthält keine GitHub Client ID; die Authorize-URL wird serverseitig erzeugt.

## Schritt 2: Backend-Konfiguration

Die Credentials werden ausschließlich als geschützte Backend-Environment-Werte verwaltet. Keine Client ID/Secrets müssen als `VITE_*`-Variable in die APK eingebaut werden.

### Scopes erklärt

| Scope | Beschreibung |
|-------|--------------|
| `read:user` | Liest öffentliches GitHub-Profil |
| `user:email` | Liest private E-Mail-Adressen |
| `repo` | **Vollzugriff auf alle Repositories** (optional) |

> ⚠️ **Achtung**: Der `repo` Scope gibt LESE- und SCHREIB-Zugriff auf ALLE Repositories des Users. Das ist für ein Tool, das Code generiert, durchaus sinnvoll.

## Schritt 3: Backend Secrets setzen

> ⚠️ **SECRET ROTATION ERFORDERLICH** - Das Client Secret wurde in einem unsicheren Kanal geteilt.

### Auf dem Server (via SSH):

```bash
# Auf dem VPS:
docker exec sovereign-backend env | grep GITHUB

# Backend neu starten nach Secret-Änderung:
docker restart sovereign-backend
```

### Erforderliche Environment Variables

Bevorzugte GitHub-App-Identität:

```bash
GITHUB_APP_ID=<numerische-app-id>
GITHUB_APP_CLIENT_ID=<github-app-client-id>
GITHUB_APP_CLIENT_SECRET=<geschützt>
GITHUB_APP_PRIVATE_KEY=<geschützt>
GITHUB_OAUTH_REDIRECT_URI=https://chat.arelorian.de/auth/github/callback.html
GITHUB_TOKEN_ENCRYPTION_KEY=<geschützt>
```

Legacy-Fallback nur als vollständiges Paar:

```bash
GITHUB_CLIENT_ID=<oauth-app-client-id>
GITHUB_CLIENT_SECRET=<geschützt>
```

Sovereign mischt niemals Client ID und Secret aus unterschiedlichen Credential-Familien.

**Siehe `backend/tests/test_github_oauth_security.py` für Security-Requirements.**

## Schritt 4: Security-Regeln

### 🔐 Token bleibt IMMER im Backend

```typescript
// ❌ VERBOTEN: Token im Frontend
interface CurrentUser {
  githubAccessToken?: string; // ABSOLUT VERBOTEN!
}

// ✅ RICHTIG: Token verschlüsselt im Backend
interface CurrentUser {
  githubId?: string;
  githubUsername?: string;
  // Token ist NUR im Backend
}
```

### Verschlüsselung

Tokens werden mit `cryptography.fernet.Fernet` verschlüsselt:

```python
# Backend: Token verschlüsseln
encrypted = _encrypt_token(access_token)

# Backend: Token entschlüsseln für API-Zugriff
token = _decrypt_token(row["github_access_token"])
```

### Scopes

| Scope | Nutzung |
|-------|---------|
| `read:user` | ✅ Standard (Login) |
| `user:email` | ✅ Standard (Login) |
| `repo` | ⚠️ Nur bei Bedarf, separat anfordern |

### Backend-Proxy

Alle GitHub-API-Operationen laufen über das Backend:

## Schritt 5: Testen

1. Starte das Frontend
2. Öffne das Login Modal
3. Klicke "Mit GitHub anmelden"
4. Du solltest zum GitHub Authorization Screen weitergeleitet werden
5. Nach Autorisierung wirst du zurückgeleitet und bist eingeloggt

## Troubleshooting

### "Popup wurde blockiert"
→ Der Popup-Blocker des Browsers hat das OAuth-Fenster blockiert.
→ Lösung: Der Code fällt automatisch auf Redirect-Flow zurück.

### GitHub zeigt direkt nach Klick eine 404

Das passiert vor dem Callback und deutet auf eine ungültige/stale Client-ID hin. Prüfe `/api/auth/github/configured`: `configured`, `credentialSource`, `identityVerified`, `appIdCollision`, `blocker` und die Client-ID-Fingerprints sind secret-sicher abrufbar. Bei GitHub-App-Nutzung verifiziert Sovereign die konfigurierte Client-ID zusätzlich gegen die authentifizierte GitHub-App-Identität.

### GitHub-Login fehlgeschlagen

- Callback URL muss exakt `https://chat.arelorian.de/auth/github/callback.html` sein.
- GitHub App **Client ID** verwenden, nicht die numerische App ID.
- Credential-Paare vollständig halten; keine Cross-Mischung zwischen GitHub App und Legacy OAuth App.
- Datenbank/State/PKCE müssen verfügbar sein.

## User Interface nach Login

Nach erfolgreichem GitHub-Login hat der User Zugriff auf:
- Sein GitHub-Profil im UserStore
- Repo-Operationen über Backend-Proxy

```typescript
const user = useUserStore.getState().user;

// ✅ RICHTIG: GitHub-Verbindung prüfen
if (user?.githubId) {
  // GitHub ist verbunden
}

// ❌ VERBOTEN: Token niemals hier!
if (user?.githubAccessToken) { // ABSOLUT VERBOTEN!
```

Alle GitHub-API-Calls müssen über das Backend laufen!

---

## Tests

| Test | Datei | Status |
|------|-------|--------|
| Token Contract | `backend/tests/test_github_oauth_security.py` | ✅ 13/13 bestanden |
| State/PKCE | `backend/tests/test_oauth_state_validation.py` | ✅ |
| PKCE | `backend/tests/test_oauth_pkce_validation.py` | ✅ |
| Frontend Regression | `e2e/security/oauth-token-never-in-frontend.spec.ts` | ⏳ Manuell |

## Status: 🟡 PRODUKTIONSFÄHIG (mit Einschränkungen)

- ✅ Backend Security Features implementiert und getestet
- ✅ Contract Tests bestehen
- ⏳ E2E Test muss in CI integriert werden
- 🔴 Client Secret Rotation erforderlich

Siehe: https://github.com/OuroborosCollective/Sovereign-Studio-ato/issues/560
