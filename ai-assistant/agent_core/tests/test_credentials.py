"""密码测试仅使用合成口令；不接真实身份或网络。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent_core.credentials import hash_password, verify_password


class CredentialsTests(unittest.TestCase):
    def test_salted_hash_and_verification(self):
        first = hash_password("synthetic password one")
        second = hash_password("synthetic password one")
        self.assertNotEqual(first, second)
        self.assertNotIn("synthetic password one", first)
        self.assertTrue(verify_password("synthetic password one", first))
        self.assertFalse(verify_password("different password", first))

    def test_malformed_hashes_fail_closed(self):
        for value in ("", "other$100000$YQ==$YQ==", "pbkdf2_sha256$999999999$YQ==$YQ==",
                      "pbkdf2_sha256$100000$%%%$%%%", None, "x" * 301):
            self.assertFalse(verify_password("synthetic", value))

    def test_invalid_password_fails_closed(self):
        for password in (None, "", "x" * 257):
            self.assertFalse(verify_password(password, "invalid"))
            with self.assertRaises(ValueError):
                hash_password(password)


if __name__ == "__main__":
    unittest.main()