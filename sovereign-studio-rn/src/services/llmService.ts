export interface LLMResponse {
  content: string;
  error?: string;
}

// Nutzt den öffentlichen MLvoca-Inferenz-Proxy, um ohne API-Keys direkt aus der APK heraus Prompts abzufeuern.
export async function askRefactorLLM(
  currentCode: string,
  instruction: string,
  systemPrompt: string
): Promise<string> {
  const prompt = `
Bestehender Code:
\`\`\`typescript
${currentCode}
\`\`\`


Arbeitsanweisung für die Überarbeitung:
${instruction}


WICHTIG: Gib NUR den modifizierten Code zurück. Keine Erklärungen, kein Markdown, kein \`\`\`typescript.
`;

  try {
    const response = await fetch("https://mlvoca.github.io/free-llm-api/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "deepseek-r1",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: prompt },
        ],
        stream: false,
      }),
    });

    const data = await response.json();
    // Extrahiere die Content-Antwort und entferne Markdown-Code-Blöcke
    let content = data.choices?.[0]?.message?.content || data.response || "";
    // Entferne Markdown-Code-Block wrappers falls vorhanden
    content = content.replace(/^```typescript\n?/, "").replace(/\n?```$/, "");
    return content.trim();
  } catch (error: any) {
    throw new Error(`LLM-Anfrage fehlgeschlagen: ${error.message}`);
  }
}