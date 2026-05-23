/**
 * NOCode Studio V3 - Prompt Factory
 * Specialized for Gemini API integration with architectural awareness.
 */

export type PromptRole = 'user' | 'model' | 'system';

export interface PromptPart {
  text: string;
}

export interface PromptContent {
  role: PromptRole;
  parts: PromptPart[];
}

export interface RepositoryContext {
  files?: Array<{ path: string; content: string }>;
  frameworks: string[];
  platform: 'ios' | 'android' | 'web' | 'cross-platform';
  constraints: string[];
}

export class PromptBuilder {
  private static readonly BASE_SYSTEM_INSTRUCTION = `
    You are the NOCode Studio V3 AI Core.
    Architecture: Mobile-First, Vite, TypeScript, Capacitor 6.
    Capabilities: Cross-platform LLM-driven development, Biometrics, Push-Notifications.
    Strict Rules:
    - Never use global regex replace(//g). Use split/join or specific patterns.
    - Avoid TS1135 errors by ensuring clean syntax and proper character escaping.
    - No empty JSX tags (<></> is allowed if containing nodes, but avoid empty fragments).
    - Optimize for high-performance mobile execution.
    - Follow the CI/CD pipeline logic for automated Android optimization.
  `;

  /**
   * Generates a system prompt with injected architectural constraints.
   */
  public static buildSystemInstruction(customConstraints: string[] = []): PromptContent {
    const combinedConstraints = [
      ...customConstraints,
      "Ensure all code is compatible with Capacitor 6 native bridges.",
      "Prioritize type safety and exhaustive error handling."
    ].join('\n');

    return {
      role: 'system',
      parts: [{
        text: `${this.BASE_SYSTEM_INSTRUCTION}\n\nAdditional Project Constraints:\n${combinedConstraints}`
      }]
    };
  }

  /**
   * Constructs a development-focused prompt injecting repository context.
   */
  public static buildDevelopmentPrompt(
    userQuery: string,
    context: RepositoryContext
  ): PromptContent {
    const contextString = this.formatRepositoryContext(context);
    
    const promptText = `
      Context Awareness:
      ${contextString}

      Task:
      ${userQuery}

      Response Requirements:
      - Return only valid, production-ready code or precise architectural advice.
      - Adhere to NOCode Studio V3 mobile-first design patterns.
    `;

    return {
      role: 'user',
      parts: [{ text: promptText.trim() }]
    };
  }

  /**
   * Injects specific file contents into the prompt flow.
   */
  private static formatRepositoryContext(context: RepositoryContext): string {
    const fileContext = context.files?.map(f => `File: ${f.path}\nContent:\n${f.content}`).join('\n---\n') || '';
    const frameworkContext = `Frameworks: ${context.frameworks.join(', ')}`;
    const platformContext = `Target Platform: ${context.platform}`;
    
    return `
      ${platformContext}
      ${frameworkContext}
      ${context.constraints.length > 0 ? 'Constraints: ' + context.constraints.join(', ') : ''}
      
      Files in Scope:
      ${fileContext}
    `.trim();
  }

  /**
   * Sanitizes strings without using forbidden global regex.
   */
  public static sanitizeInput(input: string): string {
    // Avoids replace(//g) by using split/join pattern for common injections
    return input.split('<script').join('[SECURE_STRIPPED]').split('</script>').join('');
  }
}

export default PromptBuilder;