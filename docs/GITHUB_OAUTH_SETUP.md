# GitHub OAuth Setup Guide

> ⚠️ **Status**: Backend ist bereits konfiguriert und läuft! (Stand: 2026-07-08)
> Du musst nur noch die GitHub OAuth App erstellen und die Credentials eintragen.

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

## Schritt 4: Security beachten

### Access Token sicher speichern

```javascript
// ❌ BAD: Token als Plain-Text speichern
user.githubAccessToken = access_token;

// ✅ GOOD: Token verschlüsseln
user.githubAccessToken = encrypt(access_token, ENCRYPTION_KEY);

// ✅✅ BEST: Token nur im Backend speichern, nie an Frontend senden
// Frontend bekommt nur Session-Cookie
```

### Token-Refresh

GitHub OAuth Tokens laufen nicht ab, ABER:
- User können Tokens in GitHub Settings widerrufen
- User können der App Berechtigungen entziehen

**Empfehlung:** Regelmäßig den Token validieren:
```javascript
async function validateGitHubToken(token) {
  const res = await fetch('https://api.github.com/user', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return res.ok;
}
```

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
- Automatischer GitHub API-Zugriff für Repo-Operationen

```typescript
const user = useUserStore.getState().user;

if (user?.githubAccessToken) {
  // Kann GitHub API nutzen!
  const octokit = new Octokit({ auth: user.githubAccessToken });
}
```
