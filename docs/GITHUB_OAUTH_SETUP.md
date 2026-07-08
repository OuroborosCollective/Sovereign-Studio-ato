# GitHub OAuth Setup Guide

## Übersicht

Dieses Dokument beschreibt, wie du GitHub OAuth Login in Sovereign Studio einrichtest.

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

## Schritt 1: GitHub OAuth App erstellen

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

## Schritt 2: Frontend konfigurieren

Füge in deiner `.env` Datei hinzu:

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

## Schritt 3: Backend implementieren

Im Backend (sovereign-backend) muss folgender Endpoint implementiert werden:

### POST `/api/auth/github`

**Request:**
```json
{
  "code": "oauth_authorization_code_hier"
}
```

**Ablauf:**
```javascript
// 1. Code gegen Access Token tauschen
const tokenResponse = await fetch('https://github.com/login/oauth/access_token', {
  method: 'POST',
  headers: {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    client_id: GITHUB_CLIENT_ID,
    client_secret: GITHUB_CLIENT_SECRET,
    code: code
  })
});

const { access_token } = await tokenResponse.json();

// 2. User-Info von GitHub holen
const userResponse = await fetch('https://api.github.com/user', {
  headers: {
    'Authorization': `Bearer ${access_token}`,
    'Accept': 'application/vnd.github+json'
  }
});
const githubUser = await userResponse.json();

// 3. User in DB erstellen/aktualisieren
const user = await upsertUser({
  githubId: githubUser.id.toString(),
  githubUsername: githubUser.login,
  githubAccessToken: access_token, // ⚠️ Sicher speichern!
  email: githubUser.email || `${githubUser.login}@users.noreply.github.com`,
  displayName: githubUser.name || githubUser.login,
  avatarUrl: githubUser.avatar_url
});

// 4. Session erstellen & User zurückgeben
return res.json(user);
```

### GET `/api/auth/github/callback`

Optional: Redirect-basierter Flow (falls Popup blockiert wird):

```
https://deine-backend-domain.de/api/auth/github/callback?code=xxx&state=yyy
```

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
