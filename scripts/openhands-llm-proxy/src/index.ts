type WorkersAiBinding = {
  run(model: string, input: unknown): Promise<unknown>;
};

type WorkerFetchHandler<BindingEnv> = {
  fetch(request: Request, env: BindingEnv): Promise<Response> | Response;
};

type SafeRouteLog = {
  method: string;
  path: string;
  hasAuth: boolean;
  contentType: string | null;
  bodyKeys?: string[];
  hasMessages?: boolean;
  hasPrompt?: boolean;
  hasInput?: boolean;
  parsedMessageCount?: number;
  inputType?: string;
};

export interface Env {
  AI: WorkersAiBinding;
  DEFAULT_MODEL?: string;
  OPENHANDS_PROXY_KEY?: string;
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization"
    },
  });
}

function createRouteLog(request: Request, pathname: string): SafeRouteLog {
  return {
    method: request.method,
    path: pathname,
    hasAuth: Boolean(request.headers.get("Authorization")),
    contentType: request.headers.get("Content-Type")
  };
}

function logRoute(label: string, routeLog: SafeRouteLog): void {
  console.log(label, JSON.stringify(routeLog));
}

function logSafeError(label: string, error: unknown): void {
  const errorType = error instanceof Error ? error.name : typeof error;
  console.log(label, JSON.stringify({ errorType }));
}

function safeRequestError(status = 400): Response {
  return json({ error: { message: "Request could not be processed" } }, status);
}

function requireProxyKey(request: Request, env: Env): Response | null {
  const expected = env.OPENHANDS_PROXY_KEY?.trim();
  if (!expected) {
    return json({ error: { message: "OpenHands proxy key is not configured" } }, 503);
  }
  const auth = request.headers.get("Authorization") || "";
  const received = auth.replace(/^Bearer\s+/i, "").trim();
  if (!received || received !== expected) {
    return json({ error: { message: "Unauthorized" } }, 401);
  }
  return null;
}

function extractModel(raw: string, def: string): string {
  if (raw.startsWith("openai/")) return raw.substring(7);
  return raw || def;
}

function getModelFromBody(body: Record<string, unknown>, env: Env): string {
  const rawModel = typeof body.model === "string" && body.model.trim()
    ? body.model.trim()
    : env.DEFAULT_MODEL || "@cf/meta/llama-3.1-8b-instruct-fp8";
  return extractModel(rawModel, env.DEFAULT_MODEL || "@cf/meta/llama-3.1-8b-instruct-fp8");
}

function extractMessagesFromBody(body: Record<string, unknown>): Array<{role: string; content: string}> {
  const messages: Array<{role: string; content: string}> = [];

  // Handle messages array (standard chat format)
  if (Array.isArray(body.messages)) {
    for (const m of body.messages as Array<unknown>) {
      if (typeof m === "object" && m !== null) {
        const msg = m as Record<string, unknown>;
        if (typeof msg.content === "string") {
          messages.push({
            role: typeof msg.role === "string" ? msg.role : "user",
            content: msg.content
          });
        }
      }
    }
  }

  // Handle prompt (simple string format)
  if (messages.length === 0 && typeof body.prompt === "string") {
    messages.push({ role: "user", content: body.prompt });
  }

  // Handle input (OpenAI Responses API format)
  if (messages.length === 0 && typeof body.input === "string") {
    messages.push({ role: "user", content: body.input });
  }

  return messages;
}

async function chatComplete(request: Request, env: Env): Promise<Response> {
  const routeLog = createRouteLog(request, new URL(request.url).pathname);

  const auth = requireProxyKey(request, env);
  if (auth) return auth;

  try {
    const body = await request.json() as Record<string, unknown>;
    routeLog.bodyKeys = Object.keys(body);
    routeLog.hasMessages = Array.isArray(body.messages);
    routeLog.hasPrompt = typeof body.prompt === "string";
    routeLog.hasInput = typeof body.input === "string";

    const model = getModelFromBody(body, env);
    const messages = extractMessagesFromBody(body);
    routeLog.parsedMessageCount = messages.length;
    logRoute("OpenHands proxy chat request", routeLog);

    if (messages.length === 0) {
      return json({ error: { message: "no valid messages" } }, 400);
    }

    // Call Workers AI with messages
    const result = await env.AI.run(model, { messages });
    const content = typeof result === "object" && result && "response" in result
      ? String((result as { response?: unknown }).response || "")
      : JSON.stringify(result);

    return json({
      id: `chatcmpl-${crypto.randomUUID()}`,
      object: "chat.completion",
      created: Math.floor(Date.now() / 1000),
      model: body.model || env.DEFAULT_MODEL || "@cf/meta/llama-3.1-8b-instruct-fp8",
      choices: [{
        index: 0,
        message: { role: "assistant", content },
        finish_reason: "stop"
      }]
    });
  } catch (error) {
    logSafeError("OpenHands proxy chat error", error);
    return safeRequestError(400);
  }
}

