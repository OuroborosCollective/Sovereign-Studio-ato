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

<!-- proven-learning:2e4e1b65d673f9c4f93865d40acfe09c57ac0c2cad59cd1a08b17c9a59f9361a -->
## Milvus-Projektion getrennt von kanonischen pgvector-Zahlen ausweisen

- Zeitpunkt: 2026-07-20T16:26:22Z
- Vorgang: integration
- Inhalts-Hash: sha256:2e4e1b65d673f9c4f93865d40acfe09c57ac0c2cad59cd1a08b17c9a59f9361a
- Quellrevision: ff35255d01fefa3e0455028ab4489ef8f75aa952
- Merge-Ziel: main
- Erwarteter PR-Head: ff35255d01fefa3e0455028ab4489ef8f75aa952
- Geänderte Pfade: backend/enterprise_platform/service.py, backend/tests/test_enterprise_platform_contract.py, backend/tests/test_enterprise_platform_service.py, scripts/sovereign-backend/enterprise_platform/service.py, src/features/admin/api/adminApiClient.ts, src/features/admin/components/EnterpriseBackendPanel.tsx
- Problem: Das Admin-Backend zeigte nur PostgreSQL/pgvector-Wissensvektoren. Der vorhandene Milvus-Outbox-Zustand mit pending, syncing, indexed oder blocked war nicht separat sichtbar und konnte dadurch fälschlich als erfolgreiche Milvus-Indexierung verstanden werden.
- Lösung: Die Admin-Statistik weist pgvector-Wissensvektoren und Milvus-Projektionen getrennt aus. Für Milvus werden total, indexed, pending, syncing, blocked sowie Knowledge-Block- und Agent-Pattern-Anteile angezeigt. Ein PostgreSQL-Outbox-Receipt wird nie als direkter Milvus-Collection-Readback bezeichnet. Milvus selbst wird unabhängig mit Create, Insert, Query, Vector Search und Cleanup geprüft; Gotenberg und Tika werden mit einem privaten Marker-Canary geprüft.
- Gültigkeit: Für alle Systeme mit kanonischer relationaler oder pgvector-Persistenz und einem asynchronen externen Vektorindex. Besonders relevant für Admin-Telemetrie, Readiness-Anzeigen und Learning-Pipelines.
- Quellen: OuroborosCollective/Sovereign-Studio-ato@ff35255d01fefa3e0455028ab4489ef8f75aa952:backend/document_ingestion.py; OuroborosCollective/Sovereign-Studio-ato@ff35255d01fefa3e0455028ab4489ef8f75aa952:backend/enterprise_platform/service.py; OuroborosCollective/Sovereign-Studio-ato@ff35255d01fefa3e0455028ab4489ef8f75aa952:backend/knowledge_library.py

### Nachweise

- Canonical deployment mirror (repository_check, SHA-256 19d31b44a1c099fd33e4472f558c96c695a85dca639327560bcd42248c0cd090): Canonical and deployment backend service files have zero mirror mismatches.
- Enterprise platform contract tests (repository_check, SHA-256 4bc172dc714b8d9d64af940f931c5a7530d95f4e70d84fc61d41d55b3dcc0070): Targeted architecture and Admin contract suite completed with 7 passed tests.
- Enterprise platform service tests (repository_check, SHA-256 b9b524cfb5b52057f53a320ff7b6ac4f916a2a417338a3cdaf2fe8919446ef74): Targeted service suite completed with 8 passed tests and exit code zero.
- Python compile (repository_check, SHA-256 aa343bab03398f4df0d12bc10cfe80205f39a71fb6756a581d704d9adb94a636): Canonical backend application compiled successfully with Python py_compile.
- Repository diff contract (repository_check, SHA-256 0e05bbaaeed393f822c20071480267e43472326791338d583a527143f454e7fc): Git diff whitespace and patch integrity check completed successfully.
- Gotenberg Tika document canary (runtime_readback, SHA-256 e27c36974947d7ea4ca3f209dbee6e6ae83f974f138e2d4c58bd6bbde336fa28): Gotenberg generated a PDF and Tika extracted the exact private canary marker.
- Milvus collection runtime canary (runtime_readback, SHA-256 fcec7cbf57dc84602ae841fe981528ac576f89dd7003c83bda529fc0aab31de4): Private Milvus path created a collection, inserted, queried, searched and removed it.

