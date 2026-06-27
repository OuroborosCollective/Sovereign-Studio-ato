# Dependency‑Graph CI Check

Dieses Repository nutzt [Madge](https://github.com/pahen/madge), um den Modul‑Graphen der TypeScript‑/React‑Quellen zu visualisieren und zyklische Abhängigkeiten automatisch zu blockieren.

* **Workflow:** `.github/workflows/dependency-graph.yml`
* **Fehlschlag:** PR schlägt fehl, sobald ein Zyklus erkannt wird.
* **Artefakt:** `deps.svg` wird vom Bot als Kommentar angeheftet.

Für lokale Checks:

```bash
npm ci
npx madge --circular --extensions ts,tsx src
npx madge --image deps.svg --extensions ts,tsx src
```
