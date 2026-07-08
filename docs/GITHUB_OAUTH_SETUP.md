# GitHub OAuth Setup Guide

> ⚠️ **SICHERHEIT**: Client Secrets NIE in Chat, Docs, Issues oder Commits posten!
> Secrets nur über sichere Kanäle teilen.

> 🔴 **AKTION ERFORDERLICH**: Client Secret wurde in diesem Chat geteilt.
> **SOFORT ROTIEREN**: https://github.com/settings/applications/4247582

## Übersicht

Dieses Dokument beschreibt, wie du GitHub OAuth Login in Sovereign Studio einrichtest.

## Bereits vorhanden (NICHT erledigt - Security-Checks ausstehend)

- ⏳ Backend Endpoint `/api/auth/github` - Code vorhanden, Security-Tests ausstehend
- ⏳ DB Migration `github_*` Spalten - vorhanden
- ⏳ Frontend `loginWithGitHub()` - vorhanden, Security-Tests ausstehend
- ⏳ LoginModal mit GitHub Button - vorhanden
- ⏳ `VITE_GITHUB_OAUTH_CLIENT_ID` - gesetzt (VPS), Secret noch ausstehend

## Security Status: 🔴 INCOMPLETE

| Check | Status | Beweis erforderlich |
|-------|--------|---------------------|
| Token NICHT im Frontend | ⏳ | Regression Test fehlt |
| Token-Verschlüsselung | ⏳ | Contract Test fehlt |
| Scopes minimal | ✅ | ✓ Implementiert |
| PKCE Frontend | ⏳ | Vorbereitet, Backend fehlt |
| PKCE Backend | 🔴 | NICHT implementiert |
| State Validierung | 🔴 | NICHT implementiert |
| E2E Security Test | 🔴 | NICHT implementiert |

**Siehe Issue #560 für Details und offene Tasks.**

## Schritt 1: GitHub OAuth App erstellen (NOCH OFFEN ⏳)

1. Gehe zu: https://github.com/settings/applications/new
2. Fülle die Felder aus:

   | Feld | Wert |
   |------|------|
   | **Application name** | Sovereign Studio (oder dein Name) |
   | **Homepage URL** | `https://deine-domain.de` |
   | **Authorization callback URL** | `https://deine-backend-domain.de/api/auth/github/callback` |

3. Klicke **Register application**
4. Kopiere die **Client ID**
5. Generiere einen **Client Secret** (falls noch nicht vorhanden)

## Schritt 2: Client ID im Frontend setzen

> **Für AI Studio / Cloud Deployment:**
> Setze die `VITE_GITHUB_OAUTH_CLIENT_ID` in den Secrets/Environment Variables deines Deployments.

> **Für lokale Entwicklung:**
> Füge in deiner `.env` Datei hinzu:

```env
# GitHub OAuth (für Login)
VITE_GITHUB_OAUTH_CLIENT_ID=dein_github_client_id

# Optional: Alternative Redirect-URI
# VITE_GITHUB_OAUTH_REDIRECT_URI=https://deine-domain.de/auth/github/callback
```

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

### Erforderliche Environment Variables:

```bash
GITHUB_CLIENT_ID=DEINE_CLIENT_ID          # Von GitHub OAuth App
GITHUB_CLIENT_SECRET=DEIN_CLIENT_SECRET     # ⚠️ FRISCH GENERIERT
GITHUB_TOKEN_ENCRYPTION_KEY=zufälliger_64_byte_string  # Für Token-Verschlüsselung
```

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

### "GitHub-Login fehlgeschlagen"
→ Prüfe in der Browser-Konsole:
  - Ist `VITE_GITHUB_OAUTH_CLIENT_ID` gesetzt?
  - Stimmt die Redirect-URI mit der GitHub App überein?

### Backend-Fehler
→ Prüfe Server-Logs:
  - Ist `GITHUB_CLIENT_SECRET` gesetzt?
  - Ist die Datenbank-Verbindung OK?

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

Security-Tests in Issue #560 definiert:

| Test | Datei | Status |
|------|-------|--------|
| Token nicht in Response | `backend/tests/test_github_oauth_security.py` | ⏳ |
| Token-Verschlüsselung | `backend/tests/test_github_oauth_security.py` | ⏳ |
| State Validierung | `backend/tests/test_oauth_state_validation.py` | ⏳ |
| PKCE Validierung | `backend/tests/test_oauth_pkce_validation.py` | ⏳ |
| Frontend Regression | `e2e/security/oauth-token-never-in-frontend.spec.ts` | ⏳ |

## Status: 🔴 NICHT PRODUKTIONSREIF

> **Diese Integration ist NICHT produktionsreif!**
> Security-Tests und Contract-Tests müssen erst bestehen.

Siehe: https://github.com/OuroborosCollective/Sovereign-Studio-ato/issues/560
