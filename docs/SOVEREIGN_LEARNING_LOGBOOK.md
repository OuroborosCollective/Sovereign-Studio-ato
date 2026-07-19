# Sovereign Learning Logbook

Dieses Logbuch enthält ausschließlich evidence-geprüfte, deduplizierte Lernmuster. Ein Eintrag ist keine Laufzeitwahrheit für spätere Revisionen und muss vor Wiederverwendung erneut geprüft werden.

<!-- proven-learning:cb268ab1ff7cac28f4f380f2377e6e3513a92a385902fa51f7deff6c7dd026d1 -->
## Carry new MCP capabilities through every release truth plane

- Zeitpunkt: 2026-07-19T17:13:09.928000Z
- Vorgang: integration
- Inhalts-Hash: sha256:cb268ab1ff7cac28f4f380f2377e6e3513a92a385902fa51f7deff6c7dd026d1
- Quellrevision: c2e7c58a8123b909c502a4303ac5f75791bd32e8
- Merge-Ziel: main
- Erwarteter PR-Head: c2e7c58a8123b909c502a4303ac5f75791bd32e8
- Geänderte Pfade: .github/workflows/sovereign-chatgpt-mcp.yml, tools/sovereign-chatgpt-mcp/Dockerfile, tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh, tools/sovereign-chatgpt-mcp/freemium_product_architect_tools.py, tools/sovereign-chatgpt-mcp/launcher.py, tools/sovereign-chatgpt-mcp/tests/test_freemium_product_architect_tools.py
- Problem: A new MCP module can pass isolated unit tests yet remain unavailable or unverifiable when launcher registration, container packaging, VPS installation, release-archive inventory, and exact-head CI are not updated together.
- Lösung: Treat MCP capability integration as one bounded contract: implement deterministic tools with explicit truth fields, add negative security tests, register the module in the launcher, package it in Docker, copy and import-check it in the VPS installer, require it in the release archive, and bind all relevant CI conclusions to the unchanged PR head.
- Gültigkeit: Use for new or renamed Python MCP tool modules in Sovereign-Studio-ato whenever the module must become part of the private Docker MCP runtime.
- Quellen: OuroborosCollective/Sovereign-Studio-ato@c2e7c58a8123b909c502a4303ac5f75791bd32e8:.github/workflows/sovereign-chatgpt-mcp.yml; OuroborosCollective/Sovereign-Studio-ato@c2e7c58a8123b909c502a4303ac5f75791bd32e8:tools/sovereign-chatgpt-mcp/freemium_product_architect_tools.py; OuroborosCollective/Sovereign-Studio-ato@c2e7c58a8123b909c502a4303ac5f75791bd32e8:tools/sovereign-chatgpt-mcp/tests/test_freemium_product_architect_tools.py

### Nachweise

- PR #844 exact-head relevant checks (github_actions, SHA-256 ee4912c8a49b8a90217944bcb529e2487e5a6b693f37298fa4ec9c2725bcaff0): PR head c2e7c58a8123b909c502a4303ac5f75791bd32e8 is clean and mergeable; Validate MCP operator, CodeQL, hardcode scan, code quality, Android, full build/test, runtime contracts, immutable backend image, and Pyre completed successfully with no failed or pending check.

