# Sovereign Studio

Ideenfabrik Auftrag:
Erstelle oder verbessere README und Update History so, dass ein normaler Nutzer versteht, was das Tool kann und wie man es benutzt.

Repository-Kontext:
Repo-Snapshot ist geladen und darf für konkrete Dateiänderungen analysiert werden.

Umsetzung:
- Analysiere zuerst die vorhandene Repo-Struktur und betroffene Dateien.
- Erzeuge echte Änderungen im passenden Codepfad.
- Halte Sovereign Tool getrennt von WASD/Science-Portal Drift.
- Nutze Runtime-Checks, Validierungen und Tests, soweit sinnvoll.
- Keine Mock-, Stub- oder Facade-Live-Pfade.
- Gib am Ende klar aus, was geändert wurde und welche Checks noch offen sind.

## Runtime goals

- Provider output is never trusted blindly.
- Each result must pass the Sovereign five-layer brain contract.
- README requests must update README/docs, not only generated preview artifacts.
- GitHub push uses real repo tree analysis before branch creation.
- Workflows are surfaced to the user before final approval.

## Architecture

node repo, README=yes, workflows=yes, tests=yes, runtime=yes

## Launch readiness

target/repository: 78/100 HEALTHY

## Provider order

1. mlvoca - Existing Mlvoca route
2. pollinations - Existing Pollinations route
3. optional-user-keys - Optional user-key routes
4. ovh-anonymous-code-chat - OVHcloud anonymous code_chat@latest
5. ovh-anonymous-fixed-model - OVHcloud anonymous pinned model
6. puter-js-opt-in - Puter.js opt-in route
7. hf-curated-public-space - Curated Hugging Face public Space
