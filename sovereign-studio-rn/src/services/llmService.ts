export interface LLMResponse {
  content: string;
  error?: string;
}

// Nutzt den Groq API für kostenlose LLM-Inferenz (free tier verfügbar)
// Fallbacks: pawan.krd (keyless), mlvoca.com (Ollama) und Zhipu AI (BigModel)
export async function askRefactorLLM(
  currentCode: string,
  instruction: string,
  systemPrompt: string,
  groqApiKey?: string
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

  // Wenn ein echter API Key vorhanden ist, verwende Groq
  if (groqApiKey && groqApiKey.length > 10) {
    try {
      const groqResponse = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${groqApiKey}`
        },
        body: JSON.stringify({
          model: "deepseek-r1-distill-qwen-32b",
          messages: [
            { role: "system", content: systemPrompt },
            { role: "user", content: prompt }
          ],
          stream: false,
        }),
      });

      if (groqResponse.ok) {
        const groqData = await groqResponse.json();
        let content = groqData.choices?.[0]?.message?.content || "";
        content = content.replace(/[\s\S]*?<\/think>/gi, "");
        content = content.replace(/^```typescript\n?/, "").replace(/\n?```$/, "");
        return content.trim();
      }
    } catch (groqError) {
      // Fallthrough zu den kostenlosen Alternativen
    }
  }

  // Fallback 1: Pawan.krd - Schlüsselloser Free Proxy
  try {
    const pawanResponse = await fetch("https://pawan.krd/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer pk-free-anonymous-drive"
      },
      body: JSON.stringify({
        model: "meta-llama/llama-3-8b-instruct",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: prompt }
        ],
        temperature: 0.3,
        stream: false,
      }),
    });

    if (pawanResponse.ok) {
      const pawanData = await pawanResponse.json();
      let content = pawanData.choices?.[0]?.message?.content || "";
      content = content.replace(/^```typescript\n?/, "").replace(/\n?```$/, "");
      return content.trim();
    }
  } catch (pawanError) {
    // Pawan ebenfalls fehlgeschlagen
  }

  // Fallback 2: mlvoca.com (Ollama kompatibel)
  try {
    const mlvocaResponse = await fetch("https://mlvoca.com/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "deepseek-r1:1.5b",
        prompt: `${systemPrompt}\n\n${prompt}`,
        stream: false,
      }),
    });

    if (mlvocaResponse.ok) {
      const mlvocaData = await mlvocaResponse.json();
      let content = mlvocaData.response || "";
      content = content.replace(/[\s\S]*?<\/think>/gi, "");
      content = content.replace(/^```typescript\n?/, "").replace(/\n?```$/, "");
      return content.trim();
    }
  } catch (mlvocaError) {
    // mlvoca ebenfalls fehlgeschlagen
  }

  // Fallback 3: Zhipu AI (BigModel) — deaktiviert (kein Key konfiguriert)
  // Wenn ein echter Zhipu-Key vorhanden ist, über groqApiKey-Parameter übergeben
  // und als primäre Route nutzen. Kein hardcoded Key erlaubt.

  throw new Error("Kein LLM-Service verfügbar. Bitte einen Groq API Key eintragen.");
}