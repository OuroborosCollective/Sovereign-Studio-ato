import unittest
from backend.agent_runtime.contracts import sanitize_agent_text

class TestSecurityMasking(unittest.TestCase):
    def test_github_token_masking(self):
        tokens = [
            "ghp_1234567890abcdefghijklmnopqrstuvwxyz",
            "gho_1234567890abcdefghijklmnopqrstuvwxyz",
            "ghu_1234567890abcdefghijklmnopqrstuvwxyz",
            "ghs_1234567890abcdefghijklmnopqrstuvwxyz",
            "ghr_1234567890abcdefghijklmnopqrstuvwxyz",
            "github_pat_1234567890abcdefghijklmnopqrstuvwxyz1234567890abcdef",
        ]
        for token in tokens:
            if token.startswith("github_pat_"):
                prefix = "github_pat_"
            else:
                prefix = token.split("_")[0] + "_"
            self.assertEqual(sanitize_agent_text(token), f"{prefix}[redacted]")

    def test_ai_provider_key_masking(self):
        keys = {
            "sk-or-v1-1234567890abcdefghijklmnopqrstuvwxyz": "sk-or-v1-[redacted]",
            "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz": "sk-proj-[redacted]",
            "sk-ant-1234567890abcdefghijklmnopqrstuvwxyz": "sk-ant-[redacted]",
            "sk-1234567890abcdefghijklmnopqrstuvwxyz": "sk-[redacted]",
            "gsk_1234567890abcdefghijklmnopqrstuvwxyz": "gsk_[redacted]",
            "hf_1234567890abcdefghijklmnopqrstuvwxyz": "hf_[redacted]",
            "together_1234567890abcdefghijklmnopqrstuvwxyz": "together_[redacted]",
            "pollinations_1234567890abcdefghijklmnopqrstuvwxyz": "pollinations_[redacted]",
            "AIza1234567890abcdefghijklmnopqrstuvwxyz12345": "AIza[redacted]",
        }
        for key, expected in keys.items():
            self.assertEqual(sanitize_agent_text(key), expected)

    def test_bearer_token_masking(self):
        texts = {
            "Bearer 1234567890abcdef": "Bearer [redacted]",
            "Authorization: Bearer 1234567890abcdef": "Authorization: Bearer [redacted]",
        }
        for text, expected in texts.items():
            self.assertEqual(sanitize_agent_text(text), expected)

    def test_label_based_masking(self):
        labels = [
            "password=mysecret",
            "token: mysecret",
            "api_key = mysecret",
            "'secret': 'mysecret'",
            "\"access_token\": \"mysecret\"",
        ]
        for label in labels:
            self.assertIn("[redacted]", sanitize_agent_text(label))
            # Verify prefix is preserved
            prefix = label.split("mysecret")[0]
            self.assertEqual(sanitize_agent_text(label), f"{prefix}[redacted]")

    def test_mixed_content_masking(self):
        mixed = "Error: Invalid API key sk-1234567890abcdefghijklmnopqrstuvwxyz for user test@example.com"
        expected = "Error: Invalid API key sk-[redacted] for user test@example.com"
        self.assertEqual(sanitize_agent_text(mixed), expected)

if __name__ == "__main__":
    unittest.main()
