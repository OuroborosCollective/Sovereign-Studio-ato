# TypeScript Contract Pilot - Architecture Inventory

**Issue**: #1115  
**Revision**: `559b52c` (HEAD of main, 2026-08-03)  
**Status**: `PLANNED` (pending evidence)

## Ziel

Pilot Compile-Time TypeScript Contract Generation für MCP- und Receipt-Grenzen zu implementieren, um zu untersuchen, ob aus einer kanonischen TypeScript-Typquelle zuverlässig folgende Artefakte erzeugt werden können:

- Strikte Runtime-Validatoren
- JSON-Schema-Projektionen
- MCP `inputSchema` / `outputSchema`
- Validierte strukturierte Toolantworten
- Contract-Hashes für Permission- und Execution-Receipts

## Inventory Findings

### 1. Bestehende TypeScript-Typflächen

#### 1.1 Cloudflare Worker AI Proxy (`cloudflare-worker-ai-proxy/src/index.ts`)

**Interfaces (12)**:
```typescript
interface Env { CF_AI_TOKEN, CF_ACCOUNT_ID, DEFAULT_MODEL, RATE_LIMIT, ... }
interface ChatMessage { role: 'system'|'user'|'assistant', content: string }
interface ChatCompletionRequest { model?, messages, temperature?, max_tokens?, stream? }
interface EmbeddingRequest { model?, input: string|string[] }
interface EmbeddingResponse { object, data[], model, usage }
interface ChatCompletionResponse { id, object, created, model, choices[], usage? }
interface CloudflareAIResponse { result?, success, errors? }
interface ProviderEndpoint { name, url, requiresAuth, authHeader? }
```

**Status**: Kein Zod, kein Schema-Export, nur Interfaces für TypeScript-Kompilierzeit.

#### 1.2 Frontend Types (`src/types/*.d.ts`)

**Runtime Globals** (`src/types/runtime-globals.d.ts`):
```typescript
declare global {
  interface Window {
    __SOVEREIGN_RUNTIME__?: { ... }
    __CAPACITOR__?: { ... }
    __WORKER_BRIDGE__?: { ... }
  }
}
```

**Predictive Types** (`src/predictive/*.d.ts`):
```typescript
interface RuntimeGuardResult {
  riskReduction?: number
  properties?: { confidence?, safety?, ... }
}
```

**Status**: Nur Declaration Merging, keine Runtime-Validierung.

#### 1.3 Predictive Layer (`src/predictive/types.ts`)

**Types**:
```typescript
type SafetyLevel = 'safe' | 'caution' | 'danger'
type PredictionConfidence = 'high' | 'medium' | 'low'
type SignalType = 'guard' | 'warning' | 'block'
```

**Status**: String-Literals ohne Validierung.

### 2. Bestehende Python/Pydantic-Verträge

#### 2.1 Backend Agent Runtime (`backend/agent_runtime/cognitive_swarm_agents.py`)

**MissionIntent** (Pydantic):
```python
class MissionIntent(BaseModel):
    mode: Literal["conversation", "read_only_analysis", "repository_execution"]
    normalized_goal: str = Field(min_length=1, max_length=2000)
    requires_online_tools: bool
    requires_repository_workspace: bool
    learning_scope: list[str] = Field(default_factory=list, max_length=12)
    confidence: float = Field(ge=0.0, le=1.0)
```

**FreeSingleAgentResult** (Pydantic):
```python
class FreeSingleAgentResult(BaseModel):
    assistant_text: str = Field(min_length=1, max_length=8000)
    findings: list[str] = Field(default_factory=list, max_length=20)
    blockers: list[str] = Field(default_factory=list, max_length=20)
```

**DispatchPlan, WorkerReport, JudgeVerdict** (Pydantic):
```python
class DispatchPlan(BaseModel):
    ordered_work: list[str] = Field(min_length=6, max_length=6)
```

**Status**: Pydantic für Backend, kein TypeScript-Dual.

### 3. Bestehende MCP Tool Registry

#### 3.1 MCP Tool Catalog (`tools/sovereign-chatgpt-mcp/`)

**Tool Count**: ~50+ Tools via `@mcp.tool()` Decorator

**Registry Endpoint**: `mcp_tool_contract_registry(include_schemas=False, max_tools=500)`

**Tool Contract Schema** (extracted from `operational_governance_tools.py`):
```python
{
    "name": str,
    "description": str,
    "capabilities": list[str],
    "effect": str,  # "read" | "mutate" | "coordinate"
    "annotations": {
        "readOnlyHint": bool,
        "idempotentHint": bool,
        "destructiveHint": bool,
    },
    "parameters": dict,  # FastMCP inputSchema
    "outputSchema": dict,
    "contractSha256": str,
}
```

