/**
 * VPS Connector — Express Route-Handler (Backend-Stub).
 *
 * Diese Datei definiert den API-Vertrag für den VPS Connector.
 * Sie kann in einen Express-Server eingehängt werden sobald
 * `ssh2` installiert ist.
 *
 * SETUP (wenn ein Express-Server vorhanden ist):
 *   pnpm add ssh2 @types/ssh2
 *   import { vpsRouter } from './server/vpsRoutes';
 *   app.use('/api/vps', vpsRouter);
 *
 * ENDPUNKTE:
 *   POST /api/vps/connect    → { sessionId }
 *   POST /api/vps/exec       → { stdout, stderr, exitCode }
 *   GET  /api/vps/tree       → { entries: DirEntry[] }
 *   POST /api/vps/disconnect → { ok }
 *
 * Issue #454
 */

// ── Typen ────────────────────────────────────────────────────────────────────

export interface VpsSession {
  id: string;
  host: string;
  username: string;
  createdAt: number;
  // client: Client; // ssh2 Client — nach pnpm add ssh2 einkommentieren
}

// Sessions in-memory — pro Server-Instanz
// In Produktion: Redis oder DB für Multi-Instance-Betrieb
const sessions = new Map<string, VpsSession>();

// ── Route-Handler (Express-kompatibel) ───────────────────────────────────────

/**
 * POST /api/vps/connect
 * Body: { host, port, username, authMethod, password?, privateKey? }
 * Response: { sessionId }
 */
export async function handleVpsConnect(req: ConnectRequest, res: ExpressResponse) {
  const { host, port = 22, username, authMethod, password, privateKey } = req.body as {
    host: string;
    port?: number;
    username: string;
    authMethod: 'password' | 'key';
    password?: string;
    privateKey?: string;
  };

  if (!host || !username) {
    return res.status(400).json({ error: 'host und username sind Pflichtfelder' });
  }
  if (authMethod === 'password' && !password) {
    return res.status(400).json({ error: 'Passwort fehlt' });
  }
  if (authMethod === 'key' && !privateKey) {
    return res.status(400).json({ error: 'SSH-Key fehlt' });
  }

  // TODO: ssh2-Verbindung aufbauen
  // const { Client } = await import('ssh2');
  // const client = new Client();
  // await new Promise<void>((resolve, reject) => {
  //   client.on('ready', resolve).on('error', reject).connect({
  //     host, port, username,
  //     password: authMethod === 'password' ? password : undefined,
  //     privateKey: authMethod === 'key' ? privateKey : undefined,
  //   });
  // });

  const sessionId = crypto.randomUUID();
  sessions.set(sessionId, {
    id: sessionId,
    host,
    username,
    createdAt: Date.now(),
    // client,
  });

  // Session nach 4h automatisch bereinigen
  setTimeout(() => sessions.delete(sessionId), 4 * 60 * 60 * 1000);

  return res.json({ sessionId });
}

/**
 * POST /api/vps/exec
 * Body: { sessionId, command }
 * Response: { stdout, stderr, exitCode }
 *
 * SICHERHEIT: Erlaubt nur explizit vom User bestätigte Befehle.
 * Kein Auto-Execute — die Frontend-Komponente erzwingt Bestätigung.
 */
export async function handleVpsExec(req: ConnectRequest, res: ExpressResponse) {
  const { sessionId, command } = req.body as { sessionId: string; command: string };
  const session = sessions.get(sessionId);
  if (!session) return res.status(404).json({ error: 'Session nicht gefunden oder abgelaufen' });
  if (!command?.trim()) return res.status(400).json({ error: 'Befehl fehlt' });

  // TODO: ssh2 exec
  // const result = await new Promise<{ stdout: string; stderr: string; exitCode: number }>(
  //   (resolve, reject) => {
  //     session.client.exec(command, (err, stream) => {
  //       if (err) return reject(err);
  //       let stdout = '', stderr = '';
  //       stream.on('data', (d: Buffer) => stdout += d.toString());
  //       stream.stderr.on('data', (d: Buffer) => stderr += d.toString());
  //       stream.on('close', (code: number) => resolve({ stdout, stderr, exitCode: code ?? 0 }));
  //     });
  //   }
  // );

  // Stub-Response (entfernen sobald ssh2 installiert ist)
  return res.json({ stdout: '', stderr: 'Backend noch nicht implementiert — ssh2 installieren', exitCode: 1 });
}

/**
 * GET /api/vps/tree?sessionId=...&path=...
 * Response: { entries: Array<{ name, type, size?, permissions? }> }
 */
export async function handleVpsTree(req: ConnectRequest, res: ExpressResponse) {
  const { sessionId, path = '/' } = req.query as { sessionId: string; path?: string };
  const session = sessions.get(sessionId);
  if (!session) return res.status(404).json({ error: 'Session nicht gefunden' });

  // TODO: ssh2 sftp readdir
  // const sftp = await new Promise<SFTPWrapper>((resolve, reject) => {
  //   session.client.sftp((err, sftp) => err ? reject(err) : resolve(sftp));
  // });
  // const list = await new Promise<FileEntry[]>((resolve, reject) => {
  //   sftp.readdir(path, (err, list) => err ? reject(err) : resolve(list));
  // });

  return res.json({ entries: [] }); // Stub
}

/**
 * POST /api/vps/disconnect
 * Body: { sessionId }
 * Response: { ok }
 */
export async function handleVpsDisconnect(req: ConnectRequest, res: ExpressResponse) {
  const { sessionId } = req.body as { sessionId: string };
  const session = sessions.get(sessionId);
  if (session) {
    // session.client.end(); // nach ssh2-Install
    sessions.delete(sessionId);
  }
  return res.json({ ok: true });
}

// ── Minimal-Typen für Express (vermeidet express-Dependency in dieser Datei) ─

interface ConnectRequest {
  body: unknown;
  query: Record<string, string | undefined>;
}
interface ExpressResponse {
  status(code: number): ExpressResponse;
  json(data: unknown): unknown;
}
