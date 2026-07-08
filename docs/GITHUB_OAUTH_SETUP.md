# GitHub OAuth Setup Guide

> ⚠️ **SICHERHEIT**: Client Secrets NIE in Chat, Docs, Issues oder Commits posten!
> Secrets nur über sichere Kanäle teilen.

> 🔴 **AKTION ERFORDERLICH**: Client Secret wurde in diesem Chat geteilt.
> **SOFORT ROTIEREN**: https://github.com/settings/applications/4247582

## Übersicht

Dieses Dokument beschreibt, wie du GitHub OAuth Login in Sovereign Studio einrichtest.

## Bereits erledigt ✅

- ✅ Backend Endpoint `/api/auth/github` implementiert
- ✅ DB Migration für `github_id`, `github_username`, `github_access_token` Spalten
- ✅ Frontend `loginWithGitHub()` Funktion
- ✅ LoginModal mit GitHub Button
- ✅ Environment Variable: `VITE_GITHUB_OAUTH_CLIENT_ID` (noch nicht gesetzt)

## Architektur

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend       │     │   GitHub        │     │   Backend       │
│   (LoginModal)   │────▶│   OAuth         │────▶│   (sovereign-   │
│                  │◀────│                  │◀────│   backend)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
      Popup öffnen          Authorization           Token austauschen
      & Code empfangen       & User-Login            & User erstellen
```

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

> ⚠️ **Bereits erledigt!** Der Endpoint `/api/auth/github` ist implementiert.
> Du musst nur noch die Environment Variables im Backend setzen.

### Auf dem Server (via SSH):

```bash
# Auf dem VPS:
docker exec sovereign-backend env
# Prüfen ob GITHUB_CLIENT_ID und GITHUB_CLIENT_SECRET gesetzt sind

# Falls nicht, in docker-compose.yml oder Container Environment setzen:
docker exec sovereign-backend env GITHUB_CLIENT_ID=dein_client_id
docker exec sovereign-backend env GITHUB_CLIENT_SECRET=dein_client_secret
```

### Oder in Docker Compose (.env oder environment):

```yaml
services:
  sovereign-backend:
    environment:
      - GITHUB_CLIENT_ID=dein_client_id
      - GITHUB_CLIENT_SECRET=dein_client_secret
```

Der Endpoint ist bereits implementiert in `backend_app.py`!

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

## Status: 🟡 Hardening Required

| Check | Status |
|-------|--------|
| Token nicht im Frontend | ✅ Behoben |
| Token-Verschlüsselung | ✅ Implementiert |
| Scopes reduziert | ✅ `read:user`, `user:email` |
| PKCE-Validierung | ⏳ Offen |
| E2E Test | ⏳ Offen |
| Client Secret Rotation | 🔴 **Erforderlich!** |
