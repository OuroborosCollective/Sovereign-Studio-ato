# Architektur‑Audit‑Pipeline

Diese Pipeline läuft bei **jedem Pull‑Request** und stellt sicher, dass der Code keine versteckten UI‑Fassaden, toten Exporte oder zyklischen Abhängigkeiten enthält.

| Tool | Zweck |
|------|-------|
| **dependency‑cruiser** | Prüft Import‑Graph, stoppt bei Zyklen / Layer‑Verstößen |
| **madge** | Generiert `arch.svg` & blockiert weitere Zyklen |
| **ts‑prune** | Meldet ungenutzte Exporte (Dead Code) |
| **knip** | Findet unbenutzte Dateien, Scripts & Dependencies |
| **eslint-plugin-import** | `import/no-cycle`, `import/no-unused-modules` |

Bei Fehlern schlägt der Job fehl — der PR muss nachgebessert werden.

Lokaler Schnelltest:

```bash
npm ci
npm run audit:arch
```
