"""Host-only adapter for the fixed Aurion env repair. No caller-selected I/O.

Contracts reviewed at Echoes_of_Aurion 7a4d28a1ab207ed4875e8a33fdd1531335fba826.
Never execute its promoter or database verifier (the latter writes a volume).
"""
from __future__ import annotations
import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import time
import urllib.error
import urllib.request

from aurion_native_auth import (TARGET, ENV_FILE, RUNTIME_FILE, RELEASE, SEAL, SHA,
    RepairBlocked, atomic_replace, canonical_hash, configuration, fingerprint,
    parse_env, read_protected, repaired_env)

CONTAINER = "echoes-of-aurion-aurion-1"
COMPOSE_SHA256 = "35efb0b8fb3d419a38576f8b570d8e372ac1a77931da1e1365f0a005fa631eb6"
SCHEMA_SOURCE_SHA256 = "4d61fd09f3215c55845e46c6eef31cb2e262139c58df796df0f4bbf2ef365c50"
PUBLIC_RECEIPT = "/var/lib/aurion-traefik-runtime-readback/current.json"
RELEASES = "/opt/aurion-traefik-runtime/releases/"
RECEIPTS = "/var/lib/aurion-traefik-runtime/receipts/"
VOLUMES = {"/var/lib/aurion/glb": "echoes-of-aurion-glb-assets",
           "/var/lib/aurion/game-dev-workspace": "echoes-of-aurion-game-dev-workspace",
           "/var/lib/aurion/companion-memory": "echoes-of-aurion-companion-memory"}
DIGEST_FIELDS = {"AURION_BUILD_INPUT_DIGEST": "buildInputDigest",
                 "AURION_ARTIFACT_DIGEST": "artifactDigest",
                 "AURION_RUNTIME_IMAGE_DIGEST": "runtimeImageDigest",
                 "AURION_RELEASE_ARCHIVE_DIGEST": "releaseArchiveDigest"}
SCHEMA = json.loads('{"aurionNativeAuthAccessTokens": {"columns": {"expiresAtMs": ["bigint", false], "issuedAtMs": ["bigint", false], "sessionId": ["varchar(64)", false], "tokenDigest": ["varchar(64)", false]}, "indexes": {"PRIMARY": [0, ["tokenDigest"]], "aurionNativeAuthAccessTokens_session_idx": [1, ["sessionId"]]}}, "aurionNativeAuthRefreshTokens": {"columns": {"consumedAtMs": ["bigint", true], "expiresAtMs": ["bigint", false], "issuedAtMs": ["bigint", false], "sessionId": ["varchar(64)", false], "tokenDigest": ["varchar(64)", false]}, "indexes": {"PRIMARY": [0, ["tokenDigest"]], "aurionNativeAuthRefreshTokens_session_idx": [1, ["sessionId"]]}}, "aurionNativeAuthSessions": {"columns": {"absoluteExpiresAtMs": ["bigint", false], "appBuild": ["varchar(120)", false], "createdAtMs": ["bigint", false], "currentRefreshDigest": ["varchar(64)", false], "id": ["varchar(64)", false], "idleExpiresAtMs": ["bigint", false], "revokedAtMs": ["bigint", true], "userId": ["int", false]}, "indexes": {"PRIMARY": [0, ["id"]], "aurionNativeAuthSessions_user_idx": [1, ["userId"]]}}, "aurionNativeAuthTransactions": {"columns": {"appBuild": ["varchar(120)", false], "codeChallenge": ["varchar(43)", false], "consumedAtMs": ["bigint", true], "createdAtMs": ["bigint", false], "expiresAtMs": ["bigint", false], "handoffCodeDigest": ["varchar(64)", true], "handoffExpiresAtMs": ["bigint", true], "id": ["varchar(64)", false], "issuedAtMs": ["bigint", true], "requestStateDigest": ["varchar(64)", false], "requestStateSealed": ["varchar(256)", false], "returnId": ["varchar(64)", false], "verifiedUserId": ["int", true]}, "indexes": {"PRIMARY": [0, ["id"]], "aurionNativeAuthTransactions_expiry_idx": [1, ["expiresAtMs"]], "aurionNativeAuthTransactions_handoff_uq": [0, ["handoffCodeDigest"]]}}}')

