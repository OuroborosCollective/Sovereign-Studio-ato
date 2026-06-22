import { callMlvoCa, callGroq, callHuggingFace, callTogether, callOpenRouter, callPollinations, type ProviderType } from './providerManager';
import { geminiService } from './geminiService';

export interface RefactorContext {
  projectName: string;
  repoUrl?: string;
  files: RefactorFile[];
  technologies: string[];
  goals: string[];
}

export interface RefactorFile {
  path: string;
  content?: string;
  sha?: string;
  type: 'blob' | 'tree';
  size?: number;
  language?: string;
}

export interface RefactorMemoryContext {
  source: 'remote-memory' | 'pattern-memory' | 'runtime';
  summary: string;
  patterns: string[];
}

export interface RefactorPlan {
  id: string;
  timestamp: string;
  context: RefactorContext;
  analysis: string;
  tasks: RefactorTask[];
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  provider: ProviderType;
}

export interface RefactorTask {
  id: string;
  type: 'analyze' | 'refactor' | 'generate' | 'explain' | 'fix';
  title: string;
  description: string;
  files?: string[];
  originalCode?: string;
  generatedCode?: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  error?: string;
}

export interface RefactorOptions {
  model?: string;
  temperature?: number;
  maxOutputTokens?: number;
  strictMode?: boolean;
  memoryContext?: RefactorMemoryContext;
}

function safeText(value: string, maxLength = 8000): string {
  return value.trim().slice(0, maxLength);
}

function formatMemoryContext(memory: RefactorMemoryContext | null): string {
  if (!memory) return '';
  const summary = safeText(memory.summary, 1200);
  const patterns = memory.patterns.map((pattern) => `- ${safeText(pattern, 400)}`).join('\n');
  return [
    'REMOTE MEMORY CONTEXT:',
    `Source: ${memory.source}`,
    summary ? `Summary: ${summary}` : '',
    patterns ? `Patterns:\n${patterns}` : '',
    'Use this memory only as supporting context. Runtime checks and guards remain authoritative.',
  ].filter(Boolean).join('\n');
}

export class RefactorEngine {
  private geminiKey: string;
  private groqKey: string;
  private hfKey: string;
  private togetherKey: string;
  private openrouterKey: string;
  private pollinationsKey: string;
  private currentProvider: ProviderType = 'mlvoca';
  private context: RefactorContext | null = null;
  private history: RefactorPlan[] = [];
  private memoryContext: RefactorMemoryContext | null = null;

  constructor() {
    this.geminiKey = '';
    this.groqKey = '';
    this.hfKey = '';
    this.togetherKey = '';
    this.openrouterKey = '';
    this.pollinationsKey = '';
  }

  setKeys(keys: {
    gemini?: string;
    groq?: string;
    huggingface?: string;
    together?: string;
    openrouter?: string;
    pollinations?: string;
  }) {
    if (keys.gemini) this.geminiKey = keys.gemini;
    if (keys.groq) this.groqKey = keys.groq;
    if (keys.huggingface) this.hfKey = keys.huggingface;
    if (keys.together) this.togetherKey = keys.together;
    if (keys.openrouter) this.openrouterKey = keys.openrouter;
    if (keys.pollinations) this.pollinationsKey = keys.pollinations;
  }

  setContext(context: RefactorContext) {
    this.context = context;
  }

  setMemoryContext(memory: RefactorMemoryContext | null) {
    this.memoryContext = memory;
  }

  getMemoryContext(): RefactorMemoryContext | null {
    return this.memoryContext;
  }

  getCurrentProvider(): ProviderType {
    return this.currentProvider;
  }

  getHistory(): RefactorPlan[] {
    return this.history;
  }

  private withMemory(prompt: string, options: RefactorOptions): string {
    const memory = formatMemoryContext(options.memoryContext ?? this.memoryContext);
    if (!memory) return prompt;
    return `${memory}\n\nUSER TASK:\n${prompt}`;
  }

  async generate(prompt: string, options: RefactorOptions = {}): Promise<string> {
    const providers = this.getProviderChain(options.model || 'gemini-1.5-flash');
    const enrichedPrompt = this.withMemory(prompt, options);

    for (const provider of providers) {
      try {
        const result = await this.callProvider(provider, enrichedPrompt, options);
        this.currentProvider = provider.type;
        return result;
      } catch (error: any) {
        console.warn(`Provider ${provider.type} failed:`, error?.message);
        continue;
      }
    }

    throw new Error('All AI providers failed. Please add an API key or try later.');
  }

