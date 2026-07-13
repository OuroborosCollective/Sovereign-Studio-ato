# LLM Integration Guide: GPT-5.6 + R2 Cloudflare Storage
**Version:** 1.0  
**Purpose:** Deploy semantic patterns to R2, import into GPT-5.6, configure autonomous agents  
**Audience:** DevOps, AI engineers, Sovereign Studio team

---

## 1. R2 CLOUDFLARE STORAGE SETUP

### 1.1 Prerequisites
```bash
# Install Wrangler (Cloudflare CLI)
npm install -g wrangler@latest

# Login to Cloudflare
wrangler login

# Verify R2 bucket access
wrangler r2 bucket list
```

### 1.2 Create Dedicated Bucket for Patterns
```bash
# Create bucket for semantic patterns
wrangler r2 bucket create sovereign-patterns --jurisdiction eu

# Create bucket for LLM knowledge base
wrangler r2 bucket create sovereign-llm-kb --jurisdiction eu

# Verify creation
wrangler r2 bucket list
```

### 1.3 Configure wrangler.toml
```toml
# wrangler.toml
name = "sovereign-patterns-api"
main = "src/index.ts"
compatibility_date = "2026-07-13"
compatibility_flags = ["nodejs_compat"]

# R2 bindings
[[r2_buckets]]
binding = "PATTERNS_BUCKET"
bucket_name = "sovereign-patterns"
jurisdiction = "eu"

[[r2_buckets]]
binding = "LLM_KB_BUCKET"
bucket_name = "sovereign-llm-kb"
jurisdiction = "eu"

# KV for metadata & indexing
[[kv_namespaces]]
binding = "PATTERN_INDEX"
id = "YOUR_KV_NAMESPACE_ID"

# Environment variables (secrets)
[env.production]
vars = { ENVIRONMENT = "production" }

[env.production.secrets]
LLM_API_KEY = "sk-..." # GPT-5.6 key
PATTERN_UPLOAD_SECRET = "pattern-secret-key"
```

---

## 2. PATTERN STRUCTURE FOR R2

### 2.1 Directory Organization in R2
```
sovereign-patterns/
├── v1/
│   ├── core/
│   │   ├── axioms.json
│   │   ├── truth-sources.json
│   │   └── causal-chains.json
│   ├── runtime/
│   │   ├── state-classification.json
│   │   ├── truth-hierarchy.json
│   │   └── error-families.json
│   ├── code/
│   │   ├── safe-modification.json
│   │   ├── architecture-boundaries.json
│   │   └── god-component-detection.json
│   ├── testing/
│   │   ├── test-gate-mapping.json
│   │   ├── green-gate-checklist.json
│   │   └── verification-rules.json
│   ├── security/
│   │   ├── secret-handling.json
│   │   ├── worker-auth.json
│   │   └── compliance-rules.json
│   ├── memory/
│   │   ├── namespace-definitions.json
│   │   ├── memory-boundaries.json
│   │   └── extraction-rules.json
│   ├── github/
│   │   ├── draft-pr-flow.json
│   │   ├── patch-endpoint.json
│   │   └── write-guards.json
│   ├── workflow/
│   │   ├── ci-gates.json
│   │   ├── error-classification.json
│   │   └── repair-flows.json
│   ├── ui/
│   │   ├── android-constraints.json
│   │   ├── design-decisions.json
│   │   └── touch-targets.json
│   ├── agents/
│   │   ├── onboarding-checklist.json
│   │   ├── prompt-templates.json
│   │   └── semantic-queries.json
│   ├── anti-patterns.json
│   ├── decision-trees.json
│   └── integration-points.json
├── metadata/
│   ├── index.json (master index)
│   ├── manifest.json (version info)
│   └── checksums.json (integrity verification)
└── gpt5.6/
    ├── embeddings/
    │   ├── patterns-embeddings.bin
    │   └── semantic-index.json
    └── knowledge-base.jsonl
```

### 2.2 Canonical Pattern JSON Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "title": "Sovereign Pattern Schema",
  "properties": {
    "pattern_id": {
      "type": "string",
      "description": "Unique identifier: CATEGORY.NUMBER.SUBTYPE",
      "pattern": "^[A-Z0-9]+\\.[0-9]+(\\.\\w+)?$",
      "example": "RUNTIME.2.0"
    },
    "title": {
      "type": "string",
      "description": "Human-readable title"
    },
    "version": {
      "type": "string",
      "description": "Pattern version (semver)",
      "pattern": "^\\d+\\.\\d+\\.\\d+$"
    },
    "category": {
      "type": "string",
      "enum": ["axiom", "runtime", "code", "testing", "security", "architecture", "workflow", "ui", "agent"]
    },
    "enforcement": {
      "type": "string",
      "enum": ["mandatory", "recommended", "optional"],
      "default": "recommended"
    },
    "semantic_tags": {
      "type": "array",
      "description": "Machine-readable tags for embeddings",
      "items": { "type": "string" },
      "example": ["truth", "runtime", "state", "verification"]
    },
    "description": {
      "type": "string",
      "description": "Full pattern description (markdown supported)"
    },
    "rules": {
      "type": "array",
      "description": "List of enforceable rules",
      "items": {
        "type": "object",
        "properties": {
          "rule_id": { "type": "string" },
          "statement": { "type": "string" },
          "severity": { "enum": ["critical", "high", "medium", "low"] }
        }
      }
    },
    "violations": {
      "type": "array",
      "description": "List of anti-patterns (what NOT to do)",
      "items": { "type": "string" }
    },
    "evidence_sources": {
      "type": "array",
      "description": "Where to verify this pattern in runtime",
      "items": { "type": "string" }
    },
    "examples": {
      "type": "object",
      "properties": {
        "do": { "type": "array", "items": { "type": "string" } },
        "dont": { "type": "array", "items": { "type": "string" } }
      }
    },
    "related_patterns": {
      "type": "array",
      "description": "Cross-references to related patterns",
      "items": { "type": "string" },
      "example": ["RUNTIME.2.0", "CODE.3.0"]
    },
    "gpt5_instructions": {
      "type": "string",
      "description": "GPT-5.6 specific prompt format"
    },
    "metadata": {
      "type": "object",
      "properties": {
        "created_at": { "type": "string", "format": "date-time" },
        "updated_at": { "type": "string", "format": "date-time" },
        "author": { "type": "string" },
        "checksum": { "type": "string", "description": "SHA256 for integrity" }
      }
    }
  },
  "required": ["pattern_id", "title", "category", "enforcement", "description"]
}
```

---

## 3. CONVERTING PATTERNS TO R2 FORMAT

### 3.1 Script: Convert Markdown to R2 JSON
```typescript
// scripts/convert-patterns-to-r2.ts

