"""Release contract: every imported broker module must be staged on the host."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class AshenHostInstallerContract(unittest.TestCase):
    def test_broker_installer_stages_ashen_read_only_adapter(self):
        installer = (ROOT / "deploy" / "install-on-vps.sh").read_text(encoding="utf-8")
        lines = re.findall(r"^for file in broker\\.py [^\\n]+; do$", installer, flags=re.MULTILINE)
        self.assertEqual(1, len(lines), "A single canonical host-broker install loop is required")
        self.assertIn("ashen_broker_adapter.py", lines[0].split(),
                      "Without this file, broker.py fails on live import after deployment")
        self.assertTrue((ROOT / "ashen_broker_adapter.py").is_file())

if __name__ == "__main__":
    unittest.main()