  private getProviderChain(model: string): Array<{ type: ProviderType; apiKey: string; model: string }> {
    const chain: Array<{ type: ProviderType; apiKey: string; model: string }> = [];

    chain.push({ type: 'mlvoca', apiKey: '', model: this.mapModel(model, 'mlvoca') });
    chain.push({ type: 'pollinations', apiKey: this.pollinationsKey || '', model: this.mapModel(model, 'pollinations') });

    if (this.geminiKey?.trim()) chain.push({ type: 'gemini', apiKey: this.geminiKey, model });
    if (this.groqKey?.trim()) chain.push({ type: 'groq', apiKey: this.groqKey, model: this.mapModel(model, 'groq') });
    if (this.hfKey?.trim()) chain.push({ type: 'huggingface', apiKey: this.hfKey, model: this.mapModel(model, 'huggingface') });
    if (this.togetherKey?.trim()) chain.push({ type: 'together', apiKey: this.togetherKey, model: this.mapModel(model, 'together') });
    if (this.openrouterKey?.trim()) chain.push({ type: 'openrouter', apiKey: this.openrouterKey, model: this.mapModel(model, 'openrouter') });

    return chain;
  }

  private mapModel(model: string, provider: ProviderType): string {
    const maps: Partial<Record<string, Partial<Record<ProviderType, string>>>> = {
      'gemini-1.5-flash': {
        groq: 'llama-3.1-8b-instant',
        huggingface: 'meta-llama/Llama-3.2-1B-Instruct',
        together: 'meta-llama/Llama-3.2-1B-Instruct-Turbo',
        openrouter: 'meta-llama/llama-3.1-8b-instruct:free',
        mlvoca: 'deepseek-r1:1.5b',
        pollinations: 'openai',
        gemini: model,
      },
      'gemini-1.5-pro': {
        groq: 'llama-3.1-70b-versatile',
        huggingface: 'meta-llama/Llama-3.2-3B-Instruct',
        together: 'meta-llama/Llama-3.2-70B-Instruct-Turbo',
        openrouter: 'meta-llama/llama-3.1-70b-instruct:free',
        mlvoca: 'deepseek-r1:1.5b',
        pollinations: 'openai-large',
        gemini: model,
      },
    };

    return maps[model]?.[provider] || (provider === 'pollinations' ? 'openai' : model);
  }

  private async callProvider(provider: { type: ProviderType; apiKey: string; model: string }, prompt: string, options: RefactorOptions): Promise<string> {
    const opts = {
      temperature: options.temperature ?? 0.7,
      maxOutputTokens: options.maxOutputTokens ?? 4096,
    };

    switch (provider.type) {
      case 'mlvoca': {
        const mlvoca = await callMlvoCa(provider.model, prompt, opts);
        return mlvoca.text;
      }
      case 'pollinations': {
        const pollinations = await callPollinations(provider.model, prompt, opts, provider.apiKey);
        return pollinations.text;
      }
      case 'gemini':
        return await geminiService.generateText(provider.apiKey, prompt, {
          model: provider.model,
          temperature: opts.temperature,
          maxOutputTokens: opts.maxOutputTokens,
        });
      case 'groq': {
        const groq = await callGroq(provider.apiKey, provider.model, prompt, opts);
        return groq.text;
      }
      case 'huggingface': {
        const hf = await callHuggingFace(provider.apiKey, provider.model, prompt, opts);
        return hf.text;
      }
      case 'together': {
        const together = await callTogether(provider.apiKey, provider.model, prompt, opts);
        return together.text;
      }
      case 'openrouter': {
        const openrouter = await callOpenRouter(provider.apiKey, provider.model, prompt, opts);
        return openrouter.text;
      }
      default:
        throw new Error(`Unknown provider: ${provider.type}`);
    }
  }

