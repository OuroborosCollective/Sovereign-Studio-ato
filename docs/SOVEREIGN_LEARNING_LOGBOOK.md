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

<!-- proven-learning:4c01019fedf1e058c640e42c8150cb1c307b1defd3f8245ff89796ff79cd5e87 -->
## Revision-bound MCP self-update registry authentication

- Zeitpunkt: 2026-07-22T21:06:08Z
- Vorgang: fix
- Inhalts-Hash: sha256:4c01019fedf1e058c640e42c8150cb1c307b1defd3f8245ff89796ff79cd5e87
- Quellrevision: 5c98d8791853956edff21ef60e0eb7fbdcea272f
- Merge-Ziel: main
- Erwarteter PR-Head: 5c98d8791853956edff21ef60e0eb7fbdcea272f
- Geänderte Pfade: tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh, tools/sovereign-chatgpt-mcp/deploy/self-update-chatgpt-mcp.sh, tools/sovereign-chatgpt-mcp/tests/test_transactional_installer_contract.py
- Problem: A private MCP self-update may begin before the immutable GHCR tag for the exact merge revision is published, while the local systemd service does not automatically inherit workflow-scoped registry credentials.
- Lösung: Classify authentication denial before not-found publication states; retry only bounded image_not_published or transient registry transport failures; create a temporary per-run Docker auth configuration from protected host metadata with directory mode 0700 and file mode 0600; remove it after execution; preserve exact revision, immutable digest, revision label and cross-runtime parity gates.
- Gültigkeit: Private revision-bound container deployments where merges trigger self-updates asynchronously and CI registry credentials are isolated from the host service context.
- Quellen: OuroborosCollective/Sovereign-Studio-ato@5c98d8791853956edff21ef60e0eb7fbdcea272f:tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh; OuroborosCollective/Sovereign-Studio-ato@5c98d8791853956edff21ef60e0eb7fbdcea272f:tools/sovereign-chatgpt-mcp/deploy/self-update-chatgpt-mcp.sh; OuroborosCollective/Sovereign-Studio-ato@5c98d8791853956edff21ef60e0eb7fbdcea272f:tools/sovereign-chatgpt-mcp/tests/test_transactional_installer_contract.py

### Nachweise

- Changed-path ownership coverage (repository_check, SHA-256 971198cc655d82145b38b5faee6f32b01df0ad2084e4eb8d14323f5a2a443759): All changed MCP deployment and test paths are covered by the repository owner.
- Revision-bound PR evidence graph (repository_check, SHA-256 c8fe70ca64a62221095daba694ad3b8195a30ddcc034c64c748a1f15a730cd7e): Exact-head tests, GitHub checks and CODEOWNERS evidence were bound into a complete release-ready graph.

<!-- proven-learning:c6bff5e4a01f06cb5417c35a3771ff71e42dfaa81b28b93bef82cae7ecf1e49d -->
## Normalize controlled Compose staging binds before boundary validation

- Zeitpunkt: 2026-07-22T21:33:43Z
- Vorgang: fix
- Inhalts-Hash: sha256:c6bff5e4a01f06cb5417c35a3771ff71e42dfaa81b28b93bef82cae7ecf1e49d
- Quellrevision: c6e4e20e030366267f1f818e8c7cfe1b8cf996e0
- Merge-Ziel: main
- Erwarteter PR-Head: c6e4e20e030366267f1f818e8c7cfe1b8cf996e0
- Geänderte Pfade: tools/sovereign-chatgpt-mcp/managed_compose.py, tools/sovereign-chatgpt-mcp/tests/test_freellmapi_managed_compose.py
- Problem: A fixed Compose template can contain a safe relative bind mount. During `docker compose config`, that source is resolved against a controlled temporary staging directory, but validating the temporary absolute path against final deployment allowlists falsely blocks the deployment before any mutation.
- Lösung: Pass the trusted internal staging root into rendered-Compose validation. Canonicalize each bind source; only sources that are true descendants of that staging root are converted to the corresponding relative path beneath the fixed stack deploy root. Then apply the unchanged forbidden-source and allowed-root checks. Sources outside the staging root are never rewritten and remain blocked unless independently allowlisted.
- Gültigkeit: Managed Compose systems that render immutable multi-file templates in a private temporary directory before atomically copying them to a fixed deploy root.
- Quellen: OuroborosCollective/Sovereign-Studio-ato@c6e4e20e030366267f1f818e8c7cfe1b8cf996e0:tools/sovereign-chatgpt-mcp/managed_compose.py; OuroborosCollective/Sovereign-Studio-ato@c6e4e20e030366267f1f818e8c7cfe1b8cf996e0:tools/sovereign-chatgpt-mcp/tests/test_freellmapi_managed_compose.py

### Nachweise

