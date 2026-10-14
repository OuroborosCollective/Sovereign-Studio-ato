from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from managed_compose import ManagedComposeRuntime, STACKS


def inventory():
    containers = {}
    for service in ("server", "database", "redis", "guacd"):
        name = f"patchmon-sovereign-{service}-1"
        mounts = []
        if service in {"database", "redis"}:
            mounts = [{
                "type": "volume", "rw": True,
                "destination": "/data" if service == "redis" else "/var/lib/postgresql/data",
                "name": "patchmon-sovereign_patchmon_redis_data" if service == "redis" else "patchmon-sovereign_patchmon_postgres_data",
            }]
        containers[name] = {"present": True, "project": "patchmon-sovereign", "service": service,
                            "id": service + "-identity", "imageId": service + "-image", "mounts": mounts,
                            "networks": [{"name": "patchmon-sovereign_patchmon-internal"}]}
    return {
        "ok": False, "containers": containers,
        "boundaryViolations": [{"code": "PATCHMON_NETWORK_INTERNAL_MODE_MISMATCH"}],
        "networks": [{"name": "patchmon-sovereign_patchmon-internal", "internal": False}],
        "httpHealth": {"ok": True}, "fleet": {"ok": True},
        "redisDependencies": {
            "status": "REDIS_DEPENDENCY_EVIDENCE_OBSERVED", "unknownConnectionCount": 0,
            "configuredConsumers": [{"container": "patchmon-sovereign-server-1", "match": "PATCHMON_REDIS"}],
            "connectedConsumers": [{"container": "patchmon-sovereign-server-1", "connectionCount": 11}],
        },
    }


