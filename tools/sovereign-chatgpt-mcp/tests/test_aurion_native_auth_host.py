"""Real host adapter against temporary files and external Docker/HTTP fixtures.

No test in this file is production or device evidence.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aurion_native_auth as core
import aurion_native_auth_host as host
import test_aurion_native_auth_files as file_tests


def schema_rows():
    columns, indexes = [], []
    for table, contract in host.SCHEMA.items():
        for name, (typ, nullable) in contract["columns"].items():
            columns.append({"TABLE_NAME": table, "COLUMN_NAME": name, "COLUMN_TYPE": typ,
                            "IS_NULLABLE": "YES" if nullable else "NO", "COLUMN_DEFAULT": None, "EXTRA": ""})
        for name, (unique, cols) in contract["indexes"].items():
            for position, col in enumerate(cols, 1):
                indexes.append({"TABLE_NAME": table, "INDEX_NAME": name, "NON_UNIQUE": unique,
                    "SEQ_IN_INDEX": position, "COLUMN_NAME": col, "SUB_PART": None, "INDEX_TYPE": "BTREE"})
    return {"ready": True, "columns": columns, "indexes": indexes}


class SchemaContracts(unittest.TestCase):
    def test_full_schema_and_mysql_integer_display_width(self):
        value = schema_rows()
        self.assertTrue(host.schema_matches(value))
        for row in value["columns"]:
            if row["COLUMN_TYPE"] == "int":
                row["COLUMN_TYPE"] = "int(11)"
            elif row["COLUMN_TYPE"] == "bigint":
                row["COLUMN_TYPE"] = "bigint(20)"
        self.assertTrue(host.schema_matches(value))

    def test_each_required_column_and_index_is_checked(self):
        initial = schema_rows()
        for group in ("columns", "indexes"):
            for position in range(len(initial[group])):
                value = copy.deepcopy(initial)
                del value[group][position]
                with self.subTest(group=group, position=position):
                    self.assertFalse(host.schema_matches(value))

    def test_type_nullability_uniqueness_and_prefix_drift(self):
        for group, key, new in (("columns", "COLUMN_TYPE", "varchar(63)"),
            ("columns", "IS_NULLABLE", "YES"), ("columns", "EXTRA", "auto_increment"),
            ("indexes", "NON_UNIQUE", 1), ("indexes", "SUB_PART", 10)):
            value = schema_rows()
            # Choose PRIMARY for the uniqueness case.
            index = next(i for i, row in enumerate(value[group]) if group != "indexes" or row["INDEX_NAME"] == "PRIMARY")
            value[group][index][key] = new
            with self.subTest(key=key):
                self.assertFalse(host.schema_matches(value))


class MappedFiles(host.HostFiles):
    def __init__(self, root):
        self.root = root

    def directory(self, path):
        return super().directory(str(self.root / path.lstrip("/")))


class HostAdapterContracts(unittest.TestCase):
    def setUp(self):
        ownership = patch.object(os, "fchown", return_value=None)
        ownership.start()
        self.addCleanup(ownership.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.metadata = file_tests.FilesystemContracts.root_metadata(self, protect_test_ancestors=True)
        self.metadata.start()
        self.addCleanup(self.metadata.stop)
        original_stat = os.stat
        def root_stat(*args, **kwargs):
            value = original_stat(*args, **kwargs)
            fields = {key: getattr(value, key) for key in dir(value) if key.startswith("st_")}
            fields.update(st_uid=0, st_gid=0)
            return SimpleNamespace(**fields)
        self.stat_patch = patch.object(host.os, "stat", side_effect=root_stat)
        self.stat_patch.start()
        self.addCleanup(self.stat_patch.stop)
        self.state_root = self.root / "state"
        self.state_root.mkdir(mode=0o700)
        self.state = core.NativeAuthState(self.state_root)
        self.revision = "a" * 40
        self.release_id = self.revision + "-42"
        self.release = host.RELEASES + self.release_id
        self.compose_path = self.release + "/docker-compose.traefik.yml"
        self.image = "sha256:" + "b" * 64
        self.container = "c" * 64
        self.env = {"UNRELATED": "SYNTHETIC_PRIVATE_ENV_VALUE"}
        self.write(core.ENV_FILE, b"UNRELATED=SYNTHETIC_PRIVATE_ENV_VALUE\n")
        routing = {"AURION_ENV_FILE": core.ENV_FILE, "AURION_DOMAIN": "arelogic.space",
                   "TRAEFIK_NETWORK": "areloria_arelorian-network",
                   "AURION_DATABASE_NETWORK": "echoes-of-aurion-internal", "TRAEFIK_CERTRESOLVER": "letsencrypt"}
        self.write(core.RUNTIME_FILE, "".join(k + "=" + v + "\n" for k, v in routing.items()).encode())
        self.compose_bytes = b"services: synthetic-reviewed-compose-contract\n"
        self.compose_hash = core.fingerprint(self.compose_bytes)
        self.compose_pin = patch.object(host, "COMPOSE_SHA256", self.compose_hash)
        self.compose_pin.start()
        self.addCleanup(self.compose_pin.stop)
        self.write(self.compose_path, self.compose_bytes, 0o644)
        checksums = b"synthetic checksums manifest\n"
        self.write(self.release + "/checksums.sha256", checksums, 0o644)
        manifest = {"recordType": "aurion_traefik_runtime_artifact", "revision": self.revision,
                    "files": {"docker-compose.traefik.yml": self.compose_hash}, "buildInputDigest": "sha256:" + "d" * 64}
        manifest_bytes = json.dumps(manifest).encode()
        self.write(self.release + "/manifest.json", manifest_bytes, 0o644)
        self.receipt = {"recordType": "aurion_traefik_runtime_readback", "revision": self.revision,
            "releaseId": self.release_id, "containerId": self.container, "imageId": self.image,
            "runtimeImageDigest": self.image, "buildInputDigest": manifest["buildInputDigest"],
            "artifactDigest": "sha256:" + core.fingerprint(checksums), "releaseArchiveDigest": "sha256:" + "e" * 64,
            "runtimeManifestSha256": core.fingerprint(manifest_bytes), "domain": "arelogic.space",
            "traefikNetwork": routing["TRAEFIK_NETWORK"], "databaseNetwork": routing["AURION_DATABASE_NETWORK"]}
        self.write(host.PUBLIC_RECEIPT, json.dumps(self.receipt).encode(), 0o644)
        self.write(host.RECEIPTS + self.release_id + ".json",
                   json.dumps({**self.receipt, "recordType": "aurion_traefik_runtime_receipt"}).encode())
        for link, target in ((host.RECEIPTS + "current.json", host.RECEIPTS + self.release_id + ".json"),
                             ("/opt/aurion-traefik-runtime/current", self.release)):
            (self.root / link.lstrip("/")).symlink_to(target)
        self.env.update({k: self.receipt[v] for k, v in host.DIGEST_FIELDS.items()})
        self.row = {"Name": "/" + host.CONTAINER, "Id": self.container, "Image": self.image,
            "Mounts": [{"Type": "volume", "Name": name, "Destination": dest, "RW": True} for dest, name in host.VOLUMES.items()],
            "NetworkSettings": {"Networks": {"areloria_arelorian-network": {}, "echoes-of-aurion-internal": {}}},
            "HostConfig": {"Privileged": False, "ReadonlyRootfs": False, "Memory": 0, "NanoCpus": 0,
                           "PidMode": "", "UsernsMode": "", "RestartPolicy": {"Name": "unless-stopped"}},
            "State": {"Running": True, "Health": {"Status": "healthy"}},
            "Config": {"Healthcheck": {**host.HEALTH_TIMING, "Test": ["CMD-SHELL", host.HEALTH_COMMAND]}, "Image": "echoes-of-aurion:" + self.revision,
                "Labels": {"com.docker.compose.project": "echoes-of-aurion", "com.docker.compose.service": "aurion",
                    "com.docker.compose.project.config_files": self.compose_path,
                    "com.docker.compose.project.working_dir": self.release,
                    "org.opencontainers.image.revision": self.revision},
                "Env": [k + "=" + v for k, v in self.env.items()]}}
        self.commands, self.requests = [], []
        self.db = schema_rows()
        self.fail_health_after_up = False
        self.up_count = 0
        self.elapsed = 0
        self.started_at = 0
        self.health_after = {}
        self.host = host.AurionNativeAuthHost(self.state, runner=self.runner, files=MappedFiles(self.root),
                                            http=SimpleNamespace(request=self.http), sleep=self.advance, monotonic=lambda: self.elapsed)
        self.runtime = core.NativeAuthRepair(self.host, self.state)

    def advance(self, seconds):
        self.elapsed += seconds

    def write(self, path, raw, mode=0o600):
        p = self.root / path.lstrip("/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        p.chmod(mode)

    def current_env(self):
        raw = (self.root / core.ENV_FILE.lstrip("/")).read_text()
        values = dict(line.split("=", 1) for line in raw.splitlines() if line and not line.startswith("#"))
        return {**values, **{k: self.receipt[v] for k, v in host.DIGEST_FIELDS.items()}}

    def runner(self, argv, **kwargs):
        self.commands.append((argv, kwargs))
        if argv[:2] == ["docker", "inspect"]:
            if self.up_count in self.health_after:
                delay, final = self.health_after[self.up_count]
                self.row["State"]["Health"]["Status"] = final if self.elapsed - self.started_at >= delay else "starting"
            payload = [self.row]
        elif argv[:3] == ["docker", "image", "inspect"]:
            payload = [{"Id": self.image, "Config": {"Env": [], "Healthcheck": {**host.HEALTH_TIMING, "Test": ["CMD-SHELL", host.HEALTH_COMMAND]}, "Labels": {"org.opencontainers.image.revision": self.revision}}}]
        elif argv[:3] == ["docker", "volume", "inspect"]:
            payload = [{"Name": name} for name in host.VOLUMES.values()]
        elif argv[:2] == ["docker", "exec"]:
            self.assertEqual(argv[2], self.container)
            self.assertNotIn("verify-aurion-runtime-database.mjs", argv)
            payload = self.db
        elif argv[:2] == ["docker", "compose"]:
            if "up" in argv:
                self.up_count += 1
                self.started_at = self.elapsed
                self.row["Id"] = "f" * 64
                self.row["Config"]["Env"] = [k + "=" + v for k, v in self.current_env().items()]
                self.row["Config"]["Labels"]["com.docker.compose.project.config_files"] = ",".join(argv[i + 1] for i, arg in enumerate(argv) if arg == "-f")
                self.row["State"]["Health"]["Status"] = "unhealthy" if self.fail_health_after_up and self.up_count == 1 else "healthy"
                payload = None
            elif "--quiet" in argv:
                payload = None
            else:
                pinned = argv.count("-f") == 2
                payload = {"services": {"aurion": {"image": self.image if pinned else "echoes-of-aurion:" + self.revision,
                                                    "environment": self.current_env()}}, "name": "echoes-of-aurion"}
        else:
            self.fail("Unexpected external operation")
        return subprocess.CompletedProcess(argv, 0, "" if payload is None else json.dumps(payload), "")

    def http(self, path, body=None):
        self.requests.append((path, body))
        if path == "/healthz":
            health = {"status": "ok", "service": "echoes-of-aurion", "revision": self.revision,
                **{field: self.receipt[field] for field in host.DIGEST_FIELDS.values()},
                "authority": {"ruleset": "aurion-zone-v3", "tickHz": 10, "causalReceipts": True}}
            return 200, health
        return (200 if body else 400), None

    def approve(self):
        plan = self.runtime.plan(self.revision)
        return plan, self.runtime.issue(plan["planHash"], self.revision)["operationId"]

    def test_full_adapter_plan_apply_and_readback(self):
        plan, operation = self.approve()
        result = self.runtime.apply(operation)
        self.assertEqual(result["phase"], "VERIFIED")
        self.assertTrue(result["ok"])
        self.assertEqual(self.up_count, 1)
        up = next(argv for argv, _ in self.commands if "up" in argv)
        self.assertEqual(up[-8:], ["up", "--detach", "--no-build", "--pull", "never", "--no-deps", "--force-recreate", "aurion"])
        override = json.loads(self.host.read("image", operation).raw)
        self.assertEqual(override, {"services": {"aurion": {"image": self.image}}})
        self.assertEqual(len([p for p, body in self.requests if body is not None]), 2)
        self.runtime.readback(operation)
        self.runtime.apply(operation)
        self.assertEqual(len([p for p, body in self.requests if body is not None]), 2)
        self.assertEqual(self.up_count, 1)
        self.assertNotIn("SYNTHETIC_PRIVATE_ENV_VALUE", json.dumps(result))
        for argv, _ in self.commands:
            self.assertNotIn("SYNTHETIC_PRIVATE_ENV_VALUE", " ".join(argv))

    def test_schema_drift_blocks_before_backup(self):
        self.db["indexes"].pop()
        with self.assertRaisesRegex(core.RepairBlocked, "SCHEMA_MISMATCH"):
            self.runtime.plan(self.revision)
        self.assertEqual(self.up_count, 0)

    def test_prepared_without_host_backup_readback_is_read_only(self):
        plan, operation = self.approve()
        with self.state.lock():
            self.state.begin(operation, {"operationId": operation, "plan": plan, "phase": "PREPARED"})
            self.state.consume(operation)
        result = self.runtime.readback(operation)
        self.assertEqual(result["phase"], "PREPARED")
        self.assertTrue(result["readback"]["sameImage"])
        self.assertTrue(result["readback"]["healthy"])
        self.assertEqual(self.up_count, 0)
        self.assertFalse(any(body is not None for _, body in self.requests))

    def test_existing_key_is_reused_end_to_end(self):
        raw = core.repaired_env(b"UNRELATED=SYNTHETIC_PRIVATE_ENV_VALUE\n", generate_key=True)
        raw = raw.replace(b"NATIVE_AUTH_RELEASE_ENABLED=true", b"NATIVE_AUTH_RELEASE_ENABLED=false")
        self.write(core.ENV_FILE, raw)
        self.row["Config"]["Env"] = [k + "=" + v for k, v in self.current_env().items()]
        original_key = core.parse_env(raw)[core.SEAL]
        plan, operation = self.approve()
        self.assertFalse(plan["generateKey"])
        self.runtime.apply(operation)
        actual = (self.root / core.ENV_FILE.lstrip("/")).read_bytes()
        self.assertEqual(core.parse_env(actual)[core.SEAL], original_key)

    def test_missing_or_changed_volume_blocks_plan(self):
        self.row["Mounts"].pop()
        with self.assertRaisesRegex(core.RepairBlocked, "HOST_ADAPTER_FAILED"):
            self.runtime.plan(self.revision)
        self.assertEqual(self.up_count, 0)

    def test_receipt_container_drift_blocks(self):
        self.row["Id"] = "0" * 64
        with self.assertRaisesRegex(core.RepairBlocked, "HOST_ADAPTER_FAILED"):
            self.runtime.plan(self.revision)

    def test_unexpected_receipt_fields_are_never_persisted(self):
        marker = "SYNTHETIC_PRIVATE_RECEIPT_FIELD"
        self.write(host.PUBLIC_RECEIPT, json.dumps({**self.receipt, "unexpected": marker}).encode(), 0o644)
        _, operation = self.approve()
        result = self.runtime.apply(operation)
        self.assertEqual(result["phase"], "VERIFIED")
        self.assertNotIn(marker, json.dumps(result))
        for path in self.state_root.glob("*.json"):
            self.assertNotIn(marker, path.read_text())

    def test_compose_path_cannot_select_other_deployment(self):
        self.row["Config"]["Labels"]["com.docker.compose.project.config_files"] = "/tmp/other.yml"
        with self.assertRaisesRegex(core.RepairBlocked, "HOST_ADAPTER_FAILED"):
            self.runtime.plan(self.revision)

    def test_config_drift_after_approval_denies_all_target_writes(self):
        _, operation = self.approve()
        self.write(core.ENV_FILE, b"UNRELATED=changed\n")
        with self.assertRaises(core.RepairBlocked):
            self.runtime.apply(operation)
        self.assertEqual(self.up_count, 0)
        self.assertFalse(any(self.state_root.glob("*backup*")))

    def test_health_failure_restores_original_env_same_image(self):
        original = (self.root / core.ENV_FILE.lstrip("/")).read_bytes()
        _, operation = self.approve()
        self.fail_health_after_up = True
        result = self.runtime.apply(operation)
        self.assertEqual(result["phase"], "ROLLED_BACK")
        self.assertEqual((self.root / core.ENV_FILE.lstrip("/")).read_bytes(), original)
        self.assertEqual(self.up_count, 2)
        self.assertEqual(len([body for _, body in self.requests if body is not None]), 0)

    def test_delayed_healthy_after_normal_start_does_not_roll_back(self):
        self.health_after[1] = (32, "healthy")
        _, operation = self.approve()
        result = self.runtime.apply(operation)
        self.assertEqual(result["phase"], "VERIFIED")
        self.assertGreaterEqual(self.elapsed, 32)
        self.assertEqual(self.up_count, 1)

    def test_start_timeout_rolls_back_and_waits_for_delayed_recovery(self):
        original = (self.root / core.ENV_FILE.lstrip("/")).read_bytes()
        self.health_after = {1: (1000, "healthy"), 2: (32, "healthy")}
        _, operation = self.approve()
        result = self.runtime.apply(operation)
        self.assertEqual(result["phase"], "ROLLED_BACK")
        self.assertEqual(self.elapsed, 187)
        receipt = self.state.read("receipt", operation)
        self.assertEqual(receipt["startupOutcome"], "timeout")
        self.assertEqual(receipt["rollbackStartupOutcome"], "healthy")
        self.assertEqual((self.root / core.ENV_FILE.lstrip("/")).read_bytes(), original)
        self.assertFalse(any(body is not None for _, body in self.requests))

    def test_rollback_timeout_remains_uncertain_without_repeated_recreation(self):
        self.health_after = {1: (0, "unhealthy"), 2: (1000, "healthy")}
        _, operation = self.approve()
        result = self.runtime.apply(operation)
        self.assertEqual(result["phase"], "ROLLBACK_UNVERIFIED")
        self.assertEqual(self.state.read("receipt", operation)["rollbackStartupOutcome"], "timeout")
        self.assertEqual(self.elapsed, 155)
        self.runtime.apply(operation)
        self.assertEqual(self.up_count, 2)

    def test_unknown_health_does_not_authorize_rollback(self):
        self.health_after[1] = (0, "unknown")
        _, operation = self.approve()
        result = self.runtime.apply(operation)
        self.assertEqual(result["phase"], "APPLIED_UNVERIFIED")
        self.assertEqual(self.state.read("receipt", operation)["startupOutcome"], "unknown")
        self.assertEqual(self.elapsed, 155)
        self.assertEqual(self.up_count, 1)

    def test_healthcheck_drift_blocks_before_backup(self):
        self.row["Config"]["Healthcheck"]["Interval"] = 60_000_000_000
        with self.assertRaises(core.RepairBlocked):
            self.runtime.plan(self.revision)
        self.assertEqual(self.up_count, 0)

    def test_removed_unrelated_env_blocks_plan(self):
        self.write(core.ENV_FILE, b"")
        with self.assertRaises(core.RepairBlocked):
            self.runtime.plan(self.revision)
        self.assertEqual(self.up_count, 0)
        self.assertFalse(any(self.state_root.glob("*backup*")))

    def test_secret_command_error_is_redacted(self):
        self.host.runner = lambda *a, **k: subprocess.CompletedProcess(a, 1, "SYNTHETIC_PRIVATE_STDOUT", "SYNTHETIC_PRIVATE_STDERR")
        with self.assertRaisesRegex(core.RepairBlocked, "HOST_ADAPTER_FAILED"):
            self.runtime.plan(self.revision)


if __name__ == "__main__":
    unittest.main()
