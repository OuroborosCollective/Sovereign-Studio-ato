export interface LLMResponse {
  content: string;
  error?: string;
}

// Nutzt den Groq API für kostenlose LLM-Inferenz (free tier verfügbar)
// Alternativ: mlvoca.com/api/generate (Ollama kompatibel)
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
    // Versuche zuerst Groq API (free tier)
    const groqResponse = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer gsk_test_key_for_demo" // Placeholder - Nutzer muss eigenen Key eintragen
      },
      body: JSON.stringify({
        model: "deepseek-r1-distill-qwen-32b", // Kostenloses Reasoning-Modell
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: prompt }
        ],
        stream: false,
      }),
    });

    if (!groqResponse.ok) {
      throw new Error(`Groq API Fehler: ${groqResponse.status}`);
    }

    const groqData = await groqResponse.json();
    let content = groqData.choices?.[0]?.message?.content || "";
    
    // DeepSeek R1 gibt oft  Blöcke zurück - diese entfernen
    content = content.replace(/[\s\S]*?<\/think>/gi, "");
    // Entferne Markdown-Code-Block wrappers
    content = content.replace(/^```typescript\n?/, "").replace(/\n?```$/, "");
    return content.trim();
  } catch (error: any) {
    // Fallback: Versuche mlvoca.com (Ollama kompatibel)
    try {
      const fallbackResponse = await fetch("https://mlvoca.com/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "deepseek-r1:1.5b",
          prompt: `${systemPrompt}\n\n${prompt}`,
          stream: false,
        }),
      });

      if (fallbackResponse.ok) {
        const fallbackData = await fallbackResponse.json();
        let content = fallbackData.response || "";
        //  Blöcke entfernen
        content = content.replace(/[\s\S]*?<\/think>/gi, "");
        content = content.replace(/^```typescript\n?/, "").replace(/\n?```$/, "");
        return content.trim();
      }
    } catch (fallbackError) {
      // Fallback ebenfalls fehlgeschlagen
    }
    throw new Error(`LLM-Anfrage fehlgeschlagen: ${error.message}`);
  }
}