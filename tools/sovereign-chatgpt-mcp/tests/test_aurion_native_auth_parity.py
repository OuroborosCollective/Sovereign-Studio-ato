import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
MCP = ROOT / "tools/sovereign-chatgpt-mcp"


class ParityContracts(unittest.TestCase):
    def test_canonical_backend_mirrors(self):
        for name in ("aurion_native_auth.py", "command_contract.py", "command_queue.py", "owner_ssh_console.py"):
            with self.subTest(name=name):
                self.assertEqual((MCP / name).read_bytes(), (ROOT / "scripts/sovereign-backend" / name).read_bytes())

    def test_host_modules_staged_by_existing_installer(self):
        installer = (MCP / "deploy/install-on-vps.sh").read_text()
        loops = [line for line in installer.splitlines() if line.startswith("for file in ") and ("broker.py" in line or "Dockerfile requirements.txt" in line)]
        self.assertEqual(len(loops), 2)
        for name in ("aurion_native_auth.py", "aurion_native_auth_host.py"):
            self.assertIn(name, (MCP / "Dockerfile").read_text())
            for line in loops:
                self.assertIn(name, line)

    def test_exactly_one_new_mutation_contract(self):
        tree = ast.parse((MCP / "command_contract.py").read_text())
        actions = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith("aurion_native_auth_")}
        self.assertEqual(actions, {"aurion_native_auth_apply"})


if __name__ == "__main__":
    unittest.main()
