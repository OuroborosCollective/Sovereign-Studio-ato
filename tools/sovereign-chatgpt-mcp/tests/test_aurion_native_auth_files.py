"""Stdlib regression tests. Synthetic files are not live-runtime evidence."""
import base64
import os
from pathlib import Path
import secrets
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aurion_native_auth as repair


class EnvContracts(unittest.TestCase):
    def test_generate_canonical_key_and_preserve_other_bytes(self):
        original = b"# retained comment\nDATABASE_URL='synthetic-not-a-credential'\n"
        result = repair.repaired_env(original, generate_key=True)
        self.assertTrue(result.startswith(original))
        self.assertEqual(repair.configuration(result), {
            "releaseEnabled": True, "stateSealKeyPresent": True, "stateSealKeyValid": True})
        value = repair.parse_env(result)[repair.SEAL]
        self.assertEqual(len(value), 43)
        self.assertEqual(len(base64.urlsafe_b64decode(value + "=")), 32)

    def test_reuse_key_without_entropy_call(self):
        original = repair.repaired_env(b"", generate_key=True)
        with patch.object(repair.secrets, "token_bytes", side_effect=AssertionError("rotation")):
            self.assertEqual(repair.repaired_env(original, generate_key=False), original)

    def test_generation_requires_exact_approval(self):
        for approval in (False, None, 1, "true"):
            with self.subTest(approval=approval), self.assertRaisesRegex(
                    repair.RepairBlocked, "KEY_GENERATION_NOT_APPROVED"):
                repair.repaired_env(b"", generate_key=approval)

    def test_new_key_plan_cannot_rotate_existing_key(self):
        original = repair.repaired_env(b"", generate_key=True)
        with self.assertRaisesRegex(repair.RepairBlocked, "KEY_GENERATION_PLAN_DRIFT"):
            repair.repaired_env(original, generate_key=True)

    def test_duplicate_any_variable_blocks(self):
        for name in (repair.SEAL, repair.RELEASE, "DATABASE_URL", "AURION_ENV_FILE"):
            with self.subTest(name=name), self.assertRaisesRegex(repair.RepairBlocked, "ENV_DUPLICATE"):
                repair.parse_env((name + "=\n" + name + "=\n").encode())

    def test_ambiguous_shell_forms_block(self):
        for raw in (b"export A=B\n", b" A=B\n", b"A=${B}\n", b"A=`id`\n",
                    b"A=hello world\n", b"A=foo#comment\n", b"A='unterminated\n",
                    b"A=foo\r\n", b"A=\x00\n", b"A=\xff\n", b"A=foo\\bar\n"):
            with self.subTest(raw=raw), self.assertRaises(repair.RepairBlocked):
                repair.parse_env(raw)

    def test_existing_invalid_key_is_not_replaced(self):
        with self.assertRaisesRegex(repair.RepairBlocked, "EXISTING_KEY_INVALID"):
            repair.repaired_env((repair.SEAL + "=synthetic-invalid-key\n").encode(), generate_key=True)

    def test_noncanonical_base64_rejected(self):
        key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        # The last two bits are padding; alter them without changing decoded bytes.
        noncanonical = key[:-1] + alphabet[alphabet.index(key[-1]) + 1]
        self.assertFalse(repair.valid_key(noncanonical))
        self.assertFalse(repair.valid_key(key + "="))
        self.assertFalse(repair.valid_key("synthetic-invalid-key"))

    def test_release_flag_is_exact(self):
        for value in ("TRUE", "1", "yes", "false", ""):
            self.assertFalse(repair.configuration((repair.RELEASE + "=" + value).encode())["releaseEnabled"])

    def test_secret_never_in_snapshot_repr_or_configuration(self):
        raw = repair.repaired_env(b"", generate_key=True)
        secret = repair.parse_env(raw)[repair.SEAL]
        snapshot = repair.ProtectedSnapshot(raw, 1, 2, 0, 0, 0o600, 3, 4)
        self.assertNotIn(secret, repr(snapshot))
        self.assertNotIn(secret, str(snapshot.identity()))
        self.assertNotIn(secret, str(repair.configuration(raw)))

    def test_error_contains_no_input(self):
        marker = "synthetic-private-value"
        try:
            repair.repaired_env((repair.SEAL + "=" + marker).encode(), generate_key=True)
        except repair.RepairBlocked as exc:
            self.assertNotIn(marker, str(exc))
        else:
            self.fail("invalid key accepted")


class FilesystemContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.file = self.root / "config"
        self.file.write_bytes(b"OTHER=synthetic\n")
        self.file.chmod(0o600)

    def tearDown(self):
        os.close(self.fd)
        self.temporary.cleanup()

    def root_metadata(self):
        # Only the OS ownership adapter is simulated; real open/read/rename,
        # symlinks, content and inode checks remain exercised on temporary files.
        original = os.fstat
        def fstat(fd):
            result = original(fd)
            class Metadata:
                pass
            proxy = Metadata()
            for name in dir(result):
                if name.startswith("st_"):
                    setattr(proxy, name, getattr(result, name))
            proxy.st_uid = proxy.st_gid = 0
            return proxy
        return patch.object(repair.os, "fstat", side_effect=fstat)

    def test_real_nonroot_file_rejected(self):
        if os.getuid() == 0:
            self.skipTest("requires a nonroot runner")
        with self.assertRaisesRegex(repair.RepairBlocked, "FILE_PROTECTION"):
            repair.read_protected(self.fd, "config")

    def test_atomic_replace_and_independent_readback(self):
        with self.root_metadata():
            before = repair.read_protected(self.fd, "config")
            result = repair.atomic_replace(self.fd, "config", before, b"OTHER=changed\n")
            self.assertEqual(result.raw, self.file.read_bytes())
            self.assertNotEqual(result.inode, before.inode)
            self.assertEqual(result.mode, 0o600)

    def test_stale_content_rejected(self):
        with self.root_metadata():
            before = repair.read_protected(self.fd, "config")
            self.file.write_bytes(b"OTHER=concurrent\n")
            with self.assertRaisesRegex(repair.RepairBlocked, "FILE_DRIFT"):
                repair.atomic_replace(self.fd, "config", before, b"OTHER=wrong\n")
        self.assertEqual(self.file.read_bytes(), b"OTHER=concurrent\n")
        self.assertEqual([p.name for p in self.root.iterdir()], ["config"])

    def test_symlink_swap_never_changes_target(self):
        with self.root_metadata():
            before = repair.read_protected(self.fd, "config")
            other = self.root / "other"
            other.write_bytes(b"untouched")
            self.file.unlink()
            self.file.symlink_to(other)
            with self.assertRaisesRegex(repair.RepairBlocked, "FILE_UNAVAILABLE"):
                repair.atomic_replace(self.fd, "config", before, b"wrong")
        self.assertEqual(other.read_bytes(), b"untouched")
        self.assertTrue(self.file.is_symlink())

    def test_inode_swap_with_identical_content_rejected(self):
        with self.root_metadata():
            before = repair.read_protected(self.fd, "config")
            replacement = self.root / "replacement"
            replacement.write_bytes(before.raw)
            replacement.chmod(0o600)
            replacement.replace(self.file)
            with self.assertRaisesRegex(repair.RepairBlocked, "FILE_DRIFT"):
                repair.atomic_replace(self.fd, "config", before, b"wrong")

    def test_bad_mode_and_hardlink_rejected(self):
        with self.root_metadata():
            self.file.chmod(0o644)
            with self.assertRaisesRegex(repair.RepairBlocked, "FILE_PROTECTION"):
                repair.read_protected(self.fd, "config")
            self.file.chmod(0o600)
            os.link(self.file, self.root / "alias")
            with self.assertRaisesRegex(repair.RepairBlocked, "FILE_PROTECTION"):
                repair.read_protected(self.fd, "config")

    def test_names_cannot_escape_directory(self):
        for name in ("..", "../config", "/etc/passwd", "", "."):
            with self.subTest(name=name), self.assertRaisesRegex(repair.RepairBlocked, "FILE_NAME"):
                repair.read_protected(self.fd, name)


if __name__ == "__main__":
    unittest.main()
