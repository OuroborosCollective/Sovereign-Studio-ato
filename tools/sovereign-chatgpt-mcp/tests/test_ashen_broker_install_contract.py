"""Release contract: each imported Ashen module must reach the installed host broker and MCP image."""
import shlex
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class AshenHostInstallerContract(unittest.TestCase):
    def test_host_and_container_both_receive_ashen_adapter(self):
        installer = (ROOT / "deploy" / "install-on-vps.sh").read_text(encoding="utf-8")
        host_loops = [line for line in installer.splitlines()
                      if line.startswith("for file in broker.py ") and line.endswith("; do")]
        build_loops = [line for line in installer.splitlines()
                       if line.startswith("for file in Dockerfile ") and line.endswith("; do")]
        self.assertEqual(1, len(host_loops), "One canonical host broker install loop")
        self.assertEqual(1, len(build_loops), "One canonical container source install loop")
        self.assertIn("ashen_broker_adapter.py", host_loops[0].split())
        self.assertIn("ashen_broker_adapter.py", build_loops[0].split())
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        copy_lines = [line for line in dockerfile.splitlines()
                      if line.startswith("COPY ") and line.endswith(" /app/")]
        self.assertEqual(1, len(copy_lines))
        self.assertIn("ashen_broker_adapter.py", copy_lines[0].split())
        self.assertTrue((ROOT / "ashen_broker_adapter.py").is_file())

    def test_installer_preserves_only_the_existing_ashen_activation_pins(self):
        installer = (ROOT / "deploy" / "install-on-vps.sh").read_text(encoding="utf-8")
        environment_writer = installer.split('INSTALL_STAGE="write_broker_environment"', 1)[1]
        environment_writer = environment_writer.split('} > "$BROKER_ENV"; then', 1)[0]
        projection = next(line for line in environment_writer.splitlines()
                          if line.lstrip().startswith("grep -E "))
        grep, option, pattern, *_ = shlex.split(projection)
        pins = [
            "SOVEREIGN_MCP_ASHEN_SOURCE_ROOT=/var/lib/unityarpg/.local/share/are-arpg/ashen-source",
            "SOVEREIGN_MCP_ASHEN_SOURCE_SHA=" + "a" * 40,
            "SOVEREIGN_MCP_ASHEN_UNITY_SHA=" + "b" * 40,
            "SOVEREIGN_MCP_ASHEN_IMAGE_ID=sha256:" + "c" * 64,
        ]
        allowed_existing = "SOVEREIGN_MCP_PRIVATE_OWNER_MODE=1"
        result = subprocess.run(
            [grep, option, pattern],
            input="\n".join([*pins, allowed_existing, "SOVEREIGN_MCP_ASHEN_UNLISTED=fixture"]) + "\n",
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual([*pins, allowed_existing], result.stdout.splitlines())

if __name__ == "__main__":
    unittest.main()