- Changed-path ownership coverage (repository_check, SHA-256 22cafe14b67e852f34b3d376100e19c54cbcd75fb23d790c9d11e25c2d78d768): Both changed MCP control-plane paths have explicit repository owner coverage.
- PR 938 exact-head evidence graph (repository_check, SHA-256 22b6fbd35584a93d81e65d13f1bd0e7a21cbc73df4fadcc48304a2437304c766): The exact PR head has complete test, GitHub Actions and ownership evidence with no graph findings.

<!-- proven-learning:554ab837fad61bd97dd2aa1ebb54cd337fd863f9b2729b20911ead497d5d87a2 -->
## Autonomous Free Revolver route scanner integration

- Zeitpunkt: 2026-07-23T06:07:30+02:00
- Vorgang: integration
- Inhalts-Hash: sha256:554ab837fad61bd97dd2aa1ebb54cd337fd863f9b2729b20911ead497d5d87a2
- Quellrevision: 4f7ce3c15bf057e82919c2266236d542d078e607
- Merge-Ziel: main
- Erwarteter PR-Head: 4f7ce3c15bf057e82919c2266236d542d078e607
- Geänderte Pfade: scripts/sovereign-backend/app.py, scripts/sovereign-backend/docker-compose.yml, scripts/sovereign-backend/llm_route_scanner.py, scripts/sovereign-backend/migrations/036_llm_route_scanner_candidates.sql, scripts/sovereign-backend/tests/test_llm_route_scanner.py, tools/sovereign-chatgpt-mcp/deploy/deploy-sovereign-backend, tools/sovereign-chatgpt-mcp/deploy/rollback-sovereign-backend
- Problem: The supplied standalone scanner would have created a competing web service and could have forwarded arbitrary user prompts to untrusted community endpoints outside the existing PostgreSQL and double-canary truth chain.
- Lösung: Integrate the scanner as scripts/sovereign-backend/llm_route_scanner.py inside the existing Flask backend. Run it only in production as a PostgreSQL-leased worker, enforce HTTPS, public-DNS, no-redirect and bounded-response controls, require two fixed Ping canaries, persist candidate-only evidence, and keep routing_eligible false until a separate verified provider onboarding promotes a source.
- Gültigkeit: Use this pattern when importing autonomous discovery code into a production routing system that already has a canonical provider registry, pricing evidence, route health checks, and fail-closed activation rules.
- Quellen: OuroborosCollective/Sovereign-Studio-ato@4f7ce3c15bf057e82919c2266236d542d078e607:scripts/sovereign-backend/llm_route_scanner.py; OuroborosCollective/Sovereign-Studio-ato@4f7ce3c15bf057e82919c2266236d542d078e607:scripts/sovereign-backend/migrations/036_llm_route_scanner_candidates.sql; OuroborosCollective/Sovereign-Studio-ato@4f7ce3c15bf057e82919c2266236d542d078e607:scripts/sovereign-backend/tests/test_llm_route_scanner.py

### Nachweise

- migration preview (migration_readback, SHA-256 b49811d2d7babe3df27d9a61e3e1ad1f4dac3f58b7f15b93b5f2902dca9597a2): Migration 036 executed successfully in the preview database and was fully rolled back.
- backend compile (repository_check, SHA-256 cb69a58565064e4622772c8815f17f540ccf6f6d516cf0fae85fc7df256722bb): The production backend app compiled successfully after scanner registration.
- deployment contract regression (repository_check, SHA-256 019961133611167ed3ab7e11292670f0dfc4805d1d5207709ae0f70bfbde5911): Six backend deployment and rollback contract tests passed.
- dynamic execution containment (repository_check, SHA-256 7db71cbfe4bc84eb6f9f095790a5349f39f18f81b8d539396bef49a53322fb1c): No uncontained dynamic execution pattern was found in the scanner module.
- existing Free Revolver provider regression (repository_check, SHA-256 30c31cd34e6301d8068177c99d3a3a669b9f9335650363fe690b9447be01bc39): Twenty existing Free Revolver provider runtime tests passed unchanged.
- runtime health schema regression (repository_check, SHA-256 c9fc150cddc3811dcf800f386d14597c4c11108f8e823ab3b6e0058a69d351ed): Three runtime health and required-migration schema contracts passed.
- scanner unit and security tests (repository_check, SHA-256 f08b2f5a5be49a79ca018ae9a11481b8e26f154d97c3daea11dc36d663e06248): Seven focused scanner, SSRF, fixed-canary, lease, deployment and candidate-only tests passed.
- secret literal triage (repository_check, SHA-256 71b9e748a4c58e44cbce932bfb3d609e2c16e6e7f1c5dfd02639225310ef49cd): No secret-shaped literal was found on the changed scanner surfaces.

