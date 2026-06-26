# OpenHands Operator-Briefing

Diese Dokumentation beschreibt das OpenHands Operator-Briefing Feature in Sovereign Studio.

## Übersicht

Das Operator-Briefing bietet dem Operator eine kompakte Übersicht über:

- Welche Labels OpenHands starten
- Welcher Kommentar-Marker genutzt wird
- Welche Workflows aktiv sind
- Ob ein Lauf Draft PR, Branch oder nur Log erzeugt
- Welche Secrets/Settings fehlen könnten

## Feature-Architektur

### Runtime-Schicht

```
src/features/product/runtime/openHandsOperatorBriefing.ts
```

Das Runtime-Modul `buildOpenHandsOperatorBriefing` erzeugt strukturierte Briefing-Daten:

```typescript
interface OpenHandsOperatorBriefing {
  sections: readonly BriefingSection[];
  blockedCount: number;
  warningCount: number;
  isBlocked: boolean;
}
```

### UI-Komponente

```
src/features/product/components/OpenHandsOperatorBriefingPanel.tsx
```

Die React-Komponente `OpenHandsOperatorBriefingPanel` zeigt das Briefing an:

- Collapsible Sektionen für mobile Lesbarkeit
- Farbkodierte Status-Indikatoren (grün/gelb/rot)
- Blockierte Konfiguration wird klar angezeigt

## Sektionen

### 1. OpenHands starten

Erläutert die Trigger-Mechanismen:

| Trigger | Beschreibung |
| --- | --- |
| Labels | `openhands-review`, `openhands-fix`, `openhands-agent` starten einen neuen Lauf |
| Kommentar-Marker | `/openhands` in Issue/PR Kommentar triggert ebenfalls |
| Webhook | OpenHands unterstützt auch Webhook-Events |

### 2. Aktive Workflows

Zeigt welche Workflows ausgeführt werden:

- **Draft PR Workflow** - Erstellt Branch und Draft PR nach erfolgreichem Lauf
- **Test Workflow** - Führt Tests aus und meldet Ergebnisse
- **Lint Workflow** - Prüft Code-Qualität und Formatierung

### 3. Lauf-Ergebnis

Dokumentiert die Ausgabe-Typen:

- **Draft PR** - Immer ein Draft PR, kein direkter Merge
- **Branch** - Jeder Lauf erstellt einen separaten Branch mit Änderungen
- **Logs** - Alle Schritte werden geloggt (Admin Console)

### 4. Konfiguration prüfen

Validiert die aktuelle Konfiguration:

- Agent API URL (erforderlich)
- Admin Console URL (optional)
- HTTPS-Anforderung (außer localhost)
- Aktiviert/Ready Status

### 5. Fehlende Secrets/Settings

Listet fehlende Konfigurationen auf:

- Fehlende Agent API URL → Blockiert
- Fehlende Admin Console URL → Warnung
- Fehlendes HTTPS → Blockiert (außer localhost)

## UI-Anzeige

### Status-Farben

| Status | Farbe | Bedeutung |
| --- | --- | --- |
| `ok` | 🟢 Grün (#34d399) | Konfiguriert und funktionsfähig |
| `warning` | 🟡 Gelb (#fbbf24) | Optional fehlt, kann aber starten |
| `blocked` | 🔴 Rot (#fb7185) | Erforderlich fehlt, Start blockiert |
| `info` | 🔵 Cyan (#22d3ee) | Informativ, keine Aktion nötig |

### Mobile Lesbarkeit

- Collapsible Sektionen
- Responsive Layout
- Touch-freundliche Buttons
- Scrollable bei langen Inhalten

## Validierung

Das Briefing zeigt blockierte Konfigurationen:

```
⚠️ OpenHands kann nicht starten, solange blockierende Probleme vorhanden sind.
```

Bei Warnungen:

```
⚡ OpenHands kann starten, aber einige Einstellungen fehlen.
```

## Konfiguration

### Umgebungsvariablen

```bash
# Erforderlich für OpenHands Enterprise
VITE_OPENHANDS_ENABLED=true
VITE_OPENHANDS_AGENT_API_URL=https://your-backend.example.com/openhands

# Optional für Admin Console
VITE_OPENHANDS_ADMIN_CONSOLE_URL=https://openhands-admin.example.com
```

### URL-Anforderungen

- Außerhalb von localhost: **HTTPS erforderlich**
- Localhost: HTTP erlaubt für Entwicklung

## Test-Abdeckung

Das Feature ist vollständig getestet:

- `openHandsOperatorBriefing.test.ts` - Runtime-Logik Tests
- `OpenHandsOperatorBriefingPanel.test.tsx` - UI-Komponenten Tests

### Test-Szenarien

- Erfolgreiche Konfiguration (alle grün)
- Fehlende Agent API URL (blockiert)
- Fehlende Admin Console URL (Warnung)
- HTTP URL außer localhost (blockiert)
- localhost HTTP URL (erlaubt)
- Collapsible Sektionen
- Status-Badges

## Integration

Das Briefing ist im BuilderContainer verfügbar:

1. Klick auf "🤖 Briefing" Button öffnet das Modal
2. Operator sieht alle relevanten Informationen
3. Blockierte Konfiguration wird klar hervorgehoben
4. Modal kann geschlossen werden

## Akzeptanzkriterien (Issue #371)

- [x] Operator kann erkennen, wie OpenHands sauber gestartet wird
- [x] Fehlende Konfiguration wird nicht als Erfolg angezeigt
- [x] Android-/Tablet-Lesbarkeit wird beachtet (collapsible, responsive)
- [x] Validierung wird ausgeführt, soweit möglich

## Sicherheit

- Secrets werden niemals im Briefing angezeigt
- PAT und API-Keys werden maskiert
- HTTPS wird außer localhost erzwungen