DB_SCRIPT = r'''
const mysql = await import("mysql2/promise");
const url = new URL(process.env.DATABASE_URL || "");
if (url.protocol !== "mysql:" || url.hostname !== "mariadb" || Number(url.port || 3306) !== 3306 ||
    !url.username || !url.password || url.pathname.length <= 1) throw Error();
const connection = await mysql.createConnection(process.env.DATABASE_URL);
try {
  await connection.query("START TRANSACTION READ ONLY");
  const [one] = await connection.query({sql:"SELECT 1 AS ready", timeout:5000});
  const [columns] = await connection.query({sql:
    "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ('aurionNativeAuthTransactions','aurionNativeAuthSessions','aurionNativeAuthRefreshTokens','aurionNativeAuthAccessTokens')", timeout:5000});
  const [indexes] = await connection.query({sql:
    "SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME, SUB_PART, INDEX_TYPE FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ('aurionNativeAuthTransactions','aurionNativeAuthSessions','aurionNativeAuthRefreshTokens','aurionNativeAuthAccessTokens')", timeout:5000});
  process.stdout.write(JSON.stringify({ready:one.length === 1 && one[0].ready === 1, columns, indexes}));
} finally { await connection.rollback(); await connection.end(); }
'''.strip()


def schema_matches(value):
    if value.get("ready") is not True:
        return False
    actual = {name: {"columns": {}, "indexes": {}} for name in SCHEMA}
    try:
        for row in value["columns"]:
            name, column = row["TABLE_NAME"], row["COLUMN_NAME"]
            if column in actual[name]["columns"] or row["EXTRA"] or row["COLUMN_DEFAULT"] not in (None, "NULL"):
                return False
            typ = re.sub(r"^(bigint|int)\(\d+\)$", r"\1", row["COLUMN_TYPE"].lower())
            if row["IS_NULLABLE"] not in ("YES", "NO"):
                return False
            actual[name]["columns"][column] = [typ, row["IS_NULLABLE"] == "YES"]
        grouped = {}
        for row in value["indexes"]:
            if row["SUB_PART"] is not None or row["INDEX_TYPE"] != "BTREE":
                return False
            key = (row["TABLE_NAME"], row["INDEX_NAME"])
            grouped.setdefault(key, []).append(row)
        for (table, name), rows in grouped.items():
            rows.sort(key=lambda row: row["SEQ_IN_INDEX"])
            unique = rows[0]["NON_UNIQUE"]
            if [r["SEQ_IN_INDEX"] for r in rows] != list(range(1, len(rows) + 1)) or any(r["NON_UNIQUE"] != unique for r in rows):
                return False
            actual[table]["indexes"][name] = [unique, [r["COLUMN_NAME"] for r in rows]]
        return actual == SCHEMA
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


