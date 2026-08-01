from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]


def test_admin_recheck_reuses_the_canonical_revision_bound_receipt_producer() -> None:
    runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")
    ast.parse(runtime)

    recheck = runtime.split(
        "def admin_recheck_free_revolver_provider(source_id: str):",
        1,
    )[1].split(
        "def admin_update_free_revolver_provider(source_id: str):",
        1,
    )[0]

    assert '_FREELLM_RECEIPT_SCHEMA = "sovereign.freellm-route-receipt.v3"' in runtime
    assert '"generalChatEvidenceVerified": True' in runtime
    assert "textualChatResponseVerified" in runtime
    assert "result = activate_model(" in recheck
    assert '"runtimeIdentity": result.get("runtimeIdentity")' in recheck
    assert '"receiptId": result.get("receiptId")' in recheck
    assert '"receiptSha256": result.get("receiptSha256")' in recheck
    assert "discovery_payload_sha256" in recheck
    assert "eligibility_source" in recheck

    # Recheck must not maintain a second, partial receipt writer. The canonical
    # activate_model path owns canary execution, runtime identity and v3 chat-evidence hashing.
    assert "canary = _confirmed_completion_canary(" not in recheck
    assert "jsonb_set(" not in recheck
    assert "SET disabled=false" not in recheck
