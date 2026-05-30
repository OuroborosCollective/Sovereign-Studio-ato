# 🚀 GitHub Actions - Android CI/CD

Diese GitHub Action baut automatisch APK und AAB für Play Store.

## Workflows

### Android Build (`.github/workflows/android-build.yml`)

**Trigger:**
- Push auf `main`, `fix/*`, `feat/*` branches
- Manuell via `workflow_dispatch`

**Output:**
- `*.apk` - Debug und Release APKs
- `*.aab` - Play Store ready AAB
- GitHub Release mit Artefakten

## Setup

### 1. Repository Secrets konfigurieren

Gehe zu: **Settings → Secrets and variables → Actions**

Füge folgende Secrets hinzu:

| Secret Name | Beschreibung | Beispiel |
|------------|--------------|----------|
| `ANDROID_KEYSTORE_BASE64` | Base64 encoded keystore | `$(base64 -w0 my-keystore.jks)` |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore Passwort | `mein_geheimes_pass` |
| `ANDROID_KEY_ALIAS` | Key Alias | `sovereign_studio` |
| `ANDROID_KEY_PASSWORD` | Key Passwort | `key_geheimes_pass` |

### 2. Keystore generieren (falls noch nicht vorhanden)

```bash
# Keystore erstellen
keytool -genkey -v -keystore sovereign-studio-release.keystore \
  -alias sovereign_studio \
  -keyalg RSA -keysize 2048 -validity 10000

# Base64 für GitHub (einzeilig)
base64 -w0 sovereign-studio-release.keystore
```

### 3. Keystore in GitHub Secrets speichern

```bash
# Im Terminal:
# Den Base64 output kopieren und als ANDROID_KEYSTORE_BASE64 speichern
```

## Build manuell triggern

1. GitHub Repository → **Actions** Tab
2. "Build Android APK & AAB" auswählen
3. "Run workflow" klicken
4. Build type wählen (release/debug)

## Workflow Jobs

| Job | Beschreibung |
|-----|--------------|
| `build-android` | Java/Android setup, APK & AAB builds |
| `build-web` | Web build für Preview |
| `create-release` | GitHub Release mit APK/AAB |
| `notify` | Build summary |

## Output Artefakte

Nach erfolgreichem Build findest du:

- **APK**: `android/app/build/outputs/apk/release/*.apk`
- **AAB**: `android/app/build/outputs/bundle/release/*.aab`

Download im **Actions** Tab unter "Artifacts".

## Troubleshooting

### Build schlägt fehl wegen Signing

```bash
# Prüfe ob Secrets korrekt gesetzt sind
# Format muss stimmen:
# - ANDROID_KEYSTORE_PATH: /pfad/zu/datei.keystore
# - ANDROID_KEYSTORE_PASSWORD: text
# - ANDROID_KEY_ALIAS: alias_name
# - ANDROID_KEY_PASSWORD: text
```

### Gradle Fehler

```bash
# Lokal testen
cd android && ./gradlew clean && ./gradlew assembleRelease
```

### APK nicht signiert

Stelle sicher dass `ANDROID_KEYSTORE_BASE64` gesetzt ist und korrekt decodiert wird.