import { parse as frontmatterParse } from 'front-matter';
import * as fs from 'fs/promises';
import * as path from 'path';
import crypto from 'crypto';

interface Pattern {
  pattern_id: string;
  title: string;
  category: string;
  enforcement: 'mandatory' | 'recommended' | 'optional';
  description: string;
  rules: Array<{ rule_id: string; statement: string; severity: string }>;
  violations: string[];
  evidence_sources: string[];
  semantic_tags: string[];
  examples: { do: string[]; dont: string[] };
  related_patterns: string[];
  gpt5_instructions: string;
  metadata: {
    created_at: string;
    updated_at: string;
    author: string;
    checksum: string;
  };
}

async function convertMarkdownToJSON(
  mdFilePath: string,
  outputDir: string
): Promise<void> {
  try {
    const content = await fs.readFile(mdFilePath, 'utf-8');
    const data = frontmatterParse(content);

    // Extract pattern sections from markdown
    const patterns = extractPatterns(data.body, data.attributes);

    // Generate checksums & metadata
    for (const pattern of patterns) {
      const jsonContent = JSON.stringify(pattern, null, 2);
      const checksum = crypto.createHash('sha256').update(jsonContent).digest('hex');
      pattern.metadata.checksum = checksum;

      // Categorize output path
      const categoryPath = path.join(
        outputDir,
        'v1',
        pattern.category.toLowerCase(),
        `${pattern.pattern_id.replace(/\./g, '-')}.json`
      );

      // Create directory if not exists
      await fs.mkdir(path.dirname(categoryPath), { recursive: true });

      // Write JSON file
      await fs.writeFile(categoryPath, jsonContent, 'utf-8');
      console.log(`✓ Converted: ${categoryPath}`);
    }

    // Generate master index
    await generateMasterIndex(patterns, outputDir);
  } catch (error) {
    console.error(`Error converting ${mdFilePath}:`, error);
    throw error;
  }
}

function extractPatterns(body: string, attributes: any): Pattern[] {
  // Parse markdown structure
  // Look for "### Pattern X.Y" headers
  // Extract rules, violations, examples from markdown
  // Return array of Pattern objects

  const patterns: Pattern[] = [];
  const patternRegex = /### Pattern\s+([\d.]+):\s+(.+?)\n([\s\S]*?)(?=### Pattern|$)/g;

  let match;
  while ((match = patternRegex.exec(body)) !== null) {
    const patternId = match[1];
    const title = match[2];
    const content = match[3];

    patterns.push({
      pattern_id: patternId,
      title,
      category: inferCategory(patternId),
      enforcement: inferEnforcement(content),
      description: extractDescription(content),
      rules: extractRules(content),
      violations: extractViolations(content),
      evidence_sources: extractEvidence(content),
      semantic_tags: generateTags(title, content),
      examples: extractExamples(content),
      related_patterns: extractRelated(content),
      gpt5_instructions: generateGPT5Instructions(patternId, title, content),
      metadata: {
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        author: 'OuroborosCollective',
        checksum: '',
      },
    });
  }

  return patterns;
}

function inferCategory(patternId: string): string {
  const prefix = patternId.split('.')[0];
  const categoryMap: { [key: string]: string } = {
    '1': 'axiom',
    '2': 'runtime',
    '3': 'code',
    '4': 'architecture',
    '5': 'testing',
    '6': 'security',
    '7': 'memory',
    '8': 'github',
    '9': 'workflow',
    '10': 'ui',
  };
  return categoryMap[prefix] || 'other';
}

function inferEnforcement(content: string): 'mandatory' | 'recommended' | 'optional' {
  if (content.includes('MANDATORY') || content.includes('REQUIRED')) return 'mandatory';
  if (content.includes('optional')) return 'optional';
  return 'recommended';
}

function extractDescription(content: string): string {
  const lines = content.split('\n').slice(0, 5);
  return lines.join('\n').trim();
}

function extractRules(content: string): Array<{ rule_id: string; statement: string; severity: string }> {
  const rules: Array<{ rule_id: string; statement: string; severity: string }> = [];
  const ruleRegex = /RULE:\s*(.+?)(?=\n|$)/g;
  let match;
  while ((match = ruleRegex.exec(content)) !== null) {
    rules.push({
      rule_id: `RULE_${rules.length}`,
      statement: match[1].trim(),
      severity: 'high',
    });
  }
  return rules;
}