class PatchmonNetworkMigrationTests(unittest.TestCase):
    def runtime(self, evidence):
        runtime = ManagedComposeRuntime()
        runtime._patchmon_inventory = lambda: copy.deepcopy(evidence)
        return runtime

    def test_plan_binds_container_network_and_volume_identity(self):
        before = inventory()
        plan = self.runtime(before)._patchmon_topology_plan()
        self.assertTrue(plan["ok"])
        self.assertTrue(plan["required"])
        self.assertEqual(len(plan["volumes"]), 2)
        after = copy.deepcopy(before)
        after["containers"]["patchmon-sovereign-redis-1"]["id"] = "replacement"
        changed = self.runtime(after)._patchmon_topology_plan()
        self.assertNotEqual(plan["stateSha256"], changed["stateSha256"])
        self.assertTrue(plan["oldNetworkPreserved"])
        self.assertFalse(plan["volumesDeleted"])

    def test_connection_count_churn_does_not_change_the_bound_consumer_set(self):
        evidence = inventory()
        before = self.runtime(evidence)._patchmon_topology_plan()
        evidence["redisDependencies"]["connectedConsumers"][0]["connectionCount"] = 12
        after = self.runtime(evidence)._patchmon_topology_plan()
        self.assertEqual(before["stateSha256"], after["stateSha256"])

    def test_template_only_hash_cannot_authorize_a_migration(self):
        plan = self.runtime(inventory())._patchmon_topology_plan()
        confirmation = ManagedComposeRuntime._patchmon_confirmation("a" * 64, plan)
        self.assertNotEqual(confirmation, "a" * 64)
        self.assertEqual(len(confirmation), 64)

    def test_external_and_unresolved_dependencies_block(self):
        for match in ("PATCHMON_REDIS", "OTHER_OR_UNRESOLVED", "AMBIGUOUS"):
            with self.subTest(match=match):
                evidence = inventory()
                evidence["redisDependencies"]["configuredConsumers"].append({"container": "aurion", "match": match})
                result = self.runtime(evidence)._patchmon_topology_plan()
                self.assertFalse(result["ok"])
                self.assertIn("REDIS_EXTERNAL_OR_UNRESOLVED_CONFIGURATION", result["blockers"])

    def test_empty_connections_do_not_authorize_foreign_network_detachment(self):
        evidence = inventory()
        evidence["redisDependencies"]["connectedConsumers"] = []
        evidence["containers"]["patchmon-sovereign-redis-1"]["networks"].append({"name": "echoes-of-aurion-internal"})
        result = self.runtime(evidence)._patchmon_topology_plan()
        self.assertFalse(result["ok"])
        self.assertIn("REDIS_FOREIGN_NETWORK_DEPENDENCY_REVIEW_REQUIRED", result["blockers"])

    def test_unknown_external_client_partial_inventory_and_wrong_volume_block(self):
        cases = []
        unknown = inventory(); unknown["redisDependencies"]["unknownConnectionCount"] = 1; cases.append(unknown)
        external = inventory(); external["redisDependencies"]["connectedConsumers"].append({"container": "freellm"}); cases.append(external)
        partial = inventory(); partial["fleet"]["ok"] = False; cases.append(partial)
        foreign = inventory(); foreign["containers"]["patchmon-sovereign-redis-1"]["project"] = "foreign"; cases.append(foreign)
        volume = inventory(); volume["containers"]["patchmon-sovereign-redis-1"]["mounts"][0]["name"] = "different-data"; cases.append(volume)
        for evidence in cases:
            with self.subTest(evidence=evidence):
                self.assertFalse(self.runtime(evidence)._patchmon_topology_plan()["ok"])

    def test_unresolved_consumers_block_before_any_write(self):
        evidence = inventory()
        evidence["redisDependencies"]["configuredConsumers"].append({"container": "aurion", "match": "OTHER_OR_UNRESOLVED"})
        runtime = self.runtime(evidence)
        runtime._template_files = lambda stack: ([("docker-compose.yml", b"name: patchmon-sovereign\n")], "a" * 64)
        runtime._ensure_stack_secret_env = lambda stack: self.fail("blocked migration must not write credentials")
        with patch.dict(os.environ, {"SOVEREIGN_MCP_PRIVATE_OWNER_MODE": "1", "SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE": "1"}):
            result = runtime.deploy("patchmon-sovereign", "a" * 64)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["mutationPerformed"])

    def test_post_deploy_volume_swap_rolls_back_and_never_reports_success(self):
        before = inventory()
        runtime = self.runtime(before)
        topology = runtime._patchmon_topology_plan()
        commands = []
        runtime._run = lambda argv, **kwargs: commands.append(argv) or {"ok": True, "exit_code": 0}
        after = inventory(); after["containers"]["patchmon-sovereign-redis-1"]["mounts"][0]["name"] = "different-data"
        runtime._patchmon_inventory = lambda: after
        with tempfile.TemporaryDirectory() as root:
            from dataclasses import replace
            stack = replace(STACKS["patchmon-sovereign"], deploy_root=root)
            result = runtime._patchmon_rollback(stack, ["docker", "compose"], [("docker-compose.yml", b"previous\n")], topology)
            self.assertEqual((Path(root) / "docker-compose.yml").read_bytes(), b"previous\n")
        self.assertFalse(result["ok"])
        self.assertFalse(result["runtimeVerified"])
        self.assertFalse(result["rollback"]["volumesPreserved"])
        self.assertIn("--pull", commands[0])
        self.assertNotIn("down", commands[0])
        self.assertNotIn("--volumes", commands[0])

    def migration(self, *, fail_after=False, change_before_apply=False):
        from dataclasses import replace
        before = inventory()
        after = copy.deepcopy(before)
        after["ok"] = True
        after["boundaryViolations"] = []
        if fail_after:
            after["containers"]["patchmon-sovereign-redis-1"]["mounts"][0]["name"] = "unexpected"
        commands = []
        applied = False
        calls = 0
        def runner(argv, **kwargs):
            nonlocal applied
            commands.append(argv)
            if "--force-recreate" in argv:
                applied = True
            return subprocess.CompletedProcess(argv, 0, "", "")
        runtime = ManagedComposeRuntime(runner=runner)
        def observe():
            nonlocal calls
            calls += 1
            result = copy.deepcopy(after if applied else before)
            if change_before_apply and calls >= 3:
                result["containers"]["patchmon-sovereign-redis-1"]["id"] = "changed"
            return result
        runtime._patchmon_inventory = observe
        runtime._template_files = lambda stack: ([("docker-compose.yml", b"new-template\n")], "a" * 64)
        runtime._ensure_stack_secret_env = lambda stack: {"created": False}
        runtime._render_template = lambda stack, files: (None, type("Temporary", (), {"cleanup": lambda self: None})(), {})
        states = {name: {"running": True} for name in STACKS["patchmon-sovereign"].expected_containers}
        states["patchmon-sovereign-server-1"].update({
            "present": True, "project": "patchmon-sovereign", "service": "server",
            "networks": ["patchmon-sovereign_patchmon-edge"],
            "publishedPorts": {"3000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "32830"}]},
        })
        runtime._inspect = lambda container: states[container]
        runtime._verify_expected = lambda stack: states
        runtime._patchmon_http_canary = lambda: {"ok": True}
        with tempfile.TemporaryDirectory() as root:
            stack = replace(STACKS["patchmon-sovereign"], deploy_root=root)
            (Path(root) / "docker-compose.yml").write_bytes(b"old-template\n")
            with patch.dict(STACKS, {"patchmon-sovereign": stack}), patch.dict(os.environ, {"SOVEREIGN_MCP_PRIVATE_OWNER_MODE": "1", "SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE": "1"}):
                topology = runtime._patchmon_topology_plan()
                result = runtime.deploy("patchmon-sovereign", runtime._patchmon_confirmation("a" * 64, topology))
            template = (Path(root) / "docker-compose.yml").read_bytes()
        return result, commands, template

    def test_successful_apply_scopes_recreation_to_four_services(self):
        result, commands, template = self.migration()
        self.assertEqual(result["status"], "DEPLOYED_VERIFIED")
        calls = [c for c in commands if "--force-recreate" in c]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][-4:], ["server", "database", "redis", "guacd"])
        self.assertNotIn("--remove-orphans", calls[0])
        self.assertEqual(template, b"new-template\n")

    def test_actual_apply_volume_readback_failure_restores_previous_template(self):
        result, commands, template = self.migration(fail_after=True)
        self.assertEqual(result["status"], "PATCHMON_MIGRATION_FAILED")
        self.assertTrue(result["rollback"]["attempted"])
        self.assertFalse(result["ok"])
        self.assertEqual(template, b"old-template\n")
        self.assertEqual(len([c for c in commands if "--force-recreate" in c]), 2)

    def test_rebinding_drift_blocks_before_container_or_template_replacement(self):
        result, commands, template = self.migration(change_before_apply=True)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["blocker"], "PATCHMON_TOPOLOGY_CHANGED_BEFORE_APPLY")
        self.assertFalse(any("--force-recreate" in c for c in commands))
        self.assertEqual(template, b"old-template\n")

    def test_unowned_destination_network_is_rejected(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append(argv)
            payload = "abcd1234\n" if "ls" in argv else json.dumps([{
                "Name": "patchmon-sovereign_patchmon-internal-v2", "Driver": "bridge",
                "Internal": True, "Labels": {"com.docker.compose.project": "foreign"}, "Containers": {},
            }])
            return subprocess.CompletedProcess(argv, 0, payload, "")
        self.assertFalse(ManagedComposeRuntime(runner=runner)._patchmon_destination_preflight())
        self.assertTrue(all("connect" not in c and "rm" not in c for c in calls))


if __name__ == "__main__":
    unittest.main()