**Status**: FastMCP-generierte Schemas, keine kanonische TypeScript-Quelle.

### 4. Contract Surface Analysis

| Surface | Aktuelle Form | Kanonische Quelle | Validierung |
|---------|---------------|-------------------|-------------|
| LLM Proxy Request | TypeScript Interface | Nein | Kompilierzeit |
| LLM Proxy Response | TypeScript Interface | Nein | Kompilierzeit |
| Backend MissionIntent | Pydantic BaseModel | Nein | Runtime |
| MCP Tool Input | FastMCP Schema | Nein | Runtime |
| MCP Tool Output | FastMCP Schema | Nein | Runtime |
| Frontend State | TypeScript + Zustand | Nein | Keine |
| Predictive Guard | TypeScript Literal | Nein | Keine |

### 5. Lücken für Compile-Time Generation

#### 5.1 Fehlende Kanonische Typen
- Keine shared TypeScript-Typen zwischen Frontend und MCP
- Keine Pydantic-zu-TypeScript Sync
- Keine JSON-Schema-Export-Pipeline

#### 5.2 Fehlende Tooling
- Kein `typia` / `ts-runtime` / `zod-to-json-schema`
- Keine Build-Step-Schema-Generierung
- Keine Contract-Hash-Pipeline

#### 5.3 Fehlende Validierungsschicht
- Frontend: Keine Runtime-Validierung
- MCP: Nur FastMCP-generierte Schemas
- Backend: Pydantic nur Backend-seitig

### 6. Pilotvorschlag (Minimal Scope)

#### Option A: Minimaler Pilot (3 Contracts)

1. **`MissionIntent` Pydantic → TypeScript + JSON-Schema**
   - Kanonische Quelle: `backend/agent_runtime/cognitive_swarm_agents.py`
   - Ziel: TypeScript Interface + Zod Schema + MCP inputSchema
   - Werkzeug: `datamodel-code-generator` oder manueller Export

2. **MCP `sovereign_continuity_context_read` Input**
   - Kanonische Quelle: `tools/sovereign-chatgpt-mcp/continuity.py`
   - Ziel: TypeScript Interface + JSON-Schema
   - Werkzeug: FastMCP-Schema-Export → manueller TypeScript

3. **LLM Proxy Chat Completion Request**
   - Kanonische Quelle: `cloudflare-worker-ai-proxy/src/index.ts`
   - Ziel: Zod Schema + JSON-Schema
   - Werkzeug: Manuelle Zod-Definition

#### Option B: Typia-Pilot (Research)

Referenz: https://github.com/samchon/typia (Revision `e829c27390e906cc820e99fa7d068ee4e2f5e809`)

- Abhängigkeit: `typia@^6.0.0` (MIT)
- Build: `ttsc` mit typia-Transformer
- Output: Strikte Validatoren, JSON-Schema

**Risiken**:
- Neue Abhängigkeit mit Build-Transformation
- Keine Garantie für Cloudflare Worker-Kompatibilität
- Zusätzlicher Build-Step erforderlich

### 7. Empfehlung

**Empfohlen: Option A (Minimal Pilot)**

Begründung:
1. Geringste Einführungsrisiken
2. Bereits existierende Typflächen nutzen
3. Ergebnis ist für Menschen überprüfbar
4. Keine neue Abhängigkeit mit Transformations-Overhead

**Nächste Schritte (Pilot Phase 1)**:
1.选择3个最小 Contract-Flächen
2. Manuelle TypeScript+Zod Definition erstellen
3. JSON-Schema generieren
4. Build-Pipeline validieren
5. Draft PR mit Pilot-Implementierung

### 8. Offene Fragen

- [ ] Soll Typia als Research-Abhängigkeit evaluirt werden?
- [ ] Sollen Pydantic-Modelle als kanonische Quelle dienen?
- [ ] Welche Build-Pipeline wird für Schema-Generation verwendet?
- [ ] Sollen Contract-Hashes in Receipts integriert werden?

### 9. Beziehungen

- Untergeordnet zu #1113 – Durable Workflow and Permission Receipt Layer
- Ergänzt #1100 – fail-closed Evidence/Mutation für Rescue und GitHub-Schreibpfade
- Liefert Schema-Projektionen für #1112 – Integration Plan Lane
- Darf #1111 – Bug Evidence Lane nur mit validierten, revisionsgebundenen Receipts beliefern

---

*Letzte Aktualisierung: 2026-08-06 | Revision: 559b52c*
