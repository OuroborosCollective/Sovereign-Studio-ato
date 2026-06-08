import { Octokit } from "@octokit/rest";

interface FileParams {
  patToken: string;
  owner: string;
  repo: string;
  branch: string;
  path: string;
}

interface PushParams extends FileParams {
  code: string;
  commitMessage: string;
}

// 1. Holt den aktuellen Inhalt einer Datei aus GitHub
export async function fetchFileFromGitHub({
  patToken,
  owner,
  repo,
  branch,
  path,
}: FileParams): Promise<{ content: string; sha: string }> {
  const octokit = new Octokit({ auth: patToken });
  const { data } = await octokit.repos.getContent({
    owner,
    repo,
    path,
    ref: branch,
  });

  if (Array.isArray(data) || data.type !== "file") {
    throw new Error("Der angegebene Pfad ist keine gültige Datei.");
  }

  // GitHub gibt Daten in Base64 zurück -> Dekodieren für das Smartphone
  const decodedContent = decodeURIComponent(
    escape(atob(data.content.replace(/\n/g, "")))
  );
  return { content: decodedContent, sha: data.sha };
}

// 2. Pusht den überarbeiteten Code zurück
export async function pushUpdatedCodeToGitHub({
  patToken,
  owner,
  repo,
  branch,
  path,
  code,
  commitMessage,
}: PushParams) {
  const octokit = new Octokit({ auth: patToken });

  // SHA der alten Datei ermitteln, um Konflikte zu vermeiden
  const { sha } = await fetchFileFromGitHub({
    patToken,
    owner,
    repo,
    branch,
    path,
  });
  const base64Content = btoa(unescape(encodeURIComponent(code)));

  const response = await octokit.repos.createOrUpdateFileContents({
    owner,
    repo,
    path,
    branch,
    message: commitMessage,
    content: base64Content,
    sha: sha, // Zwingend erforderlich für Updates
  });

  return { success: true, sha: response.data.content?.sha };
}