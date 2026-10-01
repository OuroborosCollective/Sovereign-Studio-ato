"""Repair the existing proxy's Compose routing; never modify OAuth credentials."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request


PROXY = "sovereign-mcp-auth-proxy-sovereign-mcp-auth-proxy-1"
SERVICE = "sovereign-mcp-auth-proxy"
COMPOSE = Path("/opt/sovereign-chatgpt-tools/mcp-auth-proxy/docker-compose.yml")
PROJECT = "sovereign-mcp-auth-proxy"
ROUTER = "traefik.http.routers.sovereign-mcp."
HOST_RULE = "Host(`arelogic.space`)"
ROUTES = (
    "/mcp", "/.well-known/oauth-protected-resource/mcp",
    "/.well-known/oauth-authorization-server", "/oauth/authorize",
    "/oauth/register", "/oauth/token", "/oauth/fusionauth-callback",
)
RULE = HOST_RULE + " && (" + " || ".join(f"Path(`{path}`)" for path in ROUTES) + ")"
ALLOWED_NETWORKS = {"areloria_arelorian-network", "sovereign-mcp-auth-internal", "traefik-public"}


def run(argv: list[str], timeout: int = 60) -> str:
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError("COMMAND_FAILED:" + hashlib.sha256((result.stdout + result.stderr).encode()).hexdigest())
    return result.stdout


def inspect() -> dict:
    return json.loads(run(["docker", "inspect", PROXY]))[0]


def compose_config(path: Path) -> dict:
    # Resolved environment values remain in memory and are never serialized.
    return json.loads(run(["docker", "compose", "--project-directory", str(COMPOSE.parent),
                          "--project-name", PROJECT, "-f", str(path), "config", "--format", "json"]))


def render(source: str, image_id: str, extra_networks: dict[str, str]) -> str:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("IMMUTABLE_IMAGE_ID_INVALID")
    pattern = re.compile(r"^(\s*-[ \t]*)([\"']?)(" + re.escape(ROUTER + "rule=") + r")([^\n]*?)\2[ \t]*$", re.M)
    matches = list(pattern.finditer(source))
    if len(matches) != 1 or matches[0].group(4) not in (HOST_RULE, RULE):
        raise ValueError("PROXY_ROUTER_BASELINE_MISMATCH")
    match = matches[0]
    line = match.group(1) + match.group(2) + match.group(3) + RULE + match.group(2)
    source = source[:match.start()] + line + source[match.end():]
    priority_pattern = re.compile(r"^(\s*-[ \t]*)([\"']?)" + re.escape(ROUTER + "priority=") + r"([^\n]*?)\2[ \t]*$", re.M)
    priorities = list(priority_pattern.finditer(source))
    if priorities:
        if len(priorities) != 1 or priorities[0].group(3) != "2000":
            raise ValueError("PROXY_PRIORITY_BASELINE_MISMATCH")
    else:
        source = source.replace(line, line + "\n" + match.group(1) + ROUTER + "priority=2000", 1)
    images = list(re.finditer(r"^(    image:[ \t]*)([\"']?)([^\n]*?)\2[ \t]*$", source, re.M))
    if len(images) != 1 or images[0].group(3) not in ("sovereign-mcp-auth-proxy:candidate", image_id):
        raise ValueError("PROXY_IMAGE_BASELINE_MISMATCH")
    image = images[0]
    source = source[:image.start()] + image.group(1) + image_id + source[image.end():]
    if extra_networks:
        blocks = list(re.finditer(r"^    networks:\n(?:      - [A-Za-z0-9_-]+\n)+", source, re.M))
        if len(blocks) != 1 or len(re.findall(r"^networks:\s*$", source, re.M)) != 1:
            raise ValueError("PROXY_NETWORK_LAYOUT_UNSUPPORTED")
        block = blocks[0]
        additions = "".join("      - " + alias + "\n" for alias in extra_networks)
        source = source[:block.end()] + additions + source[block.end():]
        definitions = ""
        for alias, name in extra_networks.items():
            if not re.fullmatch(r"mcp_routing_[a-z0-9_]+", alias) or name not in ALLOWED_NETWORKS:
                raise ValueError("PROXY_NETWORK_SCOPE_INVALID")
            definitions += f"  {alias}:\n    external: true\n    name: {name}\n"
        source = re.sub(r"^networks:\s*\n", "networks:\n" + definitions, source, count=1, flags=re.M)
    return source


def verify_config(before: dict, after: dict, image_id: str, extra_networks: dict[str, str]) -> None:
    if set(before.get("services", {})) != {SERVICE}:
        raise ValueError("PROXY_SERVICE_SCOPE_MISMATCH")
    expected = json.loads(json.dumps(before))
    service = expected["services"][SERVICE]
    service["image"] = image_id
    service["labels"][ROUTER + "rule"] = RULE
    service["labels"][ROUTER + "priority"] = "2000"
    for alias, name in extra_networks.items():
        service["networks"][alias] = None
        expected["networks"][alias] = {"name": name, "external": True}
    if expected != after:
        raise ValueError("PROXY_UNRELATED_COMPOSE_CHANGE")


def public_metadata(path: str) -> dict:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request("https://arelogic.space" + path, headers={"Accept": "application/json"})
    with opener.open(request, timeout=8) as response:
        if response.status != 200 or "application/json" not in response.headers.get("Content-Type", ""):
            raise ValueError("PUBLIC_OAUTH_METADATA_INVALID")
        data = response.read(100001)
        if len(data) > 100000:
            raise ValueError("PUBLIC_OAUTH_METADATA_TOO_LARGE")
        body = json.loads(data)
        return {k: body[k] for k in ("resource", "issuer", "authorization_servers", "authorization_endpoint", "token_endpoint", "registration_endpoint") if k in body}


def verify_runtime(image_id: str, networks: set[str], protected_admin: dict) -> None:
    for _ in range(30):
        current = inspect()
        labels = current["Config"].get("Labels") or {}
        verified = False
        if current["Image"] == image_id and current["State"].get("Running") is True and set(current["NetworkSettings"]["Networks"]) == networks and labels.get(ROUTER + "rule") == RULE and labels.get(ROUTER + "priority") == "2000":
            try:
                metadata = public_metadata("/.well-known/oauth-protected-resource/mcp")
                authorization = public_metadata("/.well-known/oauth-authorization-server")
                verified = metadata.get("resource") == "https://arelogic.space/mcp" and metadata.get("authorization_servers") == ["https://arelogic.space"] and authorization.get("issuer") == "https://arelogic.space" and public_metadata("/.well-known/oauth-protected-resource") == protected_admin
            except Exception:
                verified = False
        if verified:
            break
        time.sleep(2)
    else:
        raise ValueError("PROXY_RUNTIME_OR_PUBLIC_METADATA_UNVERIFIED")
    source = """(async()=>{const r=await fetch('http://sovereign-chatgpt-mcp:8090/mcp',{method:'POST',headers:{'Accept':'application/json, text/event-stream','Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-06-18',capabilities:{},clientInfo:{name:'sovereign-proxy-readback',version:'1'}}}),signal:AbortSignal.timeout(8000)});let t=await r.text();if(t.startsWith('event:')||t.startsWith('data:'))t=t.split('\\n').filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trim()).pop();const b=JSON.parse(t);console.log(JSON.stringify({ok:r.status===200&&b.result?.serverInfo?.name==='Sovereign ChatGPT Operator'&&!!b.result?.capabilities?.tools}))})().catch(()=>{console.log(JSON.stringify({ok:false}));process.exitCode=1})"""
    if json.loads(run(["docker", "exec", PROXY, "node", "-e", source], timeout=15)).get("ok") is not True:
        raise ValueError("PROXY_UPSTREAM_MCP_PROTOCOL_UNVERIFIED")


def main() -> None:
    if not COMPOSE.exists():
        print(json.dumps({"status": "PROXY_NOT_INSTALLED", "mutationPerformed": False}))
        return
    if os.geteuid() != 0 or COMPOSE.is_symlink() or COMPOSE.parent.is_symlink():
        raise ValueError("PROXY_COMPOSE_AUTHORITY_INVALID")
    previous = inspect()
    labels = previous["Config"].get("Labels") or {}
    if labels.get("com.docker.compose.project") != PROJECT or labels.get("com.docker.compose.project.config_files") != str(COMPOSE):
        raise ValueError("PROXY_COMPOSE_OWNER_MISMATCH")
    networks = set(previous["NetworkSettings"]["Networks"])
    if not networks <= ALLOWED_NETWORKS or "sovereign-mcp-auth-internal" not in networks:
        raise ValueError("PROXY_NETWORK_SCOPE_MISMATCH")
    image_id = previous["Image"]
    original = COMPOSE.read_bytes()
    before = compose_config(COMPOSE)
    declared_image = before["services"][SERVICE]["image"]
    if json.loads(run(["docker", "image", "inspect", declared_image]))[0]["Id"] != image_id:
        raise ValueError("PROXY_SOURCE_IMAGE_IS_NOT_RUNNING_IMAGE")
    configured_names = {item["name"] for item in before["networks"].values()}
    extras = {"mcp_routing_" + name.replace("-", "_"): name for name in sorted(networks - configured_names)}
    replacement = render(original.decode(), image_id, extras).encode()
    with tempfile.NamedTemporaryFile(dir=COMPOSE.parent, prefix=".routing-preflight-", suffix=".yml", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(replacement)
    try:
        verify_config(before, compose_config(temporary), image_id, extras)
        if COMPOSE.read_bytes() != original:
            raise ValueError("PROXY_COMPOSE_STALE_HASH")
        protected_admin = public_metadata("/.well-known/oauth-protected-resource")
        stat = COMPOSE.stat()
        backup_dir = COMPOSE.parent / "routing-recovery-backups"
        backup_dir.mkdir(mode=0o700, exist_ok=True)
        if backup_dir.is_symlink() or backup_dir.stat().st_uid != 0:
            raise ValueError("PROXY_BACKUP_OWNER_INVALID")
        backup = backup_dir / (hashlib.sha256(original).hexdigest() + ".yml")
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600) if not backup.exists() else None
        if descriptor is not None:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(original)
        elif backup.is_symlink() or backup.read_bytes() != original:
            raise ValueError("PROXY_BACKUP_HASH_MISMATCH")
        os.chmod(temporary, stat.st_mode & 0o777)
        os.chown(temporary, stat.st_uid, stat.st_gid)
        mutated = replacement != original
        if mutated:
            os.replace(temporary, COMPOSE)
            try:
                run(["docker", "compose", "--project-directory", str(COMPOSE.parent), "--project-name", PROJECT,
                     "-f", str(COMPOSE), "up", "-d", "--no-build", "--pull", "never", SERVICE], timeout=120)
                verify_runtime(image_id, networks, protected_admin)
            except Exception:
                COMPOSE.write_bytes(original)
                if json.loads(run(["docker", "image", "inspect", declared_image]))[0]["Id"] != image_id:
                    raise ValueError("PROXY_ROLLBACK_IMAGE_ID_CHANGED")
                run(["docker", "compose", "--project-directory", str(COMPOSE.parent), "--project-name", PROJECT,
                     "-f", str(COMPOSE), "up", "-d", "--no-build", "--pull", "never", SERVICE], timeout=120)
                for network in sorted(networks - set(inspect()["NetworkSettings"]["Networks"])):
                    run(["docker", "network", "connect", network, PROXY])
                raise
        else:
            verify_runtime(image_id, networks, protected_admin)
        print(json.dumps({"status": "PROXY_ROUTING_VERIFIED" if mutated else "PROXY_ROUTING_ALREADY_CONFIGURED",
                          "mutationPerformed": mutated, "secretValuesReturned": False,
                          "imageId": image_id, "composeSha256": hashlib.sha256(replacement).hexdigest(),
                          "backupSha256": hashlib.sha256(original).hexdigest(), "routePaths": ROUTES}))
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        reason = str(error).split(":", 1)[0]
        print(json.dumps({"status": "PROXY_ROUTING_BLOCKED", "errorClass": type(error).__name__,
                          "reason": reason if re.fullmatch(r"[A-Z_]+", reason) else "UNCLASSIFIED",
                          "failureSha256": hashlib.sha256(str(error).encode()).hexdigest(), "secretValuesReturned": False}))
        raise SystemExit(1)
