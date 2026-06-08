type ApprovalRequest = {
  repoUrl: string;
  workflowCode: string;
  manifestJson: string;
  blueprint: string;
};

type GitHubRepo = {
  default_branch: string;
};

type GitHubRef = {
  object: {
    sha: string;
  };
};

type GitHubPull = {
  html_url: string;
  number: number;
};

const GITHUB_API = "https://api.github.com";
const WORKFLOW_PATH = "generated/sovereign-product/workflow.ts";
const MANIFEST_PATH = "generated/sovereign-product/manifest.json";

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json",
      "access-control-allow-origin": Deno.env.get("APPROVAL_SYNC_ALLOWED_ORIGIN") ?? "*",
      "access-control-allow-methods": "POST, OPTIONS",
      "access-control-allow-headers": "content-type, authorization",
    },
  });
}

function parseRepoUrl(repoUrl: string) {
  const match = repoUrl.match(/github\.com\/([^/\s]+)\/([^/\s#?]+)/i);
  if (!match) throw new Error("INVALID_REPO_URL");

  const owner = match[1];
  const repo = match[2].replace(/\.git$/, "");
  const full = `${owner}/${repo}`;

  const allowed = Deno.env.get("GITHUB_ALLOWED_REPO");
  if (allowed && allowed !== full) {
    throw new Error("REPO_NOT_ALLOWED");
  }

  return { owner, repo, full };
}

function base64Utf8(value: string) {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function shortHash(value: string) {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).slice(0, 8);
}

async function github<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${GITHUB_API}${path}`, {
    ...init,
    headers: {
      accept: "application/vnd.github+json",
      "content-type": "application/json",
      "x-github-api-version": "2022-11-28",
      authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
  });

  const text = await response.text();

  if (!response.ok) {
    throw new Error(`GITHUB_${response.status}_${text.slice(0, 400)}`);
  }

  return text ? JSON.parse(text) as T : {} as T;
}

async function getExistingSha(token: string, owner: string, repo: string, path: string, branch: string) {
  const encodedPath = path.split("/").map(encodeURIComponent).join("/");
  const response = await fetch(
    `${GITHUB_API}/repos/${owner}/${repo}/contents/${encodedPath}?ref=${encodeURIComponent(branch)}`,
    {
      headers: {
        accept: "application/vnd.github+json",
        authorization: `Bearer ${token}`,
        "x-github-api-version": "2022-11-28",
      },
    },
  );

  if (response.status === 404) return undefined;

  const text = await response.text();

  if (!response.ok) {
    throw new Error(`GITHUB_CONTENT_${response.status}_${text.slice(0, 400)}`);
  }

  const payload = JSON.parse(text);
  return payload?.sha as string | undefined;
}

async function putFile(
  token: string,
  owner: string,
  repo: string,
  branch: string,
  path: string,
  content: string,
  message: string,
) {
  const sha = await getExistingSha(token, owner, repo, path, branch);
  const encodedPath = path.split("/").map(encodeURIComponent).join("/");

  await github(token, `/repos/${owner}/${repo}/contents/${encodedPath}`, {
    method: "PUT",
    body: JSON.stringify({
      message,
      branch,
      content: base64Utf8(content),
      ...(sha ? { sha } : {}),
    }),
  });
}

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") {
    return json(200, { ok: true });
  }

  if (request.method !== "POST") {
    return json(405, {
      ok: false,
      code: "METHOD_NOT_ALLOWED",
      message: "Only POST is allowed.",
    });
  }

  const token = Deno.env.get("GITHUB_SYNC_TOKEN");

  if (!token) {
    return json(500, {
      ok: false,
      code: "GITHUB_SYNC_TOKEN_MISSING",
      message: "Server secret GITHUB_SYNC_TOKEN is missing.",
    });
  }

  try {
    const input = await request.json() as ApprovalRequest;

    if (!input.repoUrl || !input.workflowCode || !input.manifestJson) {
      return json(400, {
        ok: false,
        code: "BAD_REQUEST",
        message: "repoUrl, workflowCode and manifestJson are required.",
      });
    }

    if (input.workflowCode.length > 250_000 || input.manifestJson.length > 250_000) {
      return json(413, {
        ok: false,
        code: "PAYLOAD_TOO_LARGE",
        message: "Approval payload is too large.",
      });
    }

    const target = parseRepoUrl(input.repoUrl);
    const repoInfo = await github<GitHubRepo>(token, `/repos/${target.owner}/${target.repo}`);
    const baseBranch = repoInfo.default_branch || "main";
    const baseRef = await github<GitHubRef>(
      token,
      `/repos/${target.owner}/${target.repo}/git/ref/heads/${encodeURIComponent(baseBranch)}`,
    );

    const stamp = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
    const branchName = `sovereign-approval/${stamp}-${shortHash(input.manifestJson)}`;

    await github(token, `/repos/${target.owner}/${target.repo}/git/refs`, {
      method: "POST",
      body: JSON.stringify({
        ref: `refs/heads/${branchName}`,
        sha: baseRef.object.sha,
      }),
    });

    await putFile(
      token,
      target.owner,
      target.repo,
      branchName,
      WORKFLOW_PATH,
      input.workflowCode,
      "chore(sovereign): add approved workflow",
    );

    await putFile(
      token,
      target.owner,
      target.repo,
      branchName,
      MANIFEST_PATH,
      input.manifestJson,
      "chore(sovereign): add approval manifest",
    );

    const pull = await github<GitHubPull>(token, `/repos/${target.owner}/${target.repo}/pulls`, {
      method: "POST",
      body: JSON.stringify({
        title: `Sovereign approval ${stamp}`,
        head: branchName,
        base: baseBranch,
        body: [
          "Approved from Sovereign Studio after green validation.",
          "",
          `Blueprint hash: ${shortHash(input.blueprint ?? "")}`,
          `Manifest hash: ${shortHash(input.manifestJson)}`,
        ].join("\n"),
      }),
    });

    return json(200, {
      ok: true,
      branchName,
      pullRequestUrl: pull.html_url,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);

    return json(500, {
      ok: false,
      code: "APPROVAL_SYNC_FAILED",
      message,
    });
  }
});