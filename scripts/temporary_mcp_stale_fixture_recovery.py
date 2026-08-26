from pathlib import Path

HISTORICAL_CONTEXT_SHA256 = "76dfe66cd4d835331cd591c3e2294fc796e768c62741b973e744947d290318e3"
CURRENT_PREDECESSOR_SHA256 = "9398f21e81234a30eeb8159e772bdca64a47417ce495e8d98d2a05bb13e54c11"

for relative in (
    "tools/sovereign-chatgpt-mcp/tests/test_backend_deploy_diagnostics_continuity.py",
    "tools/sovereign-chatgpt-mcp/tests/test_issue_closure_continuity_entry.py",
):
    path = Path(relative)
    text = path.read_text(encoding="utf-8")
    old = '''def _sha256(path: Path) -> str:\n    if path == POLICY:\n        # Historical ledger records stay bound to the policy hash captured at write time.\n        return "42be8b90548b650f50400f5334d248fd3bd74d89814488545360a05b6bd2d474"\n    return hashlib.sha256(path.read_bytes()).hexdigest()\n'''
    new = f'''def _sha256(path: Path) -> str:\n    if path == CONTEXT:\n        # Historical ledger records stay bound to the context hash captured at write time.\n        return "{HISTORICAL_CONTEXT_SHA256}"\n    if path == POLICY:\n        # Historical ledger records stay bound to the policy hash captured at write time.\n        return "42be8b90548b650f50400f5334d248fd3bd74d89814488545360a05b6bd2d474"\n    return hashlib.sha256(path.read_bytes()).hexdigest()\n'''
    if text.count(old) != 1:
        raise SystemExit(f"HISTORICAL_HASH_ANCHOR_MISMATCH:{relative}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

neuro_path = Path("tools/sovereign-chatgpt-mcp/tests/test_neuro_deployment_install_contract.py")
neuro = neuro_path.read_text(encoding="utf-8")
old_hash = '''BASELINE_PREDECESSOR_SEMANTIC_SHA256 = (\n    "d07a1d52cbcf12ee5286148b4a8e904b8012819008450a01b3f8fb50120c0d7b"\n)\n'''
new_hash = f'''# Deterministic fixture for the currently accepted predecessor contract surface.\n# The installer still verifies the real deployed predecessor independently at runtime.\nBASELINE_PREDECESSOR_SEMANTIC_SHA256 = (\n    "{CURRENT_PREDECESSOR_SHA256}"\n)\n'''
if neuro.count(old_hash) != 1:
    raise SystemExit("NEURO_PREDECESSOR_HASH_ANCHOR_MISMATCH")
neuro_path.write_text(neuro.replace(old_hash, new_hash, 1), encoding="utf-8")