// OpenAI Responses API support
async function responsesAPI(request: Request, env: Env): Promise<Response> {
  const routeLog = createRouteLog(request, new URL(request.url).pathname);

  const auth = requireProxyKey(request, env);
  if (auth) return auth;

  try {
    const body = await request.json() as Record<string, unknown>;
    routeLog.bodyKeys = Object.keys(body);
    routeLog.hasInput = typeof body.input === "string";

    const model = getModelFromBody(body, env);

    // Extract input text - support multiple formats
    let inputText = "";

    if (typeof body.input === "string" && body.input.trim()) {
      inputText = body.input.trim();
    } else if (Array.isArray(body.input)) {
      // Handle array of content parts (OpenAI Responses API format)
      for (const item of body.input) {
        if (typeof item === "object" && item !== null) {
          const contentItem = item as Record<string, unknown>;
          // input_text format
          if (contentItem.type === "input_text" && typeof contentItem.text === "string") {
            inputText += contentItem.text;
          }
          // simple string in array
          else if (typeof item === "string") {
            inputText += item;
          }
          // message format
          else if (contentItem.role === "user" && typeof contentItem.content === "string") {
            inputText += contentItem.content;
          }
        } else if (typeof item === "string") {
          inputText += item;
        }
      }
    } else if (typeof body.input === "object" && body.input !== null) {
      // Handle object format
      const inputObj = body.input as Record<string, unknown>;
      if (typeof inputObj.text === "string") {
        inputText = inputObj.text;
      } else if (Array.isArray(inputObj.parts)) {
        for (const part of inputObj.parts) {
          if (typeof part === "string") {
            inputText += part;
          } else if (typeof part === "object" && part !== null) {
            const partObj = part as Record<string, unknown>;
            if (partObj.type === "text" && typeof partObj.text === "string") {
              inputText += partObj.text;
            }
          }
        }
      }
    }

    // Fallback: if still empty, use prompt field
    if (!inputText.trim() && typeof body.prompt === "string") {
      inputText = body.prompt;
    }

    routeLog.inputType = typeof body.input;
    logRoute("OpenHands proxy responses request", routeLog);

    // Handle empty/initial requests gracefully - return a minimal ready response
    // This happens when OpenHands initializes the Responses API
    if (!inputText.trim()) {
      logRoute("OpenHands proxy empty responses initialization", routeLog);
      return json({
        id: `resp_${crypto.randomUUID().replace(/-/g, "").substring(0, 12)}`,
        object: "response",
        created_at: Math.floor(Date.now() / 1000),
        status: "in_progress",
        model: body.model || env.DEFAULT_MODEL || "@cf/meta/llama-3.1-8b-instruct-fp8",
        output: [],
        incomplete_details: { reason: "max_output_tokens" }
      });
    }

    // Call Workers AI
    const result = await env.AI.run(model, {
      messages: [{ role: "user", content: inputText }]
    });

    const outputText = typeof result === "object" && result && "response" in result
      ? String((result as { response?: unknown }).response || "")
      : JSON.stringify(result);

    // Return OpenAI Responses API format
    return json({
      id: `resp_${crypto.randomUUID().replace(/-/g, "").substring(0, 12)}`,
      object: "response",
      created_at: Math.floor(Date.now() / 1000),
      status: "completed",
      model: body.model || env.DEFAULT_MODEL || "@cf/meta/llama-3.1-8b-instruct-fp8",
      output: [
        {
          type: "message",
          role: "assistant",
          content: [
            {
              type: "output_text",
              text: outputText
            }
          ]
        }
      ],
      output_text: outputText
    });
  } catch (error) {
    logSafeError("OpenHands proxy responses error", error);
    return safeRequestError(400);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const pathname = url.pathname;

    logRoute("OpenHands proxy route", createRouteLog(request, pathname));

    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return json({ ok: true });
    }

    // Health check
    if (request.method === "GET" && (pathname === "/" || pathname === "/health")) {
      return json({
        ok: true,
        provider: "openhands-workers-ai-bridge",
        model: env.DEFAULT_MODEL || "@cf/meta/llama-3.1-8b-instruct-fp8",
        authConfigured: Boolean(env.OPENHANDS_PROXY_KEY?.trim())
      });
    }

    // Models list
    if (request.method === "GET" && (pathname === "/v1/models" || pathname === "/models")) {
      const auth = requireProxyKey(request, env);
      if (auth) return auth;

      return json({
        object: "list",
        data: [{
          id: "@cf/meta/llama-3.1-8b-instruct-fp8",
          object: "model",
          created: 0,
          owned_by: "cloudflare-workers-ai"
        }]
      });
    }

    // Chat completions
    if (request.method === "POST" && (pathname === "/v1/chat/completions" || pathname === "/chat/completions")) {
      return chatComplete(request, env);
    }

    // Completions (legacy)
    if (request.method === "POST" && (pathname === "/v1/completions" || pathname === "/completions")) {
      return chatComplete(request, env);
    }

    // OpenAI Responses API - CRITICAL for OpenHands
    if (request.method === "POST" && (pathname === "/v1/responses" || pathname === "/responses")) {
      return responsesAPI(request, env);
    }

    return json({ error: { message: "Method not allowed" } }, 405);
  },
} satisfies WorkerFetchHandler<Env>;