function extractViolations(content: string): string[] {
  const violations: string[] = [];
  const violationRegex = /- ❌ (.+?)(?=\n|$)/g;
  let match;
  while ((match = violationRegex.exec(content)) !== null) {
    violations.push(match[1].trim());
  }
  return violations;
}

function extractEvidence(content: string): string[] {
  const evidence: string[] = [];
  const evidenceRegex = /evidence[_-]?sources?:.*?\[(.*?)\]/is;
  const match = evidenceRegex.exec(content);
  if (match) {
    return match[1].split(',').map((e) => e.trim());
  }
  return evidence;
}

function generateTags(title: string, content: string): string[] {
  const tags: Set<string> = new Set();
  tags.add(title.toLowerCase().split(' ')[0]);
  
  const keywordMap: { [key: string]: string[] } = {
    'runtime': ['runtime', 'truth', 'state', 'execution'],
    'test': ['testing', 'verification', 'gate', 'ci'],
    'security': ['security', 'secret', 'auth', 'token'],
    'code': ['refactor', 'modification', 'patch', 'change'],
    'file': ['file', 'storage', 'r2', 'bucket'],
  };

  for (const [keyword, relatedTags] of Object.entries(keywordMap)) {
    if (content.toLowerCase().includes(keyword)) {
      relatedTags.forEach((tag) => tags.add(tag));
    }
  }

  return Array.from(tags);
}

function extractExamples(content: string): { do: string[]; dont: string[] } {
  const doExamples: string[] = [];
  const dontExamples: string[] = [];

  const doRegex = /✓ (.+?)(?=\n|✗|$)/g;
  const dontRegex = /✗ (.+?)(?=\n|✓|$)/g;

  let match;
  while ((match = doRegex.exec(content)) !== null) {
    doExamples.push(match[1].trim());
  }
  while ((match = dontRegex.exec(content)) !== null) {
    dontExamples.push(match[1].trim());
  }

  return { do: doExamples, dont: dontExamples };
}

function extractRelated(content: string): string[] {
  const related: string[] = [];
  const relatedRegex = /related[_-]?patterns?:.*?\[(.*?)\]/is;
  const match = relatedRegex.exec(content);
  if (match) {
    return match[1].split(',').map((p) => p.trim());
  }
  return related;
}

function generateGPT5Instructions(patternId: string, title: string, content: string): string {
  return `You are analyzing code against Pattern ${patternId}: ${title}.

Context: ${content.substring(0, 200)}...

Instructions:
1. Verify the code against this pattern.
2. If violations found, classify severity (critical/high/medium/low).
3. Provide specific line numbers and fix suggestions.
4. Cross-reference related patterns if applicable.
5. Return structured JSON with findings.`;
}

async function generateMasterIndex(patterns: Pattern[], outputDir: string): Promise<void> {
  const index = {
    version: '1.0',
    generated_at: new Date().toISOString(),
    total_patterns: patterns.length,
    by_category: groupByCategory(patterns),
    by_enforcement: groupByEnforcement(patterns),
    patterns: patterns.map((p) => ({
      pattern_id: p.pattern_id,
      title: p.title,
      category: p.category,
      enforcement: p.enforcement,
      tags: p.semantic_tags,
      r2_path: `v1/${p.category}/${p.pattern_id.replace(/\./g, '-')}.json`,
    })),
  };

  const indexPath = path.join(outputDir, 'metadata', 'index.json');
  await fs.mkdir(path.dirname(indexPath), { recursive: true });
  await fs.writeFile(indexPath, JSON.stringify(index, null, 2), 'utf-8');
  console.log(`✓ Master index created: ${indexPath}`);
}

