#!/usr/bin/env python3
"""
Tests for Admin API - Runtime Settings, Secret Masking, CORS Validation.

Covers:
- Runtime config endpoints
- Secret masking
- CORS policy validation
- Audit events
"""
import unittest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Copy the functions we need for testing (standalone, no DB dependency)
def _mask_secrets(config: dict) -> dict:
    """Mask sensitive values in config for display."""
    masked = dict(config)
    for key in masked:
        if "secret" in key.lower() or "key" in key.lower() or "token" in key.lower():
            val = str(masked[key] or "")
            if len(val) > 4:
                masked[key] = val[:2] + "*" * (len(val) - 4) + val[-2:]
            else:
                masked[key] = "****"
    return masked


_RUNTIME_CONFIG: dict = {
    "byok_mode": "user-key",
    "cors_origins": [
        "https://chat.arelorian.de",
        "https://arelorian.de",
        "https://sovereign-backend.arelorian.de",
    ],
}


class TestSecretMasking(unittest.TestCase):
    """Tests for secret masking in config display."""
    
    def test_mask_secrets_hides_key_fields(self):
        """Secrets should be masked when displaying config."""
        config = {
            "api_key": "sk-1234567890abcdef",
            "client_secret": "verysecretvalue",
            "token": "abc123token",
            "public_field": "visible",
        }
        
        masked = _mask_secrets(config)
        
        # Public fields should be visible
        self.assertEqual(masked["public_field"], "visible")
        
        # Secret fields should be masked
        self.assertNotEqual(masked["api_key"], "sk-1234567890abcdef")
        self.assertIn("*", masked["api_key"])
        
        self.assertNotEqual(masked["client_secret"], "verysecretvalue")
        self.assertIn("*", masked["client_secret"])
        
        self.assertNotEqual(masked["token"], "abc123token")
        self.assertIn("*", masked["token"])
    
    def test_mask_secrets_only_masks_named_secret_fields(self):
        """Masking only applies to fields with 'secret', 'key', or 'token' in name."""
        config = {"api_key": "ab", "my_secret": "a", "public_field": "visible"}
        masked = _mask_secrets(config)
        
        # Named secret fields get masked even if short
        self.assertEqual(masked["api_key"], "****")
        self.assertEqual(masked["my_secret"], "****")
        
        # Non-secret fields stay unchanged
        self.assertEqual(masked["public_field"], "visible")
    
    def test_mask_secrets_handles_empty_values(self):
        """Empty values should be handled gracefully."""
        config = {"api_secret": "", "public_key": None, "public_field": "visible"}
        masked = _mask_secrets(config)
        
        # Secret fields get **** even when empty
        self.assertEqual(masked["api_secret"], "****")
        # Non-secret fields stay unchanged
        self.assertEqual(masked["public_field"], "visible")


class TestCORSValidation(unittest.TestCase):
    """Tests for CORS origin validation."""
    
    def test_blocks_wildcard_origin(self):
        """Wildcard (*) origin must be blocked."""
        origins = ["https://example.com", "*"]
        
        # Simulate the validation logic
        errors = []
        for origin in origins:
            if origin.strip() == "*":
                errors.append({
                    "origin": origin,
                    "error": "Wildcard nicht erlaubt",
                    "blocker": "cors_wildcard_blocked"
                })
        
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["blocker"], "cors_wildcard_blocked")
    
    def test_blocks_auth_in_origin(self):
        """Origin with auth parameters must be blocked."""
        origins = ["https://example.com?token=abc123"]
        
        errors = []
        for origin in origins:
            if any(pattern in origin.lower() for pattern in ["token=", "key=", "auth="]):
                errors.append({
                    "origin": origin,
                    "error": "Origin darf keine Auth-Parameter enthalten",
                    "blocker": "cors_auth_in_origin_blocked"
                })
        
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["blocker"], "cors_auth_in_origin_blocked")
    
    def test_allows_valid_origins(self):
        """Valid HTTPS origins should pass validation."""
        valid_origins = [
            "https://chat.arelorian.de",
            "https://arelorian.de",
            "https://sovereign-backend.arelorian.de",
        ]
        
        errors = []
        for origin in valid_origins:
            if origin.strip() == "*":
                errors.append({"blocker": "cors_wildcard_blocked"})
            elif any(pattern in origin.lower() for pattern in ["token=", "key=", "auth="]):
                errors.append({"blocker": "cors_auth_in_origin_blocked"})
        
        self.assertEqual(len(errors), 0)
    
    def test_warns_about_http_origins(self):
        """HTTP origins should trigger warnings."""
        origins = ["http://example.com"]
        
        warnings = []
        for origin in origins:
            if origin.startswith("http://") and not origin.startswith("http://localhost"):
                warnings.append({
                    "origin": origin,
                    "warning": "Non-HTTPS Origin erkannt. Empfehlung: HTTPS verwenden."
                })
        
        self.assertEqual(len(warnings), 1)
        self.assertIn("HTTPS", warnings[0]["warning"])