<!-- proven-learning:55ffd93ae01bc44cd139bc6b1de37ef6a5fe054ae30b718bba16bd69294ee30f -->
## Dokument-Canaries müssen denselben Konvertierungspfad wie die Produktions-Ingestion ausführen

- Zeitpunkt: 2026-07-20T16:57:13Z
- Vorgang: integration
- Inhalts-Hash: sha256:55ffd93ae01bc44cd139bc6b1de37ef6a5fe054ae30b718bba16bd69294ee30f
- Quellrevision: 9929a0d1460e916736197724745ea87f12e6831e
- Merge-Ziel: main
- Erwarteter PR-Head: wird beim PR-Gate gebunden
- Geänderte Pfade: tools/sovereign-chatgpt-mcp/document_pipeline.py, tools/sovereign-chatgpt-mcp/server.py, tools/sovereign-chatgpt-mcp/tests/test_document_pipeline.py
- Problem: Der bisherige Gotenberg/Tika-Canary war technisch grün, prüfte aber Chromium HTML→PDF, während der Wissens- und Learning-Pfad Office-Dateien über Gotenbergs LibreOffice-Endpunkt in PDF umwandelt. Dadurch konnte ein grüner Canary den produktionsrelevanten Office-Pfad nicht belegen.
- Lösung: Erzeuge ein minimales deterministisches DOCX flüchtig im Speicher, sende es an `/forms/libreoffice/convert`, validiere PDF-Signatur, Größenlimit und SHA-256, übergebe das PDF an Tika und verifiziere ausschließlich den Marker. Binde den Canary an die immutable MCP-Merge-Revision und bestätige zusätzlich Gotenbergs echten LibreOffice-Access-Log sowie die private Transportgrenze.
- Gültigkeit: Für Dokument-Ingestion-, OCR-, Rendering- und Transformationspipelines, bei denen Healthchecks oder vereinfachte Canaries von der tatsächlichen Produktionsroute abweichen könnten.
- Quellen: OuroborosCollective/Sovereign-Studio-ato@9929a0d1460e916736197724745ea87f12e6831e:.github/workflows/sovereign-chatgpt-mcp.yml; OuroborosCollective/Sovereign-Studio-ato@9929a0d1460e916736197724745ea87f12e6831e:tools/sovereign-chatgpt-mcp/document_pipeline.py; OuroborosCollective/Sovereign-Studio-ato@9929a0d1460e916736197724745ea87f12e6831e:tools/sovereign-chatgpt-mcp/tests/test_document_pipeline.py

### Nachweise

- Immutable MCP main workflow (github_actions, SHA-256 29a03bc55fd2a890b867a6580e7bc46d88ee980de4d0a9d2189ac9cea9a22453): Workflow run 29761310076 passed validation, image publish, digest verification, VPS bootstrap and both live canaries on the exact merge SHA.
- Targeted document pipeline tests (repository_check, SHA-256 aa81ec25a8dbc5d5ceb4e933c835b00f893a3cf689b5bfe36b50d8ee8d31cf61): The targeted MCP document-pipeline suite completed with 15 passed tests.
- Installed MCP runtime identity (runtime_readback, SHA-256 541b3e636fa27df7cf51d61b3f8386fb257483af39749ebada9d2a9282842ca9): The private MCP runs the immutable digest for merge revision 9929a0d with broker, protocol and worker ready.
- Milvus collection lifecycle canary (runtime_readback, SHA-256 1af5bab266494d9e44f1653549f47963e23247f5b78d19d335ad8e3683891b62): The private gateway created, wrote, queried, vector-searched and removed an ephemeral Milvus collection.
- Office document live canary (runtime_readback, SHA-256 01026049ee852a62f0ea4ae4e6adbac2f4d70d6063bfdb612c110844462b3c35): An ephemeral DOCX was converted through Gotenberg LibreOffice to PDF and its marker was extracted by Tika without persistence.

