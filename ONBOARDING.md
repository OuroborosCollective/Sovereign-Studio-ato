# Developer Onboarding Guide

Willkommen im Team! Dieses Dokument dient als Einstiegshilfe für die Entwicklung an dieser hybriden Mobile-Applikation. Als Senior Architect habe ich diese Struktur entworfen, um Skalierbarkeit, Testbarkeit und eine saubere Trennung von Belangen (Separation of Concerns) zu gewährleisten.

---

## 🏗 Architektur-Übersicht

Das Projekt ist eine **Hybrid-App**, die auf dem **Capacitor** Framework basiert. Es kombiniert eine moderne Web-App (React + Vite) mit nativen Android-Fähigkeiten.

### Kern-Technologien:
- **Frontend Framework:** React 18+ mit TypeScript
- **Build-Tool:** Vite (für extrem schnelle Entwicklungszyklen)
- **State Management:** Redux Toolkit (RTK) für globalen State
- **Mobile Bridge:** Capacitor (bietet Zugriff auf native APIs)
- **AI Integration:** Google Gemini SDK/API
- **Testing:** Vitest & React Testing Library

---

## 📁 Ordnerstruktur & Komponenten

### 1. Web-App (`/src`)
Dies ist das Herzstück der Logik. Wir folgen einem **Feature-basierten Pattern**:
- `features/`: Enthält isolierte Domänen-Logik (z.B. `billing`, `config`, `privacy`). Jedes Feature beinhaltet oft eigene Komponenten und Slices.
- `services/`: Hier liegen die Abstraktionen für externe APIs. 
    - `ai/geminiService.ts`: Zentrale Logik für die Kommunikation mit Google Gemini.
    - `storageService.ts`: Abstraktion für Persistenz.
- `store/`: Die zentrale Redux-Konfiguration. Wir nutzen "Slices", um den State modular zu halten.
- `hooks/`: Custom Hooks (`useGemini`, `useBilling`), um UI und Logik sauber zu trennen.

### 2. Native Schicht (`/android`)
Dies ist ein vollständiges Android-Studio-Projekt.
- Änderungen hier sollten minimal sein und meist über die `capacitor.config.ts` oder native Plugins gesteuert werden.
- Die gebauten Web-Assets landen in `android/app/src/main/assets/public/`.

### 3. CI/CD & Dev-Ops (`/.github`)
- Wir nutzen GitHub Actions für automatisierte Android-Builds und Keystore-Generierung.
- Schau dir `android.yml` an, um den Release-Prozess zu verstehen.

---

## 🚀 Erste Schritte

### Voraussetzungen
- Node.js (Latest LTS)
- Android Studio + SDK
- Java 17 (für Gradle Builds)

### Setup
1. **Abhängigkeiten installieren:**
   bash
   npm install
   
2. **Umgebungsvariablen:**
   Kopiere `.env.example` zu `.env` und trage deinen Gemini API Key ein.
3. **Web-Dev-Server:**
   bash
   npm run dev
   
4. **Android-Synchronisierung:**
   Nach Änderungen am Web-Code oder Plugins:
   bash
   npm run build
   npx cap copy
   npx cap sync android
   

---

## 🧠 Zentrale Konzepte & Patterns

### AI Integration (Gemini)
Die App nutzt den `geminiService`. Beachte, dass KI-Interaktionen asynchron sind und über das `useGemini` Hook konsumiert werden sollten, um Ladezustände korrekt abzufangen.

### State Management
Wir nutzen den **Redux-Toolkit-Ansatz**. 
- Vermeide "Prop Drilling". 
- Globaler State (z.B. User-Level, Billing-Status) gehört in den Store.
- Lokaler UI-State (z.B. ist Modal offen?) gehört in `useState`.

### Testing Strategy
Wir legen großen Wert auf Stabilität.
- **Unit Tests:** Für Services und Utils (`*.test.ts`).
- **Component Tests:** Für kritische UI-Elemente mit Vitest.
- Ausführen mit: `npm run test`

---

## 💡 Tipps für neue Entwickler

1. **Type Safety:** Wir nutzen striktes TypeScript. Vermeide `any`. Definiere Interfaces für API-Antworten in den jeweiligen Service-Ordnern.
2. **Mobile First:** Denke beim Design immer an Touch-Targets und kleine Screens. Nutze die `MobileNavigation.tsx`.
3. **Capacitor Sync:** Wenn du Assets (Bilder in `public/`) hinzufügst, musst du `npx cap copy` ausführen, damit sie auf dem Emulator/Gerät erscheinen.
4. **Error Boundaries:** Die App nutzt eine `ErrorBoundary` Komponente. Achte darauf, kritische Feature-Bereiche damit zu kapseln, um die App bei Fehlern nicht komplett abstürzen zu lassen.
5. **Billing & Paywall:** Änderungen an `billingSlice.ts` beeinflussen den Zugriff auf AI-Features. Teste dies besonders gründlich.

---

## 🛠 Nützliche Befehle
- `npm run build`: Erstellt das Produktions-Bundle.
- `npx cap open android`: Öffnet das Projekt in Android Studio.
- `npm run test`: Startet die Test-Suite.

Willkommen an Bord! Bei Fragen zur Architektur wende dich direkt an mich. Viel Erfolg beim Coden!