class HostFiles:
    @contextmanager
    def directory(self, path):
        parts = Path(path).parts
        if not parts or parts[0] != "/" or ".." in parts:
            raise RepairBlocked("HOST_PATH_INVALID")
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for name in parts[1:]:
                next_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = next_fd
                info = os.fstat(fd)
                if info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022:
                    raise RepairBlocked("HOST_DIRECTORY_UNPROTECTED")
            yield fd
        finally:
            os.close(fd)

    def read(self, path, *, secret=False):
        path = Path(path)
        with self.directory(str(path.parent)) as fd:
            return read_protected(fd, path.name, modes=(0o600,) if secret else (0o600, 0o640, 0o644))

    def link(self, path, expected):
        path = Path(path)
        with self.directory(str(path.parent)) as fd:
            info = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_gid != 0:
                raise RepairBlocked("DEPLOYMENT_LINK_INVALID")
            if os.readlink(path.name, dir_fd=fd) != expected:
                raise RepairBlocked("DEPLOYMENT_LINK_DRIFT")

    def replace_env(self, before, raw):
        with self.directory(str(Path(ENV_FILE).parent)) as fd:
            return atomic_replace(fd, Path(ENV_FILE).name, before, raw)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class PublicHTTP:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path, body=None):
        # Only fixed private call sites select health or start; never a tool URL.
        if path not in ("/healthz", "/api/native-auth/start"):
            raise RepairBlocked("HTTP_PATH_INVALID")
        request = urllib.request.Request("https://arelogic.space" + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Cache-Control": "no-store"})
        try:
            response = self.opener.open(request, timeout=8)
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            return status, None
        with response:
            if body is not None:
                # Never read/return a start response body, transaction ID or cookies.
                return response.status, None
            raw = response.read(65537)
            if len(raw) > 65536:
                raise RepairBlocked("HEALTH_BODY_SIZE")
            return response.status, json.loads(raw)


class AurionNativeAuthHost:
    def __init__(self, state, *, runner=subprocess.run, files=None, http=None, sleep=time.sleep):
        self.state, self.runner = state, runner
        self.files, self.http, self.sleep = files or HostFiles(), http or PublicHTTP(), sleep

    def run(self, argv, *, env=None, timeout=30):
        result = self.runner(argv, capture_output=True, text=True, check=False, timeout=timeout,
                             env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                                  "LANG": "C", "LC_ALL": "C", **(env or {})})
        if result.returncode != 0 or len(result.stdout.encode()) > 2_000_000:
            raise RepairBlocked("HOST_COMMAND_FAILED")
        return result.stdout

    def inspect(self):
        rows = json.loads(self.run(["docker", "inspect", CONTAINER]))
        if not isinstance(rows, list) or len(rows) != 1:
            raise RepairBlocked("CONTAINER_CARDINALITY")
        row = rows[0]
        labels = row["Config"]["Labels"]
        if (row.get("Name") != "/" + CONTAINER or labels.get("com.docker.compose.project") != "echoes-of-aurion"
                or labels.get("com.docker.compose.service") != "aurion"
                or not SHA.fullmatch(row["Id"]) or not re.fullmatch(r"sha256:[0-9a-f]{64}", row["Image"])):
            raise RepairBlocked("CONTAINER_IDENTITY")
        return row

    @staticmethod
    def environment(row):
        values = {}
        for entry in row["Config"]["Env"]:
            key, value = entry.split("=", 1)
            if key in values:
                raise RepairBlocked("CONTAINER_ENV_DUPLICATE")
            values[key] = value
        return values

    @staticmethod
    def container_metadata(row):
        return canonical_hash({key: row.get(key) for key in ("Config", "HostConfig", "Mounts")})

    def verify_resources(self, row):
        mounts = row.get("Mounts", [])
        if len(mounts) != len(VOLUMES) or any(
                mount.get("Type") != "volume" or mount.get("RW") is not True
                or VOLUMES.get(mount.get("Destination")) != mount.get("Name") for mount in mounts):
            raise RepairBlocked("VOLUME_CONFIGURATION_DRIFT")
        if set(row.get("NetworkSettings", {}).get("Networks", {})) != {"areloria_arelorian-network", "echoes-of-aurion-internal"}:
            raise RepairBlocked("NETWORK_CONFIGURATION_DRIFT")
        conf = row.get("HostConfig", {})
        for key, expected in {"Privileged": False, "ReadonlyRootfs": False, "Memory": 0,
                              "NanoCpus": 0, "PidMode": "", "UsernsMode": ""}.items():
            if conf.get(key) != expected:
                raise RepairBlocked("HOST_CONFIGURATION_DRIFT")
        if any(conf.get(k) for k in ("CapAdd", "CapDrop", "Devices", "SecurityOpt", "PortBindings")):
            raise RepairBlocked("HOST_CONFIGURATION_DRIFT")
        if conf.get("RestartPolicy", {}).get("Name") != "unless-stopped":
            raise RepairBlocked("HOST_CONFIGURATION_DRIFT")
        # Existing named volumes only. Missing volumes block before Compose can
        # implicitly create them; never call volume create/prune/rm.
        volumes = json.loads(self.run(["docker", "volume", "inspect", *sorted(VOLUMES.values())]))
        if len(volumes) != 3 or {v.get("Name") for v in volumes} != set(VOLUMES.values()):
            raise RepairBlocked("VOLUMES_UNAVAILABLE")

    @staticmethod
    def health_matches(body, receipt):
        return (isinstance(body, dict) and body.get("status") == "ok"
                and body.get("service") == "echoes-of-aurion" and body.get("revision") == receipt["revision"]
                and all(body.get(field) == receipt[field] for field in DIGEST_FIELDS.values())
                and isinstance(body.get("authority"), dict)
                and all(body["authority"].get(k) == v for k, v in {"ruleset": "aurion-zone-v3", "tickHz": 10, "causalReceipts": True}.items()))

    def compose(self, context, *args, override=None):
        argv = ["docker", "compose", "--project-name", "echoes-of-aurion", "--env-file", RUNTIME_FILE,
                "-f", context["composePath"]]
        if override is not None:
            argv += ["-f", override]
        return self.run(argv + list(args), env=context["composeEnv"], timeout=90)

    @staticmethod
    def config_without_auth(config):
        config = json.loads(json.dumps(config))
        service = config["services"]["aurion"]
        service.pop("image", None)  # independently checked as immutable image below
        env = service.get("environment", {})
        env.pop(RELEASE, None)
        env.pop(SEAL, None)
        return config

    def resolve(self, expected_revision):
        row = self.inspect()
        self.verify_resources(row)
        receipt_file = self.files.read(PUBLIC_RECEIPT)
        receipt = json.loads(receipt_file.raw)
        release_id = receipt.get("releaseId", "")
        if (receipt.get("recordType") != "aurion_traefik_runtime_readback"
                or not re.fullmatch(re.escape(expected_revision) + r"-[0-9]+", release_id)
                or receipt.get("revision") != expected_revision or receipt.get("containerId") != row["Id"]
                or receipt.get("imageId") != row["Image"] or receipt.get("runtimeImageDigest") != row["Image"]):
            raise RepairBlocked("DEPLOYMENT_RECEIPT_MISMATCH")
        private_file = self.files.read(RECEIPTS + release_id + ".json", secret=True)
        private = json.loads(private_file.raw)
        if private.get("recordType") != "aurion_traefik_runtime_receipt" or any(
                private.get(key) != receipt.get(key) for key in (
                    "revision", "releaseId", "containerId", "imageId", "domain", "traefikNetwork", "databaseNetwork",
                    *DIGEST_FIELDS.values())):
            raise RepairBlocked("DEPLOYMENT_RECEIPT_MISMATCH")
        self.files.link(RECEIPTS + "current.json", RECEIPTS + release_id + ".json")
        release = RELEASES + release_id
        self.files.link("/opt/aurion-traefik-runtime/current", release)
        compose_path = release + "/docker-compose.traefik.yml"
        labels = row["Config"]["Labels"]
        if (labels.get("com.docker.compose.project.config_files") != compose_path
                or labels.get("com.docker.compose.project.working_dir") != release
                or labels.get("org.opencontainers.image.revision") != expected_revision
                or row["Config"]["Image"] != "echoes-of-aurion:" + expected_revision):
            raise RepairBlocked("ACTIVE_COMPOSE_UNRESOLVED")
        manifest_file = self.files.read(release + "/manifest.json")
        checksums = self.files.read(release + "/checksums.sha256")
        compose_file = self.files.read(compose_path)
        manifest = json.loads(manifest_file.raw)
        if (manifest.get("recordType") != "aurion_traefik_runtime_artifact"
                or manifest.get("revision") != expected_revision
                or fingerprint(manifest_file.raw) != receipt.get("runtimeManifestSha256")
                or "sha256:" + fingerprint(checksums.raw) != receipt.get("artifactDigest")
                or fingerprint(compose_file.raw) != COMPOSE_SHA256
                or manifest.get("files", {}).get("docker-compose.traefik.yml") != COMPOSE_SHA256
                or manifest.get("buildInputDigest") != receipt.get("buildInputDigest")):
            raise RepairBlocked("DEPLOYMENT_MANIFEST_MISMATCH")
        runtime_file = self.files.read(RUNTIME_FILE, secret=True)
        runtime = parse_env(runtime_file.raw)
        expected_routing = {"AURION_ENV_FILE": ENV_FILE, "AURION_DOMAIN": "arelogic.space",
                            "TRAEFIK_NETWORK": "areloria_arelorian-network",
                            "AURION_DATABASE_NETWORK": "echoes-of-aurion-internal"}
        if (any(runtime.get(k) != v for k, v in expected_routing.items())
                or not re.fullmatch(r"[A-Za-z0-9_-]+", runtime.get("TRAEFIK_CERTRESOLVER", ""))
                or set(runtime) != set(expected_routing) | {"TRAEFIK_CERTRESOLVER"}
                or receipt.get("domain") != runtime["AURION_DOMAIN"]
                or receipt.get("traefikNetwork") != runtime["TRAEFIK_NETWORK"]
                or receipt.get("databaseNetwork") != runtime["AURION_DATABASE_NETWORK"]):
            raise RepairBlocked("ROUTING_ENV_INVALID")
        env = self.environment(row)
        compose_env = {**runtime, "AURION_IMAGE_TAG": expected_revision, "AURION_RELEASE_SHA": expected_revision}
        for key, field in DIGEST_FIELDS.items():
            digest = receipt.get(field, "")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest) or env.get(key) != digest:
                raise RepairBlocked("RUNTIME_DIGEST_MISMATCH")
            compose_env[key] = digest
        image = json.loads(self.run(["docker", "image", "inspect", row["Image"]]))
        if (len(image) != 1 or image[0]["Id"] != row["Image"]
                or image[0]["Config"]["Labels"].get("org.opencontainers.image.revision") != expected_revision):
            raise RepairBlocked("IMAGE_REVISION_MISMATCH")
        if any(row["Config"].get(k) != image[0]["Config"].get(k) for k in ("Cmd", "Entrypoint", "User", "WorkingDir")):
            raise RepairBlocked("IMAGE_PROCESS_OVERRIDE")
        production = self.files.read(ENV_FILE, secret=True)
        parsed = parse_env(production.raw)
        # Never turn a changed non-native configuration into an incidental deploy.
        if any(env.get(k) != parsed.get(k) for k in (RELEASE, SEAL)):
            raise RepairBlocked("EFFECTIVE_AUTH_CONFIG_DRIFT")
        context = {"composePath": compose_path, "composeEnv": compose_env, "receipt": receipt,
                   "productionIdentity": production.identity(), "runtimeIdentity": runtime_file.identity(),
                   "composeIdentity": compose_file.identity(), "receiptIdentity": receipt_file.identity(),
                   "privateReceiptIdentity": private_file.identity(), "manifestIdentity": manifest_file.identity(),
                   "checksumsIdentity": checksums.identity(), "containerMetadataFingerprint": self.container_metadata(row)}
        config = json.loads(self.compose(context, "config", "--format", "json"))
        if set(config["services"]) != {"aurion"} or config["services"]["aurion"]["image"] != row["Config"]["Image"]:
            raise RepairBlocked("COMPOSE_SERVICE_MISMATCH")
        effective = config["services"]["aurion"]["environment"]
        if any(env.get(k) != str(v) for k, v in effective.items()):
            raise RepairBlocked("EFFECTIVE_CONFIG_DRIFT")
        context["configFingerprint"] = canonical_hash(self.config_without_auth(config))
        status, health = self.http.request("/healthz")
        healthy = row["State"].get("Running") is True and row["State"].get("Health", {}).get("Status") == "healthy"
        context["healthy"] = healthy and status == 200 and self.health_matches(health, receipt)
        db = json.loads(self.run(["docker", "exec", row["Id"], "node", "--input-type=module", "-e",
            "try {" + DB_SCRIPT + "} catch { process.exitCode = 1; }"], timeout=25))
        context["schemaVerified"] = schema_matches(db)
        context["schemaSourceSha256"] = SCHEMA_SOURCE_SHA256
        return context, production

    def snapshot(self, expected_revision):
        context, production = self.resolve(expected_revision)
        receipt = context["receipt"]
        return {"target": TARGET, "revision": expected_revision, "containerId": receipt["containerId"],
                "imageId": receipt["imageId"], "metadataFingerprint": canonical_hash(context),
                "configurationFingerprint": fingerprint(production.raw),
                "schemaVerified": context["schemaVerified"], "healthy": context["healthy"],
                "configuration": configuration(production.raw)}

    def name(self, kind, operation_id):
        if kind not in {"backup", "host", "image", "probe"} or not re.fullmatch(r"[0-9a-f]{32}", operation_id):
            raise RepairBlocked("HOST_RECORD_IDENTITY")
        return "aurion-native-auth-" + kind + "-" + operation_id + (".env" if kind == "backup" else ".json")

    def write(self, kind, operation_id, raw):
        with self.state.directory() as directory_fd:
            fd = os.open(self.name(kind, operation_id), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory_fd)
            with os.fdopen(fd, "wb") as stream:
                os.fchown(stream.fileno(), 0, 0)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(directory_fd)

    def read(self, kind, operation_id):
        with self.state.directory() as fd:
            return read_protected(fd, self.name(kind, operation_id))

    def host_record(self, operation_id):
        return json.loads(self.read("host", operation_id).raw)

    def backup(self, plan, operation_id):
        context, production = self.resolve(plan["snapshot"]["revision"])
        if (canonical_hash(context) != plan["snapshot"]["metadataFingerprint"]
                or fingerprint(production.raw) != plan["snapshot"]["configurationFingerprint"]):
            raise RepairBlocked("PRE_EFFECT_DRIFT")
        self.write("backup", operation_id, production.raw)
        backup = self.read("backup", operation_id)
        if backup.raw != production.raw:
            raise RepairBlocked("BACKUP_READBACK")
        context["backupIdentity"] = backup.identity()
        self.write("host", operation_id, json.dumps(context, sort_keys=True).encode())
        override = {"services": {"aurion": {"image": context["receipt"]["imageId"]}}}
        self.write("image", operation_id, json.dumps(override).encode())
        return canonical_hash(backup.identity())

    def apply_configuration(self, plan, operation_id):
        record = self.host_record(operation_id)
        # Repeat complete resolution directly before replacing the env file.
        context, before = self.resolve(plan["snapshot"]["revision"])
        if canonical_hash(context) != plan["snapshot"]["metadataFingerprint"]:
            raise RepairBlocked("PRE_EFFECT_DRIFT")
        raw = repaired_env(before.raw, generate_key=plan["generateKey"])
        record["afterFingerprint"] = fingerprint(raw)
        self.update_host(operation_id, record)  # durable expected result before rename
        self.files.replace_env(before, raw)

    def update_host(self, operation_id, record):
        with self.state.directory() as fd:
            before = read_protected(fd, self.name("host", operation_id))
            atomic_replace(fd, self.name("host", operation_id), before, json.dumps(record, sort_keys=True).encode())

    def verify_inputs(self, record, operation_id, *, restored=False):
        receipt = record["receipt"]
        self.files.link(RECEIPTS + "current.json", RECEIPTS + receipt["releaseId"] + ".json")
        self.files.link("/opt/aurion-traefik-runtime/current", RELEASES + receipt["releaseId"])
        if self.files.read(RUNTIME_FILE, secret=True).identity() != record["runtimeIdentity"]:
            raise RepairBlocked("ROUTING_DRIFT")
        if self.files.read(record["composePath"]).identity() != record["composeIdentity"]:
            raise RepairBlocked("COMPOSE_DRIFT")
        for path, key in ((PUBLIC_RECEIPT, "receiptIdentity"),
                          (RECEIPTS + receipt["releaseId"] + ".json", "privateReceiptIdentity"),
                          (RELEASES + receipt["releaseId"] + "/manifest.json", "manifestIdentity"),
                          (RELEASES + receipt["releaseId"] + "/checksums.sha256", "checksumsIdentity")):
            if self.files.read(path, secret=key == "privateReceiptIdentity").identity() != record[key]:
                raise RepairBlocked("DEPLOYMENT_METADATA_DRIFT")
        raw = self.files.read(ENV_FILE, secret=True).raw
        expected = record["productionIdentity"]["sha256"] if restored else record["afterFingerprint"]
        if fingerprint(raw) != expected:
            raise RepairBlocked("CONFIGURATION_DRIFT")
        override = str(self.state.root / self.name("image", operation_id))
        if json.loads(self.read("image", operation_id).raw) != {"services": {"aurion": {"image": receipt["imageId"]}}}:
            raise RepairBlocked("IMAGE_OVERRIDE_DRIFT")
        config = json.loads(self.compose(record, "config", "--format", "json", override=override))
        if (config["services"]["aurion"]["image"] != receipt["imageId"]
                or canonical_hash(self.config_without_auth(config)) != record["configFingerprint"]):
            raise RepairBlocked("COMPOSE_CONFIG_DRIFT")
        expected_auth = parse_env(raw)
        effective = config["services"]["aurion"]["environment"]
        if any(effective.get(k) != expected_auth.get(k) for k in (RELEASE, SEAL)):
            raise RepairBlocked("COMPOSE_AUTH_OVERRIDE")
        return override

    def recreate_same_image(self, plan, operation_id, *, restored=False):
        record = self.host_record(operation_id)
        row = self.inspect()
        self.verify_resources(row)
        if row["Image"] != plan["snapshot"]["imageId"] or row["Config"]["Labels"].get("org.opencontainers.image.revision") != plan["snapshot"]["revision"]:
            raise RepairBlocked("PRE_RECREATE_IDENTITY_DRIFT")
        if not restored and row["Id"] != plan["snapshot"]["containerId"]:
            raise RepairBlocked("PRE_RECREATE_CONTAINER_DRIFT")
        if not restored and self.container_metadata(row) != record["containerMetadataFingerprint"]:
            raise RepairBlocked("PRE_RECREATE_METADATA_DRIFT")
        override = self.verify_inputs(record, operation_id, restored=restored)
        self.compose(record, "config", "--quiet", override=override)
        self.compose(record, "up", "--detach", "--no-build", "--pull", "never", "--no-deps",
                     "--force-recreate", "aurion", override=override)

    def basic_readback(self, plan, operation_id):
        row = self.inspect()
        env = self.environment(row)
        record = self.host_record(operation_id)
        expected = record["receipt"]
        from aurion_native_auth import valid_key
        result = {"sameImage": row["Image"] == plan["snapshot"]["imageId"],
                  "sameRevision": row["Config"]["Labels"].get("org.opencontainers.image.revision") == plan["snapshot"]["revision"],
                  "healthy": False, "releaseEnabled": env.get(RELEASE) == "true",
                  "stateSealKeyPresent": bool(env.get(SEAL)), "stateSealKeyValid": valid_key(env.get(SEAL))}
        try:
            status, health = self.http.request("/healthz")
        except Exception:
            status, health = 0, None
        result["healthy"] = (row["State"].get("Running") is True
            and row["State"].get("Health", {}).get("Status") == "healthy"
            and all(env.get(k) == expected[v] for k, v in DIGEST_FIELDS.items())
            and status == 200 and self.health_matches(health, expected))
        try:
            self.verify_resources(row)
            raw = self.files.read(ENV_FILE, secret=True).raw
            parsed = parse_env(raw)
            allowed_files = record["composePath"] + "," + str(self.state.root / self.name("image", operation_id))
            result["configurationBound"] = (fingerprint(raw) == record.get("afterFingerprint")
                and all(env.get(k) == parsed.get(k) for k in (RELEASE, SEAL))
                and row["Config"]["Labels"].get("com.docker.compose.project.config_files") == allowed_files)
        except Exception:
            result["configurationBound"] = False
        return result

    def verify_after_recreate(self, plan, operation_id):
        result = {}
        for attempt in range(20):
            try:
                result = self.basic_readback(plan, operation_id)
            except Exception:
                result = {}
            if result.get("healthy") and result.get("sameImage") and result.get("sameRevision"):
                break
            if attempt < 19:
                self.sleep(1)
        # Persist admission before sending even one potentially mutating start.
        self.write("probe", operation_id, b'{"phase":"START_ADMITTED","validStart200":false,"invalidBody400":false}')
        valid, invalid = False, False
        if all(result.get(k) is True for k in ("healthy", "sameImage", "sameRevision", "releaseEnabled", "stateSealKeyValid")):
            verifier = secrets.token_urlsafe(32)
            challenge = base64.urlsafe_b64encode(__import__("hashlib").sha256(verifier.encode()).digest()).decode().rstrip("=")
            body = {"version": "aurion.native-auth.v1", "codeChallenge": challenge, "codeChallengeMethod": "S256",
                    "requestState": secrets.token_urlsafe(32), "appBuild": "sovott-native-auth-repair",
                    "platform": "android", "returnId": "aurion.android.app-link.v1"}
            valid = self.http.request("/api/native-auth/start", body)[0] == 200
            invalid = self.http.request("/api/native-auth/start", {})[0] == 400
        with self.state.directory() as fd:
            name = self.name("probe", operation_id)
            before = read_protected(fd, name)
            atomic_replace(fd, name, before, json.dumps({"phase": "COMPLETE", "validStart200": valid, "invalidBody400": invalid}).encode())

    def readback(self, plan, operation_id):
        with self.state.directory() as fd:
            try:
                os.stat(self.name("host", operation_id), dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                # A worker may stop after durable PREPARED but before backup.
                # Resolve the original deployment read-only; never manufacture
                # a host record or retry a target effect during recovery.
                context, production = self.resolve(plan["snapshot"]["revision"])
                receipt = context["receipt"]
                return {"sameImage": receipt["imageId"] == plan["snapshot"]["imageId"],
                        "sameRevision": receipt["revision"] == plan["snapshot"]["revision"],
                        "healthy": context["healthy"], **configuration(production.raw),
                        "configurationBound": False, "validStart200": False, "invalidBody400": False}
        result = self.basic_readback(plan, operation_id)
        try:
            probe = json.loads(self.read("probe", operation_id).raw)
        except RepairBlocked:
            probe = {}
        result.update(validStart200=probe.get("validStart200") is True, invalidBody400=probe.get("invalidBody400") is True)
        return result

    def rollback(self, plan, operation_id, backup_identity):
        record = self.host_record(operation_id)
        backup = self.read("backup", operation_id)
        if canonical_hash(backup.identity()) != backup_identity or backup.identity() != record["backupIdentity"]:
            raise RepairBlocked("ROLLBACK_BACKUP_DRIFT")
        observed = self.basic_readback(plan, operation_id)
        if not observed["sameImage"] or not observed["sameRevision"]:
            raise RepairBlocked("ROLLBACK_IDENTITY_DRIFT")
        self.verify_inputs(record, operation_id)
        current = self.files.read(ENV_FILE, secret=True)
        if fingerprint(current.raw) != record["afterFingerprint"]:
            raise RepairBlocked("ROLLBACK_CONFIG_DRIFT")
        self.files.replace_env(current, backup.raw)
        self.recreate_same_image(plan, operation_id, restored=True)
        for attempt in range(20):
            if self.basic_readback(plan, operation_id)["healthy"]:
                break
            if attempt < 19:
                self.sleep(1)

    def rollback_readback(self, plan, operation_id, backup_identity):
        result = self.basic_readback(plan, operation_id)
        backup = self.read("backup", operation_id)
        raw = self.files.read(ENV_FILE, secret=True).raw
        effective = self.environment(self.inspect())
        original = parse_env(backup.raw)
        result["configurationRestored"] = (canonical_hash(backup.identity()) == backup_identity
            and raw == backup.raw and all(effective.get(k) == original.get(k) for k in (RELEASE, SEAL)))
        return result