  async analyzeRepo(repoUrl: string, files: RefactorFile[]): Promise<RefactorPlan> {
    const fileList = files.filter(f => f.type === 'blob').map(f => f.path).join('\n');
    const prompt = `Analysiere dieses Repository und erstelle einen Refactor-Plan.

REPOSITORY: ${repoUrl}
DATEIEN:
${fileList}

Gib einen strukturierten Plan zurück mit:
1. ZUSAMMENFASSUNG: Was macht dieses Projekt?
2. TECHNOLOGIEN: Erkannter Stack
3. REFACTOR_TASKS: 3-5 konkrete Verbesserungen mit Priorität

Format: Markdown mit ### Überschriften`;

    const analysis = await this.generate(prompt, { temperature: 0.3 });

    const plan: RefactorPlan = {
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      context: {
        projectName: repoUrl.split('/').pop() || 'Project',
        repoUrl,
        files,
        technologies: this.extractTechList(analysis),
        goals: this.extractGoals(analysis),
      },
      analysis,
      tasks: this.extractTasks(analysis),
      status: 'completed',
      provider: this.currentProvider,
    };

    this.history.unshift(plan);
    return plan;
  }

  async generateCode(task: RefactorTask): Promise<string> {
    const context = this.context ? `KONTEXT:\n${this.context.projectName}\n\n` : '';
    const codeContext = task.originalCode ? `CODE:\n\`\`\`\n${task.originalCode}\n\`\`\`\n\n` : '';
    const prompt = `${context}${codeContext}AUFGABE: ${task.description}
${task.files ? `DATEIEN: ${task.files.join(', ')}` : ''}

Generiere den verbesserten Code. Antworte NUR mit dem Code, keine Erklärung.`;

    return await this.generate(prompt, { temperature: 0.4, maxOutputTokens: 8192 });
  }

  async applyFileChange(
    owner: string,
    repo: string,
    path: string,
    content: string,
    sha: string | undefined,
    branch: string,
    token: string
  ): Promise<any> {
    if (!token) throw new Error('GitHub PAT is required to apply changes.');

    const url = `https://api.github.com/repos/${owner}/${repo}/contents/${path}`;
    const body = {
      message: `AI Refactor: ${path}`,
      content: btoa(unescape(encodeURIComponent(content))),
      sha,
      branch,
    };

    const response = await fetch(url, {
      method: 'PUT',
      headers: {
        'Accept': 'application/vnd.github+json',
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || `GitHub API error: ${response.status}`);
    }

    return await response.json();
  }

  async explainCode(code: string): Promise<string> {
    const prompt = `Erkläre folgenden Code auf Deutsch:

\`\`\`
${code}
\`\`\`

Gib eine klare Erklärung in 3-5 Sätzen.`;

    return await this.generate(prompt, { temperature: 0.3 });
  }

  async generateFeature(description: string, files: string[]): Promise<string> {
    const context = this.context
      ? `PROJEKT: ${this.context.projectName}\nTECHNOLOGIEN: ${this.context.technologies.join(', ')}\n\n`
      : '';
    const prompt = `${context}BESCHREIBUNG:\n${description}

DATEIEN:\n${files.join('\n')}

GENERIERE kompletten, produktionsreifen Code. Antworte mit Dateipfaden und Code.`;

    return await this.generate(prompt, { temperature: 0.5, maxOutputTokens: 16384 });
  }

  private extractTechList(analysis: string): string[] {
    const match = analysis.match(/TECHNOLOGIEN?[:\s]*([^\n]+(?:\n[^\n]+)*)/i);
    if (!match) return [];
    return match[1].split(/[,\n]/).map(s => s.trim()).filter(Boolean);
  }

  private extractGoals(analysis: string): string[] {
    const match = analysis.match(/REFACTOR_TASKS?[:\s]*([\s\S]*?)(?=#|$)/i);
    if (!match) return [];
    return match[1].split(/[-•*]/).filter(s => s.trim()).map(s => s.trim()).filter(Boolean);
  }

  private extractTasks(analysis: string): RefactorTask[] {
    const tasks: RefactorTask[] = [];
    const goals = this.extractGoals(analysis);

    goals.forEach((goal) => {
      tasks.push({
        id: crypto.randomUUID(),
        type: 'refactor',
        title: goal.substring(0, 50),
        description: goal,
        status: 'pending',
      });
    });

    return tasks;
  }
}

export const refactorEngine = new RefactorEngine();
