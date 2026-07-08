# APK Build Anleitung

## Lokale .env Datei

Stelle sicher, dass deine `.env` Datei im Projekt-Root existiert:

```bash
# Im Projekt-Verzeichnis:
cat .env
```

Die Datei muss enthalten:
```env
VITE_GITHUB_OAUTH_CLIENT_ID=Iv23li6M9ZodW9uaIzUw
```

## APK neu bauen

```bash
# 1. Dependencies installieren (falls nicht vorhanden)
pnpm install

# 2. Capacitor Sync (kopiert Web-Assets zu Android)
pnpm run cap sync

# 3. Android APK bauen
pnpm run cap build android

# Die APK liegt dann unter:
# android/app/build/outputs/apk/debug/app-debug.apk
```

## Oder direkt mit Gradle

```bash
cd android
./gradlew assembleDebug
```

## Installation auf Handy

1. APK auf Handy übertragen (ADB, USB, etc.)
2. "Unbekannte Quellen" aktivieren in Android Einstellungen
3. APK installieren und öffnen
