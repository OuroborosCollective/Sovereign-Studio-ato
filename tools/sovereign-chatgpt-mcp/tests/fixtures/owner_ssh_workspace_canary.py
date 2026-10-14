import hashlib, json, os, pathlib, resource, socket, subprocess, sys, unittest
class WorkspaceCanary(unittest.TestCase):
    def test_identity(self):
        self.assertEqual((os.getuid(), os.getgid()), (65534, 65534))
        self.assertEqual(os.getcwd(), "/workspace")
    def test_host_paths_hidden(self):
        for p in ("/root", "/home", "/opt", "/run/docker.sock", "/var/run/docker.sock", "/etc/shadow"):
            self.assertFalse(os.path.exists(p), p)
    def test_network_namespace(self):
        self.assertEqual([name for _, name in socket.if_nameindex()], ["lo"])
    def test_read_only_runtime(self):
        with self.assertRaises(OSError):
            pathlib.Path("/usr/bin/.sovereign-canary").write_text("denied")
    def test_environment(self):
        self.assertEqual(os.environ["HOME"], "/tmp")
        self.assertFalse(any("TOKEN" in k or "PASSWORD" in k or "SECRET" in k for k in os.environ))
    def test_process_limits(self):
        self.assertEqual(resource.getrlimit(resource.RLIMIT_NOFILE)[0], 256)
        self.assertEqual(resource.getrlimit(resource.RLIMIT_CORE)[0], 0)
        self.assertEqual(resource.getrlimit(resource.RLIMIT_FSIZE)[0], 1073741824)
    def test_child_identity(self):
        r = subprocess.run([sys.executable, "-c", "import os; print(os.getuid())"], capture_output=True, text=True, timeout=3)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "65534"))
    def test_persisted_effect(self):
        p = pathlib.Path("runtime-evidence.txt")
        data = b"vps-workspace-runtime-verified-20261014\n"
        p.write_bytes(data)
        self.assertEqual(p.read_bytes(), data)
if __name__ == "__main__":
    unittest.main(verbosity=2)
