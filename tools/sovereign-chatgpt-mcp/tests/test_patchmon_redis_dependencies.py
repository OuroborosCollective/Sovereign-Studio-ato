from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patchmon_operator import PatchmonOperatorRuntime, PATCHMON_PROJECT, PATCHMON_REDIS_CONTAINER

REDIS_ID = "a" * 64
APP_ID = "b" * 64
OTHER_ID = "c" * 64
HEADER = "  sl  local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n"


def proc_row(remote="030002AC", port="18EB", state="01"):
    return f"0: 020002AC:{port} {remote}:C350 {state} 00000000:00000000 00:00000000 00000000 0 0 1\n"


def container(ident, name, ip, aliases, env=None):
    return {"id": ident, "name": "/" + name, "env": env or [],
            "labels": {"com.docker.compose.project": PATCHMON_PROJECT,
                       "com.docker.compose.service": "redis" if ident == REDIS_ID else "server"},
            "networks": {"shared": {"IPAddress": ip, "GlobalIPv6Address": "", "Aliases": aliases}}}


class RedisDependencyEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            container(REDIS_ID, PATCHMON_REDIS_CONTAINER, "172.2.0.2", ["redis"]),
            container(APP_ID, "app-1", "172.2.0.3", ["app"],
                      ["REDIS_URL=redis://redis:6379/0?private=do-not-return",
                       "UNRELATED_SETTING=do-not-return"]),
        ]
        self.raw = HEADER + proc_row() + HEADER
        self.calls = []
        self.inspect_fail = False
        self.proc_fail = False

    def runtime(self):
        def runner(argv, **kwargs):
            self.calls.append(argv)
            if argv[:3] == ["docker", "inspect", "--format"]:
                return subprocess.CompletedProcess(argv, 1 if self.inspect_fail else 0,
                                                   "\n".join(json.dumps(r) for r in self.rows),
                                                   "do-not-return")
            if argv == ["docker", "exec", REDIS_ID, "cat", "/proc/net/tcp", "/proc/net/tcp6"]:
                return subprocess.CompletedProcess(argv, 1 if self.proc_fail else 0, self.raw,
                                                   "do-not-return")
            raise AssertionError(argv)
        return PatchmonOperatorRuntime(runner=runner)

    def fleet(self):
        return {"ok": True, "truncated": False,
                "containers": [{"id": r["id"]} for r in self.rows]}

    def test_configured_and_live_client_are_independently_observed_without_values(self):
        result = self.runtime()._redis_dependency_evidence(self.fleet())
        self.assertEqual(result["status"], "REDIS_DEPENDENCY_EVIDENCE_OBSERVED")
        self.assertEqual(result["configuredConsumers"][0]["match"], "PATCHMON_REDIS")
        self.assertEqual(result["connectedConsumers"], [
            {"containerId": APP_ID, "container": "app-1", "connectionCount": 1}])
        self.assertFalse(result["safeToDetach"])
        encoded = json.dumps(result)
        for private in ("do-not-return", "redis://", "UNRELATED_SETTING"):
            self.assertNotIn(private, encoded)
        self.assertEqual(len(result["evidenceSha256"]), 64)
        self.assertEqual(len(self.calls), 2)

    def test_no_connections_does_not_authorize_detach(self):
        self.raw = HEADER + HEADER
        result = self.runtime()._redis_dependency_evidence(self.fleet())
        self.assertEqual(result["connectedConsumers"], [])
        self.assertEqual(result["connectionStatus"], "ESTABLISHED_TCP_SNAPSHOT")
        self.assertFalse(result["safeToDetach"])

    def test_malformed_and_unsupported_endpoint_values_are_not_returned(self):
        for value in ("https://do-not-return", "redis://[bad", "redis://redis:bad",
                      "redis://redis:0", "redis://redis:65536"):
            with self.subTest(value=value):
                self.rows[1]["env"] = ["REDIS_URL=" + value]
                result = self.runtime()._redis_dependency_evidence(self.fleet())
                self.assertEqual(result["configuredConsumers"][0]["match"], "UNRESOLVED")
                self.assertNotIn(value, json.dumps(result))

    def test_plain_host_and_address_match_only_shared_networks(self):
        for host in ("redis", "172.2.0.2", PATCHMON_REDIS_CONTAINER):
            self.rows[1]["env"] = ["REDIS_HOST=" + host]
            result = self.runtime()._redis_dependency_evidence(self.fleet())
            self.assertEqual(result["configuredConsumers"][0]["match"], "PATCHMON_REDIS")
        self.rows[1]["networks"] = {"unrelated": self.rows[1]["networks"]["shared"]}
        result = self.runtime()._redis_dependency_evidence(self.fleet())
        self.assertEqual(result["configuredConsumers"][0]["match"], "OTHER_OR_UNRESOLVED")

    def test_ambiguous_alias_is_not_claimed_as_target_dependency(self):
        self.rows.append(container(OTHER_ID, "other-redis", "172.2.0.4", ["redis"]))
        result = self.runtime()._redis_dependency_evidence(self.fleet())
        self.assertEqual(result["configuredConsumers"][0]["match"], "AMBIGUOUS")

    def test_unknown_tcp_peer_only_returns_count(self):
        self.raw = HEADER + proc_row("990002AC") + HEADER
        result = self.runtime()._redis_dependency_evidence(self.fleet())
        self.assertEqual(result["unknownConnectionCount"], 1)
        self.assertEqual(result["connectedConsumers"], [])
        self.assertNotIn("172.2.0.153", json.dumps(result))

    def test_duplicate_ip_is_unknown(self):
        self.rows.append(container(OTHER_ID, "ambiguous-peer", "172.2.0.3", []))
        result = self.runtime()._redis_dependency_evidence(self.fleet())
        self.assertEqual(result["unknownConnectionCount"], 1)

    def test_proc_unavailable_keeps_configuration_but_not_connection_claim(self):
        self.proc_fail = True
        result = self.runtime()._redis_dependency_evidence(self.fleet())
        self.assertEqual(result["status"], "REDIS_DEPENDENCY_EVIDENCE_PARTIAL")
        self.assertEqual(result["connectionStatus"], "UNAVAILABLE")
        self.assertNotIn("do-not-return", json.dumps(result))

    def test_incomplete_proc_is_invalid_not_empty_success(self):
        for raw in ("", HEADER, HEADER + "do-not-return\n" + HEADER):
            self.raw = raw
            result = self.runtime()._redis_dependency_evidence(self.fleet())
            self.assertEqual(result["connectionStatus"], "INVALID_TCP_SNAPSHOT")
            self.assertNotIn("do-not-return", json.dumps(result))

    def test_fleet_validation_rejects_unsafe_ids_partial_or_unbounded_inspection(self):
        for fleet in ({"ok": False}, {"ok": True, "truncated": True},
                      {"ok": True, "containers": [{"id": "--bad"}]},
                      {"ok": True, "containers": [{"id": APP_ID}] * 65},
                      {"ok": True, "containers": [{"id": APP_ID}, {"id": APP_ID}]}):
            self.assertEqual(self.runtime()._redis_dependency_evidence(fleet)["status"],
                             "REDIS_DEPENDENCY_EVIDENCE_UNAVAILABLE")
        self.assertEqual(self.calls, [])

    def test_wrong_redis_labels_or_stale_ids_never_exec(self):
        for mutation in ("labels", "id"):
            self.setUp()
            fleet = self.fleet()
            self.rows[0]["labels" if mutation == "labels" else "id"] = {} if mutation == "labels" else OTHER_ID
            result = self.runtime()._redis_dependency_evidence(fleet)
            self.assertEqual(result["status"], "REDIS_DEPENDENCY_EVIDENCE_UNAVAILABLE")
            self.assertEqual(len(self.calls), 1)

    def test_inspect_failure_never_leaks_stderr_or_executes(self):
        self.inspect_fail = True
        result = self.runtime()._redis_dependency_evidence(self.fleet())
        self.assertEqual(result["status"], "REDIS_DEPENDENCY_EVIDENCE_UNAVAILABLE")
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn("do-not-return", json.dumps(result))

    def test_ipv6_mapped_tcp_and_non_redis_connections(self):
        self.raw = (HEADER + proc_row(port="1234") + proc_row(state="0A") + HEADER
                    + proc_row("0000000000000000FFFF0000030002AC"))
        result = self.runtime()._redis_dependency_evidence(self.fleet())
        self.assertEqual(result["connectedConsumers"][0]["connectionCount"], 1)

    def test_duplicate_env_settings_remain_visible_as_ambiguity_to_reviewer(self):
        self.rows[1]["env"] = ["REDIS_HOST=redis", "REDIS_HOST=elsewhere"]
        result = self.runtime()._redis_dependency_evidence(self.fleet())
        self.assertEqual([x["match"] for x in result["configuredConsumers"]],
                         ["PATCHMON_REDIS", "OTHER_OR_UNRESOLVED"])
        self.assertFalse(result["safeToDetach"])

    def test_unhashable_fleet_identity_fails_closed(self):
        result = self.runtime()._redis_dependency_evidence(
            {"ok": True, "containers": [{"id": []}]})
        self.assertEqual(result["status"], "REDIS_DEPENDENCY_EVIDENCE_UNAVAILABLE")
        self.assertEqual(self.calls, [])

    def test_inspect_truncation_and_invalid_json_fail_closed(self):
        for raw in ("invalid", "x" * 500_000, json.dumps({"id": REDIS_ID})):
            calls = []
            def runner(argv, **kwargs):
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, raw, "")
            result = PatchmonOperatorRuntime(runner=runner)._redis_dependency_evidence(self.fleet())
            self.assertEqual(result["status"], "REDIS_DEPENDENCY_EVIDENCE_UNAVAILABLE")
            self.assertEqual(len(calls), 1)

    def test_malformed_inspect_shapes_fail_closed(self):
        for field, value in (("env", {}), ("networks", []), ("name", "/bad name"),
                             ("labels", [])):
            self.setUp()
            self.rows[0][field] = value
            result = self.runtime()._redis_dependency_evidence(self.fleet())
            self.assertEqual(result["status"], "REDIS_DEPENDENCY_EVIDENCE_UNAVAILABLE")



if __name__ == "__main__":
    unittest.main()
