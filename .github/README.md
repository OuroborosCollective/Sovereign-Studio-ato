# 🚀 GitHub Actions - Android CI/CD

Diese App nutzt bereits den bestehenden **android-release.yml** Workflow.

## Workflows

### Android Release (`.github/workflows/android-release.yml`)

**Trigger:**
- Push auf `main` branch
- Manuell via `workflow_dispatch` (mit optionaler version_name und version_code)

**Output:**
- `*.aab` - Play Store ready Android App Bundle
- `*.apk` - Universal APK
- `SovereignStudio-PlayStore-Release.zip` - Alle Artefakte in einem Archiv

## Setup

### 1. Repository Secrets konfigurieren

Gehe zu: **Settings → Secrets and variables → Actions**

Füge folgende Secrets hinzu:

| Secret Name | Beschreibung | Beispiel |
|------------|--------------|----------|
| `ANDROID_KEYSTORE_BASE64` | Base64 encoded keystore | `$(base64 -w0 keystore.jks)` |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore und Key Passwort | `mein_geheimes_pass` |
| `ANDROID_KEY_ALIAS` | Key Alias | `release` |

### 2. Keystore generieren (falls noch nicht vorhanden)

```bash
# Keystore erstellen
keytool -genkey -v -keystore sovereign-studio.jks \
  -alias release \
  -keyalg RSA -keysize 2048 -validity 10000

# Base64 für GitHub (einzeilig)
base64 -w0 sovereign-studio.jks
```

## Build manuell triggern

1. GitHub Repository → **Actions** Tab
2. "🚀 Android Artifact Release" auswählen
3. "Run workflow" klicken
4. Optional: Version Name und Version Code eingeben

## Output Artefakte

Nach erfolgreichem Build findest du im Actions Tab:

- **SovereignStudio-PlayStore-Release.zip** - Alle Builds
- **AAB**: `release-bundle/SovereignStudio-release.aab`
- **APK**: `release-bundle/SovereignStudio-release.apk`

## Workflow Details

Der Workflow:
1. Dekodiert den Base64 Keystore
2. Baut Release AAB und APK
3. Erstellt ein ZIP Archiv
4. Git Tag mit Version (z.B. v1.0.0)
5. Optional: Marketing Loop Trigger

## Troubleshooting

### Build schlägt fehl wegen Signing

Stelle sicher dass alle Secrets korrekt gesetzt sind:
- `ANDROID_KEYSTORE_BASE64` muss das komplette Base64 des Keystores sein
- `ANDROID_KEYSTORE_PASSWORD` muss mit dem Passwort beim Erstellen übereinstimmen
- `ANDROID_KEY_ALIAS` muss mit dem Alias beim Erstellen übereinstimmen

### Gradle Fehler

Lokal testen:
```bash
cd android && chmod +x gradlew && ./gradlew clean assembleRelease
```