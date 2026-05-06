# 🚀 Sovereign Studio V3 - Leitfaden zur Veröffentlichung im Google Play Store

Herzlichen Glückwunsch! Die App ist nun bereit für den Release. Dieser Leitfaden erklärt dir Schritt-für-Schritt, wie du die Android App (App Bundle - AAB) und die APK erstellst und diese im Google Play Store veröffentlichst.

## 🛠 1. Vorbereitungen & Keystore generieren

Damit Google und deine Nutzer wissen, dass die App wirklich von dir stammt, muss sie kryptografisch signiert werden. Dafür benötigen wir einen **Keystore**.

Wir haben ein Skript vorbereitet, das diesen Keystore automatisch für dich generiert:

1. Führe im Hauptverzeichnis des Projekts folgenden Befehl aus:
   ```bash
   npm run generate-keystore
   ```

2. **WICHTIG:** Dieser Befehl erstellt eine Datei namens `my-release-key.keystore`.
   * **Behalte diese Datei sicher!** Wenn du diese Datei verlierst, kannst du keine Updates mehr für deine App im Play Store hochladen.
   * Lade diese Datei **niemals** in dein öffentliches Git-Repository hoch (sie sollte bereits in der `.gitignore` stehen).

Das Skript gibt auch einen **Base64-kodierten String** aus. Diesen String benötigst du, wenn du eine CI/CD-Pipeline (wie GitHub Actions) nutzt, um die App automatisch bauen zu lassen.

## ⚙️ 2. Umgebungsvariablen (Signatur-Daten) konfigurieren

Der Build-Prozess (`build.gradle`) ist so eingerichtet, dass er die Signatur-Daten aus Umgebungsvariablen ausliest. Bevor du die App bauen kannst, musst du diese Variablen in deinem Terminal setzen (oder in dein CI/CD System eintragen).

Setze folgende Variablen in deinem Terminal, bevor du den Build startest:

```bash
export ANDROID_KEYSTORE_PATH="/absoluter/pfad/zu/deinem/my-release-key.keystore" # z.B. /app/my-release-key.keystore
export ANDROID_KEYSTORE_PASSWORD="sovereign123"
export ANDROID_KEY_ALIAS="sovereign_alias"
export ANDROID_KEY_PASSWORD="sovereign123"
```

*(Hinweis: Wenn du die Passwörter oder den Alias im `gen-key.js` Skript geändert hast, passe diese Werte hier entsprechend an.)*

## 📦 3. App bauen (AAB und APK)

Wir haben in der `package.json` praktische Skripte für dich angelegt.

**Voraussetzung:** Du hast die Umgebungsvariablen aus Schritt 2 gesetzt.

### App Bundle (.aab) erstellen - *Für den Play Store*
Google Play verlangt heutzutage das Android App Bundle (AAB) Format.
Führe folgenden Befehl aus:
```bash
npm run build:aab
```
Du findest das fertige Bundle unter:
`android/app/build/outputs/bundle/release/app-release.aab`

### APK (.apk) erstellen - *Zum manuellen Testen / Teilen*
Wenn du die App direkt an Tester schicken willst, ohne den Play Store zu nutzen, baust du eine APK:
```bash
npm run build:apk
```
Du findest die fertige APK unter:
`android/app/build/outputs/apk/release/app-release.apk`

---

## 🌎 4. Veröffentlichung in der Google Play Console

Nun hast du dein fertiges `.aab` File und kannst es hochladen!

### Schritt 4.1: App anlegen
1. Logge dich in der [Google Play Console](https://play.google.com/console/) ein.
2. Klicke oben rechts auf **"App erstellen"** (Create app).
3. Fülle die Basisdaten aus (App Name, Standard-Sprache, ob es eine App oder ein Spiel ist, ob kostenlos oder kostenpflichtig).
4. Akzeptiere die Richtlinien und klicke auf "App erstellen".

### Schritt 4.2: Interne Tests (Empfohlen)
Bevor du die App für die ganze Welt freigibst, solltest du sie intern testen.
1. Navigiere im linken Menü zu **Testing > Interner Test** (Internal testing).
2. Klicke auf **"Neuen Release erstellen"** (Create new release).
3. **App-Integrität / Play App Signing:** Google wird dich fragen, ob du "Play App Signing" nutzen möchtest. Stimme dem zu! Google verwaltet dann den endgültigen Key. Das ist der Standardweg.
4. Lade deine generierte **`app-release.aab`** Datei im Bereich "App Bundles" hoch.
5. Gib dem Release einen Namen und Release-Notes.
6. Klicke auf "Speichern" und dann "Release überprüfen".
7. Füge die E-Mail-Adressen deiner Tester im Reiter "Tester" hinzu.

### Schritt 4.3: Store-Eintrag ausfüllen
Bevor du einen echten Release ("Produktion") starten kannst, musst du die Store-Infos ausfüllen:
1. Gehe zu **Wachstum > Store-Eintrag > Haupt-Store-Eintrag** (Main store listing).
2. Trage ein: Kurze Beschreibung, Ausführliche Beschreibung.
3. Lade die **Grafiken** hoch:
   - App-Symbol (512x512px)
   - Vorzeigegrafik (1024x500px)
   - Screenshots vom Smartphone (mindestens 2 bis zu 8)
4. Gehe den Bereich **"Inhalt der App"** (App content) im linken Menü ganz unten durch. Fülle alle erforderlichen Fragebögen aus (Datenschutzerklärung, Werbe-ID, Datensicherheit, Altersfreigabe etc.).

### Schritt 4.4: In die Produktion (Live gehen!)
Wenn der interne Test erfolgreich war und alle Store-Informationen ausgefüllt sind:
1. Gehe zu **Release > Produktion** (Production).
2. Klicke auf **"Neuen Release erstellen"**.
3. Wähle aus dem vorherigen internen Test dein bereits hochgeladenes App-Bundle (AAB) aus der "Bibliothek aus" oder lade es hier neu hoch.
4. Speichern, Release überprüfen und dann auf **"Einführung in die Produktion starten"** klicken.

**🎉 Geschafft! Google überprüft nun deine App. Nach ein paar Tagen ist sie im Play Store für alle verfügbar!**
