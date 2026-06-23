# Sovereign Studio Patch System

Ein System um Änderungen von einer externen lokalen Instanz auf das Live-Main-Repo zu übertragen.

## Übersicht

```
┌─────────────────────────────────────────────────────────────────┐
│  LOKALE EXTERNE INSTANZ                                          │
│  ┌─────────────────┐    ┌─────────────────┐                      │
│  │ generate-local- │───▶│ patches/*.patch │                      │
│  │ patches.sh      │    │ patches/*.sh    │                      │
│  └─────────────────┘    └────────┬────────┘                      │
└──────────────────────────────────┼────────────────────────────────┘
                                   │ (Datei-Transfer)
                                   │ z.B. rsync, USB, SCP
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  MAIN LIVE INSTANZ (dieses Repository)                         │
│  ┌─────────────────┐    ┌─────────────────┐                      │
│  │ apply-workspace-│◀───│ /workspace/*.   │                      │
│  │ patches.py      │    │ patch           │                      │
│  └────────┬────────┘    └─────────────────┘                      │
│           │                                                        │
│           ▼                                                        │
│  ┌─────────────────┐    ┌─────────────────┐                      │
│  │ GitHub PR       │───▶│ Draft PR        │                      │
│  │ (via gh CLI)    │    │ (Main Branch)   │                      │
│  └─────────────────┘    └─────────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
```

## Scripts

### 1. `generate-local-patches.sh` (Lokale Externe Instanz)

Dieses Script läuft auf deiner **lokalen externen Instanz**.

```bash
# Grundlegende Nutzung
./generate-local-patches.sh

# Mit spezifischem Output-Verzeichnis
./generate-local-patches.sh --output-dir ./meine-patches

# Alle Änderungen einschließlich neuer Dateien
./generate-local-patches.sh --all

# Hilfe
./generate-local-patches.sh --help
```

**Was es tut:**
- Generiert `.patch` Dateien aus Git-Commits die noch nicht auf main sind
- Erstellt Diffs von staged und unstaged Änderungen
- Archiviert neue Dateien (mit `--all` oder `--untracked`)
- Erstellt ein TAR-GZPaket zum Teilen

**Output:**
```
./patches-to-share/
├── Sovereign-Studio-ato-commits-20250623-143052.patch
├── Sovereign-Studio-ato-staged-20250623-143052.patch
├── Sovereign-Studio-ato-unstaged-20250623-143052.patch
└── Sovereign-Studio-ato-patches-20250623-143052.tar.gz
```

### 2. `apply-workspace-patches.py` (Main Instanz)

Dieses Script läuft auf der **Main Live Instanz**.

```bash
# Standard: Scannt /workspace nach Patches
python3 apply-workspace-patches.py

# Mit spezifischem Pfad
python3 apply-workspace-patches.py /pfad/zu/patches

# Trockentest (keine Änderungen)
python3 apply-workspace-patches.py --dry-run
```

**Was es tut:**
- Sucht nach `.patch`, `.diff`, `.sh` Dateien
- Wendet Patches auf eine frische Klon des Repos an
- Erstellt einen Feature-Branch
- Pusht zum Remote
- Erstellt einen **Draft Pull Request**

### 3. `apply-external-patches.sh` (Alternative)

Eine Bash-Alternative zu `apply-workspace-patches.py`.

```bash
# Normale Ausführung
./apply-external-patches.sh /workspace/patches

# Trockentest
./apply-external-patches.sh /workspace/patches --dry-run
```

## Workflow

### Schritt 1: Änderungen auf lokaler Instanz vorbereiten

```bash
# In deinem lokalen Repository
cd ~/projects/Sovereign-Studio-ato

# Änderungen machen...

# Patches generieren
./generate-local-patches.sh

# Output: ./patches-to-share/Sovereign-Studio-ato-patches-20250623-143052.tar.gz
```

### Schritt 2: Patches zur Main-Instanz übertragen

**Option A: rsync**
```bash
rsync -av ./patches-to-share/ user@main-server:/workspace/
```

**Option B: SCP**
```bash
scp ./patches-to-share/*.tar.gz user@main-server:/workspace/
```

**Option C: USB-Stick**
1. Tar-Archiv auf USB kopieren
2. USB an Main-Instanz anschließen
3. Dateien nach `/workspace/` kopieren

### Schritt 3: Patches anwenden

```bash
# SSH zur Main-Instanz
ssh user@main-server

cd /workspace/project/Sovereign-Studio-ato

# Patches anwenden
python3 apply-workspace-patches.py /workspace/patches-to-share/
```

### Schritt 4: Pull Request prüfen

Nach erfolgreicher Ausführung:
1. GitHub öffnen: `https://github.com/OuroborosCollective/Sovereign-Studio-ato/pulls`
2. Draft PR finden
3. Review durchführen
4. PR als "Ready for Review" markieren
5. Mergen

## Dateien

| Datei | Beschreibung |
|-------|-------------|
| `generate-local-patches.sh` | Patches auf lokaler Instanz generieren |
| `apply-workspace-patches.py` | Patches auf Main-Instanz anwenden |
| `apply-external-patches.sh` | Bash-Alternative zu Python-Script |

## Tipps

### Patches automatisch finden
Das System sucht automatisch in:
- `/workspace/*.patch`
- `/workspace/*.diff`
- `/workspace/*.sh`
- `/workspace/patches/`

### Patch-Dateien manuell erstellen
```bash
# Einzelne Datei patchen
git diff > my-change.patch

# Mehrere Dateien
git diff --cached > staged.patch
git diff HEAD > all-changes.patch

# Ganze Commits
git format-patch main --stdout > commits.patch
```

### Fehlerbehandlung
Wenn ein Patch fehlschlägt:
1. Das Script versucht `--3way` Merge zuerst
2. Dann `--ignore-whitespace`
3. Bei Misserfolg wird der Patch übersprungen und fortgefahren

### Mehrere Patches
Das System wendet alle gefundenen Patches in Reihenfolge an:
```
patches/
├── fix-001.patch
├── fix-002.patch
└── feature-003.patch
```

## Troubleshooting

### "No patch files found"
- Prüfe ob Dateien die Endung `.patch`, `.diff` oder `.sh` haben
- Prüfe den Pfad: `ls -la /workspace/*.patch`

### "gh: command not found"
- GitHub CLI nicht installiert
- Script pusht trotzdem den Branch
- PR muss manuell erstellt werden

### Patch-Konflikte
- Script nutzt `--force-with-lease` für sichere Pushes
- Bei Konflikten: Branch löschen und erneut versuchen

## Sicherheit

- **Nie direkt auf main pushen** - Immer über PR
- **Draft PRs** - Änderungen sind nicht sofort sichtbar
- **Branch-Isolation** - Jede Anwendung erstellt einen neuen Branch
- **Co-Authored Commits** - Alle Commits sind als "Patch System" markiert
