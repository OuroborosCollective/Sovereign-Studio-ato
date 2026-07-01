#!/usr/bin/env python3
"""
Sovereign Git Patch - LLM Tool
==============================
Nutze diesen Code als Tool in ChatGPT, Claude, etc.

VERWENDUNG IM CHAT:
> Hier ist ein Tool das du nutzen kannst um Code-Änderungen als Draft PR zu publishen.
> [Füge diese Datei in den Code Interpreter / Workspace]

DANN KANNST DU SAGEN:
> "Mach async test für onMissionChange in BuilderContainer.test.tsx"

DER TOOL MACHT:
1. Lädt existierende Datei von GitHub
2. Prüft jeden SEARCH-Block (exakt 1 Treffer)
3. Ersetzt alle Blöcke
4. Erstellt Branch + Commit
5. Erstellt Draft PR
"""

import json
import urllib.request
import urllib.error
from typing import Optional

# ============== KONFIGURATION ==============
WORKER_URL = "https://sovereign-studio-worker.projectouroboroscollective.workers.dev/git/patch"

# Repository defaults
DEFAULT_OWNER = "OuroborosCollective"
DEFAULT_REPO = "Sovereign-Studio-ato"

# ============== TOOL FUNKTION ==============

def sovereign_patch(
    path: str,
    search: str,
    replace: str,
    message: str,
    owner: str = DEFAULT_OWNER,
    repo: str = DEFAULT_REPO,
) -> dict:
    """
    Apply SEARCH/REPLACE to GitHub file and create Draft PR.
    
    Args:
        path: File path, z.B. "src/App.tsx"
        search: EXACT code to replace (must appear exactly once)
        replace: New code
        message: Commit message
        owner: GitHub owner (default: OuroborosCollective)
        repo: GitHub repo (default: Sovereign-Studio-ato)
    
    Returns:
        dict mit:
        - ok: True bei Erfolg
        - prUrl: Link zum Draft PR
        - branch: Branch name
        - error: Fehlermeldung falls fehlgeschlagen
    
    BEISPIEL:
        sovereign_patch(
            path="src/App.tsx",
            search="const oldValue = 1;",
            replace="const newValue = 2;",
            message="fix: update value"
        )
    """
    payload = {
        "owner": owner,
        "repo": repo,
        "path": path,
        "message": message,
        "blocks": [
            {"search": search, "replace": replace}
        ]
    }
    
    try:
        req = urllib.request.Request(
            WORKER_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'Sovereign-LLM-Tool/1.0'
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            
            if result.get('ok'):
                return {
                    "ok": True,
                    "branch": result.get('branch'),
                    "commit": result.get('commit'),
                    "pr": result.get('pr'),
                    "prUrl": result.get('prUrl'),
                    "message": f"✅ Draft PR erstellt!\n🔗 {result.get('prUrl')}"
                }
            else:
                return {
                    "ok": False,
                    "error": result.get('details', result.get('error')),
                    "failedBlock": result.get('failedBlock'),
                    "message": f"❌ Patch fehlgeschlagen: {result.get('details')}"
                }
                
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        try:
            error_data = json.loads(error_body)
            error_msg = error_data.get('details', error_data.get('error', str(e)))
        except:
            error_msg = str(e)
        
        return {
            "ok": False,
            "error": error_msg,
            "message": f"❌ HTTP Error {e.code}: {error_msg}"
        }
        
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "message": f"❌ Error: {str(e)}"
        }


def sovereign_patch_multi(
    path: str,
    blocks: list,
    message: str,
    owner: str = DEFAULT_OWNER,
    repo: str = DEFAULT_REPO,
) -> dict:
    """
    Apply MULTIPLE SEARCH/REPLACE blocks to one file.
    
    Args:
        path: File path
        blocks: List of {"search": "...", "replace": "..."} dicts
        message: Commit message
        owner: GitHub owner
        repo: GitHub repo
    
    Returns:
        dict (same as sovereign_patch)
    
    BEISPIEL:
        sovereign_patch_multi(
            path="src/test.tsx",
            blocks=[
                {"search": "it('test 1'", "replace": "it('test 1', async () => {"},
                {"search": "it('test 2'", "replace": "it('test 2', async () => {"},
            ],
            message="test: make tests async"
        )
    """
    payload = {
        "owner": owner,
        "repo": repo,
        "path": path,
        "message": message,
        "blocks": blocks
    }
    
    try:
        req = urllib.request.Request(
            WORKER_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'Sovereign-LLM-Tool/1.0'
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            
            if result.get('ok'):
                return {
                    "ok": True,
                    "branch": result.get('branch'),
                    "commit": result.get('commit'),
                    "pr": result.get('pr'),
                    "prUrl": result.get('prUrl'),
                    "message": f"✅ Draft PR erstellt!\n🔗 {result.get('prUrl')}"
                }
            else:
                return {
                    "ok": False,
                    "error": result.get('details', result.get('error')),
                    "failedBlock": result.get('failedBlock'),
                    "message": f"❌ Patch fehlgeschlagen: {result.get('details')}"
                }
                
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "message": f"❌ Error: {str(e)}"
        }


# ============== HILFS FUNKTIONEN ==============

def check_worker() -> dict:
    """Prüfe ob der Worker erreichbar ist."""
    try:
        req = urllib.request.Request(
            WORKER_URL.replace('/git/patch', '/health'),
            method='GET'
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return {"ok": True, "status": json.loads(response.read().decode('utf-8'))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============== CLI TEST ==============

if __name__ == "__main__":
    print("🔧 Sovereign Git Patch - LLM Tool")
    print("=" * 40)
    
    # Check worker
    print("\n📡 Prüfe Worker...")
    health = check_worker()
    if health['ok']:
        print(f"✅ Worker OK: {health['status']}")
    else:
        print(f"❌ Worker nicht erreichbar: {health['error']}")
    
    print("\n📝 VERWENDUNG:")
    print("""
In ChatGPT/Claude mit Code Interpreter:

1. Lade diese Datei hoch oder kopiere den Code
2. Importiere die Funktionen:
   from sovereign_git_patch import sovereign_patch, sovereign_patch_multi

3. Nutze im Chat:
   sovereign_patch(
       path="src/App.tsx",
       search="alter code",
       replace="neuer code",
       message="fix: beschreibung"
   )

4. Mehrere Blöcke:
   sovereign_patch_multi(
       path="src/test.tsx",
       blocks=[
           {"search": "block1", "replace": "neu1"},
           {"search": "block2", "replace": "neu2"},
       ],
       message="fix: mehrere änderungen"
   )
    """)
