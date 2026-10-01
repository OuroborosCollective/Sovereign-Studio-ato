from pathlib import Path
import importlib.util
import unittest
from unittest.mock import patch
import json
import tempfile
import os

import yaml


PATH = Path(__file__).resolve().parents[1] / "deploy" / "repair-auth-proxy-routing.py"
SPEC = importlib.util.spec_from_file_location("auth_proxy_routing_recovery", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
IMAGE = "sha256:" + "0" * 64
SOURCE = """services:
  sovereign-mcp-auth-proxy:
    image: sovereign-mcp-auth-proxy:candidate
    env_file:
      - ./proxy.env
    read_only: true
    networks:
      - mcp_public
      - mcp_broker_private
    labels:
      - traefik.enable=true
      - traefik.http.routers.sovereign-mcp.rule=Host(`arelogic.space`)
      - traefik.http.routers.sovereign-mcp.tls=true
networks:
  mcp_public:
    external: true
    name: areloria_arelorian-network
  mcp_broker_private:
    external: true
    name: sovereign-mcp-auth-internal
"""


class AuthProxyRecoveryTests(unittest.TestCase):
    def test_actual_renderer_preserves_auth_settings_and_attached_external_network(self):
        extra = {"mcp_routing_traefik_public": "traefik-public"}
        result = yaml.safe_load(MODULE.render(SOURCE, IMAGE, extra))
        service = result["services"][MODULE.SERVICE]
        self.assertEqual(service["env_file"], ["./proxy.env"])
        self.assertTrue(service["read_only"])
        self.assertEqual(service["image"], IMAGE)
        self.assertEqual(service["networks"], ["mcp_public", "mcp_broker_private", "mcp_routing_traefik_public"])
        self.assertEqual(result["networks"]["mcp_routing_traefik_public"], {"external": True, "name": "traefik-public"})
        self.assertIn(MODULE.ROUTER + "rule=" + MODULE.RULE, service["labels"])
        self.assertIn(MODULE.ROUTER + "priority=2000", service["labels"])

    def test_admin_root_discovery_and_game_routes_are_excluded(self):
        self.assertNotIn("/admin-mcp", MODULE.ROUTES)
        self.assertNotIn("/", MODULE.ROUTES)
        self.assertNotIn("/.well-known/oauth-protected-resource", MODULE.ROUTES)
        self.assertNotIn("/.well-known/openid-configuration", MODULE.ROUTES)
        self.assertNotIn("PathPrefix", MODULE.RULE)

    def test_already_repaired_source_is_idempotent(self):
        repaired = MODULE.render(SOURCE, IMAGE, {})
        self.assertEqual(MODULE.render(repaired, IMAGE, {}), repaired)

    def test_quoted_compose_labels_keep_valid_yaml(self):
        quoted = SOURCE.replace("- " + MODULE.ROUTER + "rule=" + MODULE.HOST_RULE,
                                '- "' + MODULE.ROUTER + "rule=" + MODULE.HOST_RULE + '"')
        parsed = yaml.safe_load(MODULE.render(quoted, IMAGE, {}))
        self.assertIn(MODULE.ROUTER + "rule=" + MODULE.RULE, parsed["services"][MODULE.SERVICE]["labels"])

    def test_stale_routing_or_image_inputs_are_refused(self):
        for source in (SOURCE.replace(MODULE.HOST_RULE, "Host(`other.example`)"),
                       SOURCE.replace("sovereign-mcp-auth-proxy:candidate", "unrelated:candidate"),
                       SOURCE + "\n      - " + MODULE.ROUTER + "rule=" + MODULE.HOST_RULE + "\n"):
            with self.assertRaises(ValueError):
                MODULE.render(source, IMAGE, {})

    def test_cross_scope_network_and_mutable_image_inputs_are_refused(self):
        with self.assertRaises(ValueError):
            MODULE.render(SOURCE, "unrelated:latest", {})
        with self.assertRaises(ValueError):
            MODULE.render(SOURCE, IMAGE, {"mcp_routing_unrelated": "unrelated-network"})

    def test_config_guard_refuses_unrelated_auth_or_port_changes(self):
        before = {"services": {MODULE.SERVICE: {
            "image": "sovereign-mcp-auth-proxy:candidate", "labels": {MODULE.ROUTER + "rule": MODULE.HOST_RULE},
            "networks": {"mcp_public": None}, "env_file": ["./proxy.env"],
        }}, "networks": {"mcp_public": {"name": "areloria_arelorian-network", "external": True}}}
        after = __import__("json").loads(__import__("json").dumps(before))
        after["services"][MODULE.SERVICE]["image"] = IMAGE
        after["services"][MODULE.SERVICE]["labels"].update({MODULE.ROUTER + "rule": MODULE.RULE, MODULE.ROUTER + "priority": "2000"})
        MODULE.verify_config(before, after, IMAGE, {})
        after["services"][MODULE.SERVICE]["ports"] = ["8090:8090"]
        with self.assertRaises(ValueError):
            MODULE.verify_config(before, after, IMAGE, {})

    def test_permission_denial_occurs_before_any_docker_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "docker-compose.yml"
            path.write_text(SOURCE)
            with patch.object(MODULE, "COMPOSE", path), patch.object(MODULE.os, "geteuid", return_value=10001), patch.object(MODULE, "run") as effect:
                with self.assertRaisesRegex(ValueError, "AUTHORITY_INVALID"):
                    MODULE.main()
                effect.assert_not_called()

    def test_external_alias_allows_only_empty_default_ipam_normalization(self):
        before = {"services": {MODULE.SERVICE: {"image": "sovereign-mcp-auth-proxy:candidate",
            "labels": {MODULE.ROUTER + "rule": MODULE.HOST_RULE}, "networks": {}}}, "networks": {}}
        alias = "mcp_routing_traefik_public"
        after = {"services": {MODULE.SERVICE: {"image": IMAGE,
            "labels": {MODULE.ROUTER + "rule": MODULE.RULE, MODULE.ROUTER + "priority": "2000"},
            "networks": {alias: None}}}, "networks": {alias: {"name": "traefik-public", "external": True, "ipam": {}}}}
        MODULE.verify_config(before, after, IMAGE, {alias: "traefik-public"})
        after["networks"][alias]["ipam"] = {"driver": "unapproved-driver"}
        with self.assertRaises(ValueError):
            MODULE.verify_config(before, after, IMAGE, {alias: "traefik-public"})

    def test_failed_recreation_restores_the_exact_compose_bytes(self):
        before = {"services": {MODULE.SERVICE: {
            "image": "sovereign-mcp-auth-proxy:candidate", "labels": {MODULE.ROUTER + "rule": MODULE.HOST_RULE},
            "networks": {"mcp_public": None, "mcp_broker_private": None}, "env_file": ["./proxy.env"],
        }}, "networks": {"mcp_public": {"name": "areloria_arelorian-network", "external": True},
                          "mcp_broker_private": {"name": "sovereign-mcp-auth-internal", "external": True}}}
        after = json.loads(json.dumps(before))
        after["services"][MODULE.SERVICE]["image"] = IMAGE
        after["services"][MODULE.SERVICE]["labels"].update({MODULE.ROUTER + "rule": MODULE.RULE, MODULE.ROUTER + "priority": "2000"})
        up_calls = []
        def external_command(argv, timeout=60):
            if argv[:3] == ["docker", "image", "inspect"]:
                return json.dumps([{"Id": IMAGE}])
            up_calls.append(argv)
            if len(up_calls) == 1:
                raise RuntimeError("COMMAND_FAILED:synthetic-test-diagnostic")
            return ""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "docker-compose.yml"
            path.write_bytes(SOURCE.encode())
            actual_stat = Path.stat
            def root_backup_directory_stat(target, *args, **kwargs):
                stat = actual_stat(target, *args, **kwargs)
                if target.name == "routing-recovery-backups":
                    fields = list(stat)
                    fields[4] = 0
                    return os.stat_result(fields)
                return stat
            previous = {"Image": IMAGE, "Config": {"Labels": {
                "com.docker.compose.project": MODULE.PROJECT,
                "com.docker.compose.project.config_files": str(path),
            }}, "NetworkSettings": {"Networks": {"areloria_arelorian-network": {}, "sovereign-mcp-auth-internal": {}}}}
            with patch.object(MODULE, "COMPOSE", path), patch.object(MODULE.os, "geteuid", return_value=0), patch.object(Path, "stat", root_backup_directory_stat), patch.object(MODULE, "inspect", return_value=previous), patch.object(MODULE, "compose_config", side_effect=[before, after]), patch.object(MODULE, "public_metadata", return_value={"resource": "https://arelogic.space/admin-mcp"}), patch.object(MODULE, "run", side_effect=external_command):
                with self.assertRaises(RuntimeError):
                    MODULE.main()
            self.assertEqual(path.read_bytes(), SOURCE.encode())
            self.assertEqual(len(up_calls), 2)
            self.assertEqual(len(list((path.parent / "routing-recovery-backups").glob("*.yml"))), 1)


if __name__ == "__main__":
    unittest.main()