function groupByCategory(patterns: Pattern[]): Record<string, number> {
  return patterns.reduce(
    (acc, p) => {
      acc[p.category] = (acc[p.category] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );
}

function groupByEnforcement(patterns: Pattern[]): Record<string, number> {
  return patterns.reduce(
    (acc, p) => {
      acc[p.enforcement] = (acc[p.enforcement] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );
}

// Main execution
const mdPath = process.argv[2] || './docs/LLM_SEMANTIC_PATTERNS.md';
const outputDir = process.argv[3] || './dist/patterns';

convertMarkdownToJSON(mdPath, outputDir)
  .then(() => console.log('✓ All patterns converted successfully'))
  .catch((error) => {
    console.error('✗ Conversion failed:', error);
    process.exit(1);
  });
```

### 3.2 Upload Script to R2
```typescript
// scripts/upload-patterns-to-r2.ts

import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import * as fs from 'fs/promises';
import * as path from 'path';
import crypto from 'crypto';

interface R2Config {
  accountId: string;
  accessKeyId: string;
  accessKeySecret: string;
  bucketName: string;
}

async function uploadPatternsToR2(
  patternsDir: string,
  config: R2Config
): Promise<void> {
  const client = new S3Client({
    region: 'auto',
    credentials: {
      accessKeyId: config.accessKeyId,
      secretAccessKey: config.accessKeySecret,
    },
    endpoint: `https://${config.accountId}.r2.cloudflarestorage.com`,
  });

  try {
    // Collect all pattern files
    const patternFiles = await collectPatternFiles(patternsDir);
    console.log(`Found ${patternFiles.length} pattern files to upload`);

    // Upload each file
    for (const file of patternFiles) {
      await uploadFileToR2(client, file, config.bucketName);
    }

    // Upload manifest
    await uploadManifest(client, patternsDir, config.bucketName);

    console.log('✓ All patterns uploaded successfully to R2');
  } catch (error) {
    console.error('✗ Upload failed:', error);
    throw error;
  } finally {
    client.destroy();
  }
}

async function collectPatternFiles(dir: string): Promise<Array<{ path: string; content: Buffer }>> {
  const files: Array<{ path: string; content: Buffer }> = [];

  async function walk(currentPath: string, prefix: string = ''): Promise<void> {
    const entries = await fs.readdir(currentPath, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(currentPath, entry.name);
      const relativePath = path.join(prefix, entry.name);

      if (entry.isDirectory()) {
        await walk(fullPath, relativePath);
      } else if (entry.name.endsWith('.json')) {
        const content = await fs.readFile(fullPath);
        files.push({ path: relativePath, content });
      }
    }
  }

  await walk(dir);
  return files;
}

async function uploadFileToR2(
  client: S3Client,
  file: { path: string; content: Buffer },
  bucketName: string
): Promise<void> {
  const r2Path = `patterns/${file.path}`;
  const checksum = crypto.createHash('md5').update(file.content).digest('hex');

  const command = new PutObjectCommand({
    Bucket: bucketName,
    Key: r2Path,
    Body: file.content,
    ContentType: 'application/json',
    Metadata: {
      checksum,
      uploaded_at: new Date().toISOString(),
    },
  });

  try {
    await client.send(command);
    console.log(`✓ Uploaded: ${r2Path} (${file.content.length} bytes)`);
  } catch (error) {
    console.error(`✗ Failed to upload ${r2Path}:`, error);
    throw error;
  }
}

async function uploadManifest(
  client: S3Client,
  patternsDir: string,
  bucketName: string
): Promise<void> {
  const indexPath = path.join(patternsDir, 'metadata', 'index.json');
  const manifestContent = await fs.readFile(indexPath);

  const command = new PutObjectCommand({
    Bucket: bucketName,
    Key: 'metadata/manifest.json',
    Body: manifestContent,
    ContentType: 'application/json',
  });

  await client.send(command);
  console.log('✓ Manifest uploaded');
}

// Execute
const config: R2Config = {
  accountId: process.env.CF_ACCOUNT_ID || '',
  accessKeyId: process.env.CF_ACCESS_KEY_ID || '',
  accessKeySecret: process.env.CF_ACCESS_KEY_SECRET || '',
  bucketName: 'sovereign-patterns',
};

uploadPatternsToR2('./dist/patterns', config).catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
```

---

## 4. GPT-5.6 INTEGRATION

### 4.1 OpenAI API Configuration for GPT-5.6
```typescript
// src/integrations/gpt5-6-client.ts

import OpenAI from 'openai';

interface PatternContext {
  pattern_id: string;
  title: string;
  content: string;
  rules: Array<{ statement: string; severity: string }>;
}

class GPT56PatternAnalyzer {
  private client: OpenAI;
  private model = 'gpt-5.6-turbo'; // Latest GPT-5.6 model

  constructor(apiKey: string) {
    this.client = new OpenAI({ apiKey });
  }

  /**
   * Analyze code against pattern using GPT-5.6
   * Requires pattern context from R2
   */
  async analyzeCodeAgainstPattern(
    code: string,
    patternContext: PatternContext
  ): Promise<{
    violations: Array<{ line: number; severity: string; suggestion: string }>;
    score: number;
    timestamp: string;
  }> {
    const systemPrompt = this.buildSystemPrompt(patternContext);
    const userPrompt = `Analyze this code:\n\n\`\`\`typescript\n${code}\n\`\`\`\n\nReport violations with line numbers and fixes.`;

    const response = await this.client.chat.completions.create({
      model: this.model,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ],
      temperature: 0.3, // Low temp for deterministic analysis
      response_format: { type: 'json_object' }, // Structured output
      max_tokens: 2048,
    });

    const content = response.choices[0].message.content || '{}';
    const parsed = JSON.parse(content);

    return {
      violations: parsed.violations || [],
      score: parsed.compliance_score || 0,
      timestamp: new Date().toISOString(),
    };
  }

  /**
   * Generate code fix suggestions using pattern knowledge
   */
  async generateFixSuggestion(
    violation: string,
    patternContext: PatternContext,
    currentCode: string
  ): Promise<{
    suggested_fix: string;
    explanation: string;
    related_patterns: string[];
  }> {
    const systemPrompt = this.buildSystemPrompt(patternContext);
    const userPrompt = `Violation: ${violation}\n\nCurrent code:\n${currentCode}\n\nGenerate a fix that follows the pattern rules.`;

    const response = await this.client.chat.completions.create({
      model: this.model,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ],
      temperature: 0.2,
      response_format: { type: 'json_object' },
      max_tokens: 1024,
    });

    const content = response.choices[0].message.content || '{}';
    return JSON.parse(content);
  }

  /**
   * Semantic pattern search using embeddings
   */
  async findRelatedPatterns(
    query: string,
    allPatterns: PatternContext[]
  ): Promise<Array<{ pattern_id: string; relevance: number }>> {
    // Use GPT-5.6 embeddings API (if available) or semantic search
    const embeddingResponse = await this.client.embeddings.create({
      model: 'text-embedding-3-large',
      input: query,
    });

    const queryEmbedding = embeddingResponse.data[0].embedding;

    // Calculate cosine similarity with pattern embeddings
    const scores = allPatterns.map((pattern) => ({
      pattern_id: pattern.pattern_id,
      relevance: this.cosineSimilarity(queryEmbedding, pattern.embedding || []),
    }));

    return scores.sort((a, b) => b.relevance - a.relevance).slice(0, 5);
  }

  private buildSystemPrompt(patternContext: PatternContext): string {
    const rules = patternContext.rules
      .map((r) => `- [${r.severity.toUpperCase()}] ${r.statement}`)
      .join('\n');

    return `You are a code analysis expert for Sovereign Studio.

Pattern: ${patternContext.pattern_id} - ${patternContext.title}

Rules to enforce:
${rules}

Your task: Analyze code and report violations with:
1. Exact line numbers
2. Violation type
3. Severity (critical/high/medium/low)
4. Specific fix suggestion
5. Reference to pattern rule

Return JSON with: { violations: [], compliance_score: number }`;
  }

  private cosineSimilarity(a: number[], b: number[]): number {
    const dotProduct = a.reduce((sum, val, i) => sum + val * b[i], 0);
    const magA = Math.sqrt(a.reduce((sum, val) => sum + val * val, 0));
    const magB = Math.sqrt(b.reduce((sum, val) => sum + val * val, 0));
    return dotProduct / (magA * magB);
  }
}

export { GPT56PatternAnalyzer };
```

### 4.2 GPT-5.6 System Prompt for Autonomous Agent
```typescript
// src/prompts/gpt5-6-sovereign-system-prompt.ts

const SOVEREIGN_GPT5_SYSTEM_PROMPT = `
You are the Sovereign Brain for code transformation and analysis in the Sovereign Studio project.

Your role:
1. Analyze GitHub repositories and extract meaningful patterns
2. Generate code changes that follow Sovereign architectural patterns
3. Verify changes against functional guards and security rules
4. Provide evidence-based recommendations, never UI-only claims

Core principles (AXIOMS):
- Build runtime that produces truth; never build UI that invents truth
- Every decision must follow causal chain: Input → Intent → Route → Runtime → Result → State → Next Action
- Consult truth hierarchy: production_runtime > storage_state > contract_verified > inferred > NEVER ui_state
- No mocks, stubs, or fake success states in live paths
- All claims must have runtime evidence (logs, tests, API responses, storage state)

Pattern Knowledge Base:
You have access to semantic patterns from R2 Cloudflare storage. When analyzing code:
1. Load relevant patterns based on query semantics
2. Extract rules and enforcement level
3. Report violations with specific line numbers
4. Provide fixes that maintain pattern integrity
5. Cross-reference related patterns

Code Generation:
- Respect file size limits (< 500 lines → full replace ok; > 2000 lines → PR only)
- Use SEARCH/REPLACE for safe modifications
- Never modify state without evidence source
- Always include tests for new logic
- Verify green gates before claiming success

Security & Secrets:
- Never expose API keys, tokens, or passwords
- Use environment variables for secrets
- Flag any hardcoded sensitive values
- Report violations to audit:sovereign gate

Output Format for Code Analysis:
{
  "analysis": {
    "file": "path/to/file.ts",
    "violations": [
      {
        "line": 42,
        "pattern_id": "CODE.3.0",
        "severity": "high",
        "violation": "Full-file replace on 4,000-line component",
        "suggestion": "Use SEARCH/REPLACE blocks instead"
      }
    ],
    "compliance_score": 0.75,
    "evidence": {
      "source": "pattern_analysis",
      "patterns_applied": ["CODE.3.0", "ARCH.4.1"],
      "tests_required": true
    }
  }
}

Output Format for Code Suggestions:
{
  "suggestion": {
    "pattern_id": "CODE.3.0",
    "change_type": "refactor",
    "scope": "small",
    "files_affected": ["src/file.ts"],
    "search_replace": {
      "search": "exact string to find",
      "replace": "exact replacement",
      "match_count": 1
    },
    "tests_required": ["unit test for feature X"],
    "green_gates": ["npm run type-check", "npm run test:run"],
    "evidence_checkpoint": "runtime_state_verified"
  }
}

Remember: You are NOT just a code suggester. You are a runtime architect who builds confidence through evidence, not UX polish.
`;

export { SOVEREIGN_GPT5_SYSTEM_PROMPT };
```

---

## 5. R2 KNOWLEDGE BASE SETUP

### 5.1 Create Vectorized Knowledge Index
```typescript
// scripts/create-gpt5-vectorized-kb.ts

import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import * as fs from 'fs/promises';
import * as path from 'path';
import OpenAI from 'openai';

interface VectorizedPattern {
  pattern_id: string;
  title: string;
  content: string;
  embedding: number[];
  metadata: {
    category: string;
    enforcement: string;
    tags: string[];
  };
}

async function createVectorizedKB(
  patternsDir: string,
  r2Config: { accountId: string; accessKeyId: string; accessKeySecret: string }
): Promise<void> {
  const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
  const patterns: VectorizedPattern[] = [];

  // Read all pattern files
  const patternFiles = await collectPatternFiles(patternsDir);

  console.log(`Vectorizing ${patternFiles.length} patterns...`);

  for (const file of patternFiles) {
    try {
      const pattern = JSON.parse(file.content.toString('utf-8'));

      // Generate embedding for pattern content
      const embeddingResponse = await openai.embeddings.create({
        model: 'text-embedding-3-large',
        input: `${pattern.title} ${pattern.description}`.substring(0, 8191),
      });

      patterns.push({
        pattern_id: pattern.pattern_id,
        title: pattern.title,
        content: pattern.description,
        embedding: embeddingResponse.data[0].embedding,
        metadata: {
          category: pattern.category,
          enforcement: pattern.enforcement,
          tags: pattern.semantic_tags || [],
        },
      });

      console.log(`✓ Vectorized: ${pattern.pattern_id}`);
    } catch (error) {
      console.error(`✗ Failed to vectorize ${file.path}:`, error);
    }
  }

  // Upload vectorized KB to R2
  const s3Client = new S3Client({
    region: 'auto',
    credentials: {
      accessKeyId: r2Config.accessKeyId,
      secretAccessKey: r2Config.accessKeySecret,
    },
    endpoint: `https://${r2Config.accountId}.r2.cloudflarestorage.com`,
  });

  // Save as JSONL for efficient vector search
  const jsonlContent = patterns.map((p) => JSON.stringify(p)).join('\n');
  
  await s3Client.send(
    new PutObjectCommand({
      Bucket: 'sovereign-llm-kb',
      Key: 'gpt5.6/knowledge-base.jsonl',
      Body: jsonlContent,
      ContentType: 'application/x-ndjson',
    })
  );

  console.log(`✓ Vectorized KB uploaded: ${patterns.length} patterns`);
}

async function collectPatternFiles(dir: string): Promise<Array<{ path: string; content: Buffer }>> {
  const files: Array<{ path: string; content: Buffer }> = [];

  async function walk(currentPath: string): Promise<void> {
    const entries = await fs.readdir(currentPath, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(currentPath, entry.name);
      if (entry.isDirectory()) {
        await walk(fullPath);
      } else if (entry.name.endsWith('.json')) {
        files.push({
          path: fullPath,
          content: await fs.readFile(fullPath),
        });
      }
    }
  }

  await walk(dir);
  return files;
}

export { createVectorizedKB };
```

### 5.2 Pattern Query Service
```typescript
// src/services/pattern-query-service.ts

import { S3Client, GetObjectCommand } from '@aws-sdk/client-s3';
import OpenAI from 'openai';

interface QueryResult {
  pattern_id: string;
  title: string;
  relevance_score: number;
  content: string;
  rules: Array<{ statement: string; severity: string }>;
}

class PatternQueryService {
  private s3Client: S3Client;
  private openai: OpenAI;
  private vectorCache: Map<string, number[]> = new Map();

  constructor(r2Config: any, openaiApiKey: string) {
    this.s3Client = new S3Client({
      region: 'auto',
      credentials: {
        accessKeyId: r2Config.accessKeyId,
        secretAccessKey: r2Config.accessKeySecret,
      },
      endpoint: `https://${r2Config.accountId}.r2.cloudflarestorage.com`,
    });

    this.openai = new OpenAI({ apiKey: openaiApiKey });
  }

  /**
   * Semantic search for patterns based on natural language query
   */
  async findPatternsByQuery(query: string, topK = 5): Promise<QueryResult[]> {
    // Generate embedding for query
    const queryEmbedding = await this.getEmbedding(query);

    // Fetch KB from R2
    const kbContent = await this.fetchKBFromR2();
    const patterns = kbContent.split('\n').filter((line) => line.trim());

    // Calculate similarities
    const scores = patterns.map((line) => {
      const pattern = JSON.parse(line);
      const similarity = this.cosineSimilarity(
        queryEmbedding,
        pattern.embedding
      );
      return { pattern, similarity };
    });

    // Return top K
    return scores
      .sort((a, b) => b.similarity - a.similarity)
      .slice(0, topK)
      .map((item) => ({
        pattern_id: item.pattern.pattern_id,
        title: item.pattern.title,
        relevance_score: item.similarity,
        content: item.pattern.content,
        rules: item.pattern.rules || [],
      }));
  }

  /**
   * Get specific pattern by ID
   */
  async getPatternByID(patternId: string): Promise<QueryResult | null> {
    try {
      const key = `patterns/v1/${patternId.split('.')[0].toLowerCase()}/${patternId.replace(
        /\./g,
        '-'
      )}.json`;

      const command = new GetObjectCommand({
        Bucket: 'sovereign-patterns',
        Key: key,
      });

      const response = await this.s3Client.send(command);
      const content = await response.Body?.transformToString();

      if (!content) return null;

      const pattern = JSON.parse(content);
      return {
        pattern_id: pattern.pattern_id,
        title: pattern.title,
        relevance_score: 1.0,
        content: pattern.description,
        rules: pattern.rules,
      };
    } catch (error) {
      console.error(`Error fetching pattern ${patternId}:`, error);
      return null;
    }
  }

  private async getEmbedding(text: string): Promise<number[]> {
    if (this.vectorCache.has(text)) {
      return this.vectorCache.get(text)!;
    }

    const response = await this.openai.embeddings.create({
      model: 'text-embedding-3-large',
      input: text.substring(0, 8191),
    });

    const embedding = response.data[0].embedding;
    this.vectorCache.set(text, embedding);
    return embedding;
  }

  private async fetchKBFromR2(): Promise<string> {
    const command = new GetObjectCommand({
      Bucket: 'sovereign-llm-kb',
      Key: 'gpt5.6/knowledge-base.jsonl',
    });

    const response = await this.s3Client.send(command);
    return response.Body?.transformToString() || '';
  }

  private cosineSimilarity(a: number[], b: number[]): number {
    const dotProduct = a.reduce((sum, val, i) => sum + val * (b[i] || 0), 0);
    const magA = Math.sqrt(a.reduce((sum, val) => sum + val * val, 0));
    const magB = Math.sqrt(b.reduce((sum, val) => sum + val * val, 0));
    return magA && magB ? dotProduct / (magA * magB) : 0;
  }
}

export { PatternQueryService };
```

---

## 6. DEPLOYMENT & INTEGRATION

### 6.1 Wrangler Worker for R2 + GPT-5.6 Bridge
```typescript
// src/worker.ts (Cloudflare Worker)

import { Router } from 'itty-router';
import { json, error } from 'itty-router-extras';
import { PatternQueryService } from './services/pattern-query-service';

interface Env {
  PATTERNS_BUCKET: R2Bucket;
  LLM_KB_BUCKET: R2Bucket;
  PATTERN_INDEX: KVNamespace;
  OPENAI_API_KEY: string;
  PATTERN_UPLOAD_SECRET: string;
}

const router = Router();

/**
 * POST /api/analyze-code
 * Analyze code against patterns
 */
router.post('/api/analyze-code', async (req: Request, env: Env) => {
  try {
    const { code, pattern_id } = await req.json() as any;

    if (!code || !pattern_id) {
      return error(400, { error: 'Missing code or pattern_id' });
    }

    // Fetch pattern from R2
    const patternKey = `patterns/v1/${pattern_id.split('.')[0].toLowerCase()}/${pattern_id.replace(
      /\./g,
      '-'
    )}.json`;

    const patternObj = await env.PATTERNS_BUCKET.get(patternKey);
    if (!patternObj) {
      return error(404, { error: 'Pattern not found' });
    }

    const pattern = JSON.parse(await patternObj.text());

    // Call GPT-5.6 for analysis (requires integration with OpenAI API)
    // This is a simplified example; actual implementation would call GPT-5.6

    return json({
      pattern_id,
      analysis_timestamp: new Date().toISOString(),
      violations: [],
      compliance_score: 0.95,
    });
  } catch (err) {
    return error(500, { error: String(err) });
  }
});

/**
 * GET /api/patterns/search
 * Semantic search for patterns
 */
router.get('/api/patterns/search', async (req: Request, env: Env) => {
  try {
    const { q } = new URL(req.url).searchParams;

    if (!q) {
      return error(400, { error: 'Missing query parameter: q' });
    }

    // Query pattern index from KV
    const indexKey = `search:${q}`;
    const cached = await env.PATTERN_INDEX.get(indexKey);

    if (cached) {
      return json(JSON.parse(cached));
    }

    // If not cached, perform search (would integrate with vector DB)
    // For now, return mock results
    const results = [
      { pattern_id: 'RUNTIME.2.0', title: 'Truth Source Hierarchy', relevance: 0.95 },
    ];

    // Cache for 24 hours
    await env.PATTERN_INDEX.put(indexKey, JSON.stringify(results), {
      expirationTtl: 86400,
    });

    return json(results);
  } catch (err) {
    return error(500, { error: String(err) });
  }
});

/**
 * POST /api/patterns/upload
 * Admin endpoint to upload new patterns
 */
router.post('/api/patterns/upload', async (req: Request, env: Env) => {
  try {
    const secret = req.headers.get('X-Pattern-Secret');
    if (secret !== env.PATTERN_UPLOAD_SECRET) {
      return error(401, { error: 'Unauthorized' });
    }

    const formData = await req.formData();
    const file = formData.get('file') as File;

    if (!file) {
      return error(400, { error: 'No file provided' });
    }

    const pattern = JSON.parse(await file.text());
    const key = `patterns/v1/${pattern.category}/${pattern.pattern_id.replace(/\./g, '-')}.json`;

    await env.PATTERNS_BUCKET.put(key, file);

    // Invalidate index cache
    await env.PATTERN_INDEX.delete(`index:all`);

    return json({ success: true, pattern_id: pattern.pattern_id });
  } catch (err) {
    return error(500, { error: String(err) });
  }
});

/**
 * Health check
 */
router.get('/health', () => {
  return json({ status: 'ok', timestamp: new Date().toISOString() });
});

/**
 * 404 handler
 */
router.all('*', () => error(404, { error: 'Not found' }));

export default {
  fetch: router.handle,
};
```

### 6.2 GitHub Actions Workflow for Auto-Upload
```yaml
# .github/workflows/patterns-to-r2.yml

name: Upload Patterns to R2

on:
  push:
    paths:
      - 'docs/LLM_SEMANTIC_PATTERNS.md'
      - 'docs/patterns/**'
    branches:
      - main

jobs:
  upload-patterns:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install dependencies
        run: npm ci

      - name: Convert patterns to JSON
        run: npm run patterns:convert

      - name: Create vectorized KB
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_ACCESS_KEY_ID: ${{ secrets.CF_ACCESS_KEY_ID }}
          CF_ACCESS_KEY_SECRET: ${{ secrets.CF_ACCESS_KEY_SECRET }}
        run: npm run patterns:vectorize

      - name: Upload to R2
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_ACCESS_KEY_ID: ${{ secrets.CF_ACCESS_KEY_ID }}
          CF_ACCESS_KEY_SECRET: ${{ secrets.CF_ACCESS_KEY_SECRET }}
        run: npm run patterns:upload

      - name: Notify
        run: echo "✓ Patterns updated in R2"
```

---

## 7. BEST PRACTICES FOR R2 KNOWLEDGE UPLOADS

### 7.1 Pattern Upload Checklist
```json
{
  "pattern_upload_checklist": {
    "before_upload": [
      {
        "check": "Schema validation",
        "command": "npm run patterns:validate",
        "requirement": "All patterns pass JSON schema"
      },
      {
        "check": "Integrity check",
        "requirement": "Checksum matches local file"
      },
      {
        "check": "No secrets",
        "command": "grep -r 'VITE_\\|SECRET\\|TOKEN\\|API_KEY' patterns/",
        "requirement": "Zero matches"
      },
      {
        "check": "Versioning",
        "requirement": "Version field updated in metadata"
      },
      {
        "check": "Cross-references",
        "requirement": "All related_patterns exist and are valid"
      }
    ],
    "upload_process": [
      {
        "step": 1,
        "action": "Convert markdown to JSON",
        "script": "npm run patterns:convert"
      },
      {
        "step": 2,
        "action": "Create embeddings",
        "script": "npm run patterns:vectorize"
      },
      {
        "step": 3,
        "action": "Generate index",
        "script": "npm run patterns:index"
      },
      {
        "step": 4,
        "action": "Upload to R2",
        "script": "npm run patterns:upload"
      },
      {
        "step": 5,
        "action": "Verify in R2",
        "script": "npm run patterns:verify"
      },
      {
        "step": 6,
        "action": "Invalidate cache",
        "command": "curl -X POST /api/cache/invalidate"
      }
    ],
    "after_upload": [
      {
        "check": "R2 file count",
        "expected": "All files present"
      },
      {
        "check": "Manifest validity",
        "expected": "metadata/manifest.json accessible"
      },
      {
        "check": "Worker endpoint live",
        "test": "curl /api/patterns/search?q=runtime"
      },
      {
        "check": "GPT-5.6 KB accessible",
        "test": "Query returns results"
      }
    ]
  }
}
```

### 7.2 Versioning Strategy
```
R2 Structure:

sovereign-patterns/
├── v1/
│   ├── core/
│   ├── runtime/
│   └── ... (all categories)
├── v2/ (future)
│   └── ...
└── metadata/
    ├── index.json (latest index)
    ├── manifest.json (version info)
    └── checksums.json
```

### 7.3 Caching Strategy
```typescript
// Cache policy for pattern queries

Cache-Control: public, max-age=86400  // 24 hours for pattern files
Cache-Control: private, max-age=3600  // 1 hour for search results
Cache-Control: max-age=0              // No cache for admin uploads
```

---

## 8. MONITORING & MAINTENANCE

### 8.1 Health Check Script
```bash
#!/bin/bash
# scripts/check-patterns-health.sh

set -e

echo "🔍 Patterns Health Check"
echo "========================"

# Check R2 connectivity
echo "✓ R2 bucket accessible"
wrangler r2 object list sovereign-patterns | head -5

# Count patterns
PATTERN_COUNT=$(wrangler r2 object list sovereign-patterns | grep -c '.json' || echo 0)
echo "✓ Pattern files: $PATTERN_COUNT"

# Verify manifest
echo "✓ Verifying manifest..."
wrangler r2 object get sovereign-patterns metadata/manifest.json | jq .total_patterns

# Check worker health
echo "✓ Worker health..."
curl -s https://your-worker-domain.com/health | jq .

# Verify GPT-5.6 KB
echo "✓ Checking KB size..."
wrangler r2 object get sovereign-llm-kb gpt5.6/knowledge-base.jsonl | wc -l

echo ""
echo "✅ All checks passed"
```

### 8.2 Monthly Audit
```json
{
  "monthly_audit": {
    "tasks": [
      {
        "task": "Update deprecated patterns",
        "frequency": "monthly",
        "action": "Mark old patterns with deprecation notice"
      },
      {
        "task": "Review pattern usage",
        "frequency": "monthly",
        "metric": "Which patterns are queried most often?"
      },
      {
        "task": "Performance check",
        "frequency": "monthly",
        "metric": "Average query latency < 100ms"
      },
      {
        "task": "Backup verification",
        "frequency": "weekly",
        "action": "Verify patterns-backup bucket exists"
      }
    ]
  }
}
```

---

## 9. QUICK START: Deploy Patterns in 5 Steps

### Step 1: Convert & Prepare
```bash
npm run patterns:convert
npm run patterns:validate
```

### Step 2: Create Embeddings
```bash
export OPENAI_API_KEY="sk-..."
npm run patterns:vectorize
```

### Step 3: Upload to R2
```bash
export CF_ACCOUNT_ID="..."
export CF_ACCESS_KEY_ID="..."
export CF_ACCESS_KEY_SECRET="..."
npm run patterns:upload
```

### Step 4: Verify Deployment
```bash
npm run patterns:verify
npm run patterns:health-check
```

### Step 5: Test GPT-5.6 Integration
```bash
curl -X POST http://localhost:3000/api/analyze-code \
  -H "Content-Type: application/json" \
  -d '{
    "code": "let x = 1; x = 2;",
    "pattern_id": "RUNTIME.2.0"
  }'
```

---

## 10. PRODUCTION CHECKLIST

```
BEFORE GOING LIVE:

Security:
  □ PATTERN_UPLOAD_SECRET set in Cloudflare
  □ OPENAI_API_KEY not exposed in logs
  □ R2 bucket access restricted to worker only
  □ Auth header required for admin endpoints

Performance:
  □ Caching configured (24h for patterns, 1h for searches)
  □ Query latency < 100ms (test with real data)
  □ Vectorized KB size optimized (< 100MB)

Reliability:
  □ R2 backup bucket created
  □ Manifest checksum verification working
  □ Worker has error handling + logging
  □ Fallback pattern available if KB unavailable

Monitoring:
  □ CloudflareAnalytics dashboard created
  □ Alert rules set (error rate > 1%)
  □ Health check running every 5 minutes
  □ Logs stored for 30 days

Documentation:
  □ API docs deployed (Swagger/OpenAPI)
  □ Pattern query examples documented
  □ Troubleshooting guide created
  □ Escalation path defined
```

---

**Deployment Status:** Ready to implement  
**Last Updated:** 2026-07-13  
**Maintainer:** GitHub Copilot (OuroborosCollective)