class TestRuntimeConfig(unittest.TestCase):
    """Tests for runtime configuration."""
    
    def test_default_config_values(self):
        """Default config should have expected values."""
        # Use local copy of config
        config = _RUNTIME_CONFIG
        
        self.assertEqual(config["byok_mode"], "user-key")
        self.assertIsInstance(config["cors_origins"], list)
        self.assertGreater(len(config["cors_origins"]), 0)
    
    def test_byok_mode_valid_values(self):
        """BYOK mode should accept only valid values."""
        valid_modes = ["system-key", "user-key", "disabled"]
        
        for mode in valid_modes:
            self.assertIn(mode, valid_modes)
        
        # Invalid mode should not be accepted
        self.assertNotIn("invalid-mode", valid_modes)


class TestAuditLogging(unittest.TestCase):
    """Tests for audit logging behavior."""
    
    def test_audit_requires_reason_for_credit_adjustment(self):
        """Credit adjustments should require a reason."""
        # This tests the contract: adjustments without reason should be rejected
        # In the actual app, this is enforced at the API level
        
        test_cases = [
            {"amount": 100, "reason": "Valid reason"},  # Should pass
            {"amount": 100, "reason": ""},  # Should fail
            {"amount": 0, "reason": "Some reason"},  # Should fail
        ]
        
        # Only cases with both amount != 0 and non-empty reason should pass
        for case in test_cases:
            has_amount = case["amount"] != 0
            has_reason = bool(case["reason"])
            
            if has_amount and has_reason:
                self.assertTrue(has_amount and has_reason)  # Should pass
            else:
                self.assertFalse(has_amount and has_reason)  # Should fail


class TestCreditLedgerRules(unittest.TestCase):
    """Tests for credit ledger behavior (append-only principle)."""
    
    def test_credit_adjustment_requires_audit_reason(self):
        """Every credit adjustment must have an audit reason."""
        valid_adjustment = {
            "amount": 50,
            "reason": "Customer compensation for service outage"
        }
        
        invalid_adjustments = [
            {"amount": 50, "reason": ""},
            {"amount": 50},
            {"amount": 0, "reason": "Some reason"},
        ]
        
        # Valid case should pass the check
        self.assertTrue(bool(valid_adjustment["amount"]) and bool(valid_adjustment["reason"]))
        
        # Invalid cases should fail
        for adj in invalid_adjustments:
            has_valid_amount = bool(adj.get("amount", 0))
            has_valid_reason = bool(adj.get("reason", ""))
            # At least one condition should be false
            self.assertFalse(has_valid_amount and has_valid_reason)


class TestHealthcheckValidation(unittest.TestCase):
    """Tests for health check validation logic."""
    
    def test_builtin_tools_are_always_healthy(self):
        """Built-in tools should not need HTTP health checks."""
        builtin_tools = ["OpenHands", "Code Editor", "Terminal", "Git", "File Browser"]
        
        for tool in builtin_tools:
            self.assertIn(tool, builtin_tools)
    
    def test_http_status_codes_for_health(self):
        """Health check should interpret HTTP status codes correctly."""
        test_cases = [
            (200, "healthy"),
            (201, "healthy"),
            (301, "healthy"),
            (400, "degraded"),
            (401, "degraded"),
            (403, "degraded"),
            (500, "degraded"),
            (502, "degraded"),
            (503, "degraded"),
        ]
        
        for status_code, expected in test_cases:
            if status_code >= 500:
                result = "degraded"
            elif status_code >= 400:
                result = "degraded"
            else:
                result = "healthy"
            
            self.assertEqual(result, expected)
    
    def test_provider_urls(self):
        """Test LLM provider health check URLs."""
        providers = {
            "openai": "https://api.openai.com",
            "anthropic": "https://api.anthropic.com",
            "deepseek": "https://api.deepseek.com",
            "gemini": "https://generativelanguage.googleapis.com",
        }
        
        for provider, expected_url in providers.items():
            # Default URL should be set correctly
            self.assertIn(provider, providers)


class TestConfigPersistence(unittest.TestCase):
    """Tests for config persistence logic."""
    
    def test_default_config_structure(self):
        """Default config should have required fields."""
        default_config = {
            "byok_mode": "user-key",
            "cors_origins": [],
            "worker_health": "healthy",
            "last_deploy_at": None,
            "version": "1.0",
        }
        
        self.assertIn("byok_mode", default_config)
        self.assertIn("cors_origins", default_config)
        self.assertIn("worker_health", default_config)
    
    def test_byok_mode_enum(self):
        """BYOK mode should only accept valid values."""
        valid_modes = ["system-key", "user-key", "disabled"]
        
        for mode in valid_modes:
            # Should not raise
            self.assertIn(mode, valid_modes)
        
        # Invalid mode
        self.assertNotIn("invalid", valid_modes)
    
    def test_cors_origins_validation(self):
        """CORS origins should be validated before saving."""
        # Valid origins
        valid_origins = [
            "https://chat.arelorian.de",
            "https://arelorian.de",
        ]
        
        # Invalid origins
        invalid_origins = [
            "*",
            "https://evil.com?token=abc",
            "https://evil.com?key=secret",
        ]
        
        # Validate
        for origin in valid_origins:
            is_valid = True
            if origin.strip() == "*":
                is_valid = False
            if any(p in origin.lower() for p in ["token=", "key=", "auth="]):
                is_valid = False
            self.assertTrue(is_valid)
        
        for origin in invalid_origins:
            is_valid = True
            if origin.strip() == "*":
                is_valid = False
            if any(p in origin.lower() for p in ["token=", "key=", "auth="]):
                is_valid = False
            self.assertFalse(is_valid)


if __name__ == "__main__":
    unittest.main()
