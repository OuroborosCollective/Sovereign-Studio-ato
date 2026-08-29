# GitHub OAuth Setup Guide

Stand: 2026-08-29

> ⚠️ **SICHERHEIT**: Client Secrets NIE in Chat, Docs, Issues oder Commits posten!
> Secrets nur über sichere Kanäle teilen.

## Übersicht

Dieses Dokument beschreibt, wie du GitHub OAuth Login in Sovereign Studio einrichtest.

## Aktueller Vertrag

- Der Login-Button bezieht die OAuth-Authorize-URL ausschließlich vom Backend über `/api/auth/github/init`.
- Canonical bevorzugt Sovereign ein vollständiges `GITHUB_APP_CLIENT_ID`/`GITHUB_APP_CLIENT_SECRET`-Paar und fällt nur auf ein vollständiges Legacy-`GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET`-Paar zurück.
- GitHub App ID und GitHub App Client ID sind verschiedene Identitäten und dürfen nicht verwechselt werden.
- Für die GitHub App ist der produktive Authorize-Callback `https://sovereign-backend.arelorian.de/api/auth/github-app/callback`.
- Die Backend-Bridge leitet ausschließlich `code` und `state` an den festen Browser-Callback `https://chat.arelorian.de/auth/github/callback.html` weiter; State und PKCE werden weiterhin erst im kanonischen Login-Endpunkt geprüft.
- Ein Legacy-OAuth-App-Paar verwendet den Browser-Callback weiterhin direkt.
- `/api/auth/github/configured` liefert nur secret-sichere Konfigurations-Evidence/Fingerprints sowie getrennte `authorizeRedirectUri`, `loginForwardUri` und `callbackOrigin`-Felder, niemals Credentials.
- OAuth ist der bevorzugte Zugang. Der Play-Client bietet zusätzlich einen expliziten Sitzungs-PAT-Fallback außerhalb des Chats; der Wert bleibt flüchtig, wird nie gerendert und nur an die authentifizierte Repository-Runtime übergeben.

## Security Status: 🟡 IN PROGRESS

| Check | Status | Beweis |
|-------|--------|--------|
| OAuth-Token NICHT im Frontend; Sitzungs-PAT nicht persistiert/gerendert | ✅ | `useUserStore.ts`, `GitHubAccessCard.tsx`, `PlayReleaseChat.tsx` |
| Token-Verschlüsselung | ✅ | Contract Test ✓ |
| Scopes minimal | ✅ | `read:user`, `user:email` |
| State Validierung | ✅ | `_get_oauth_state()` |
| PKCE Backend | ✅ | `_validate_pkce()` |
| PKCE Frontend | ✅ | Vorbereitet in `githubOAuthLogin.ts` |
| Contract Tests | ✅ | 13/13 bestanden |
| E2E Security Test | ⏳ | Test vorhanden, muss manuell laufen |

**Backend deployed mit allen Security-Features.**

## Schritt 1: GitHub-Identität konfigurieren

Bevorzugt wird die bestehende GitHub App. In deren Einstellungen muss die Callback URL exakt `https://sovereign-backend.arelorian.de/api/auth/github-app/callback` enthalten. Verwende für den Login die **Client ID** der GitHub App, niemals die numerische App ID. Der statische Chat-Callback ist das Ziel der internen Bridge und muss nicht als GitHub-App-Callback ausgewählt werden.

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
GITHUB_APP_OAUTH_REDIRECT_URI=https://sovereign-backend.arelorian.de/api/auth/github-app/callback
GITHUB_APP_LOGIN_FORWARD_URI=https://chat.arelorian.de/auth/github/callback.html
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

### 🔐 OAuth-Token bleibt IMMER im Backend; PAT bleibt flüchtig

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

OAuth-Tokens werden mit `cryptography.fernet.Fernet` verschlüsselt. Ein ausdrücklich eingegebener PAT wird nicht persistiert: Er bleibt nur in einer flüchtigen Browser-Referenz, wird nach erfolgreichem OAuth verworfen und ausschließlich über authentifizierte Backend-Endpunkte an die Repository-Runtime übergeben.



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

1. Öffne das produktive Frontend unter `https://sovereign-backend.arelorian.de/app/`.
2. Melde dich bei Sovereign an und öffne den GitHub-Bereich.
3. Klicke `GitHub sicher verbinden`.
4. Verifiziere im echten Browser, dass GitHub den Authorization Screen ohne `redirect_uri is not associated` anzeigt.
5. Nach Autorisierung muss die Bridge zum Browser-Callback zurückführen; anschließend muss `/api/auth/github` State und PKCE bestätigen.
6. Führe zusätzlich einen normalen Chat-Canary und einen Repository-Aktionsentwurf aus. Ein Erfolg darf erst nach realem Runtime-/GitHub-Readback behauptet werden.

## Troubleshooting

### "Popup wurde blockiert"
→ Der Popup-Blocker des Browsers hat das OAuth-Fenster blockiert.
→ Lösung: Popups für den Sovereign-Origin erlauben und die Verbindung bewusst erneut starten. Es gibt keinen stillen Redirect-Fallback.

### GitHub zeigt direkt nach Klick eine 404

Das passiert vor dem Callback und deutet auf eine ungültige/stale Client-ID hin. Prüfe `/api/auth/github/configured`: `configured`, `credentialSource`, `identityVerified`, `appIdCollision`, `blocker` und die Client-ID-Fingerprints sind secret-sicher abrufbar. Bei GitHub-App-Nutzung verifiziert Sovereign die konfigurierte Client-ID zusätzlich gegen die authentifizierte GitHub-App-Identität.

### GitHub-Login fehlgeschlagen

- Bei GitHub-App-Credentials muss die GitHub-App-Callback-URL exakt `https://sovereign-backend.arelorian.de/api/auth/github-app/callback` sein.
- `GITHUB_APP_LOGIN_FORWARD_URI` muss auf den festen Browser-Callback `https://chat.arelorian.de/auth/github/callback.html` zeigen.
- In der vom Backend gelieferten Authorize-URL muss `redirect_uri` exakt `authorizeRedirectUri` entsprechen; `callbackOrigin` beschreibt getrennt den finalen Browser-Rückkanal.
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
