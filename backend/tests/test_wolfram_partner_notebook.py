from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime import wolfram_blockchain_readback as blockchain
from agent_runtime import wolfram_cag_partner_ledger as ledger
from agent_runtime import wolfram_partner_notebook as notebook


class _Symbol:
    def __init__(self, name: str):
        self.name = name

    def __call__(self, *args):
        return ("CALL", self.name, args)

    def __repr__(self):
        return f"Symbol({self.name})"


class _WL:
    def __getattr__(self, name: str):
        return _Symbol(name)


class _Session:
    def __init__(self, *, expected: str = "a" * 64, observed: str | None = None, result: str = "<|\"Blocks\" -> 1|>"):
        self.expected = expected
        self.observed = observed if observed is not None else expected
        self.result = result
        self.started = False
        self.terminated = False
        self.deploy_calls = 0

    def start(self):
        self.started = True

    def authorized(self):
        return True

    def evaluate(self, expr):
        assert expr[0] == "CALL"
        name = expr[1]
        args = expr[2]
        if name == "Hash":
            hashed = args[0]
            if isinstance(hashed, tuple) and len(hashed) > 1 and hashed[1] == "CloudGet":
                return self.observed
            return self.expected
        if name == "CloudDeploy":
            self.deploy_calls += 1
            rendered = repr(expr)
            assert "Permissions" in rendered
            assert "Private" in rendered
            return "CloudObject"
        if name == "ToString":
            return self.result
        raise AssertionError(f"unexpected expression {name}")

    def terminate(self):
        self.terminated = True


def _pack():
    record = ledger.build_partner_analysis_record(
        component="WolframLanguageComputation",
        normalized_question='{"code":"2+2"}',
        normalized_input_sha256="1" * 64,
        provider_response_sha256="2" * 64,
        credential_fingerprint_sha256="3" * 64,
        verdict="INCONCLUSIVE",
        derived_conclusion="Transport evidence only.",
        documentation_class="PARTNER_REPORTABLE",
        limitations=["No identity inference."],
        source_refs=["wolfram-official-cag-v1-contract"],
    )
    return ledger.build_partner_handoff_pack([record])


def test_notebook_projection_is_deterministic_and_partner_safe():
    pack = _pack()
    first = notebook.build_partner_notebook_projection(pack)
    second = notebook.build_partner_notebook_projection(dict(reversed(list(pack.items()))))
    assert first["notebookProjectionSha256"] == second["notebookProjectionSha256"]
    assert first["sourcePackSha256"] == pack["packSha256"]
    assert "credentialFingerprintSha256" not in repr(first)
    assert "cannot identify Satoshi Nakamoto" in first["researchBoundary"]["identityNotice"]


def test_notebook_projection_rejects_secret_shaped_material():
    pack = _pack()
    pack["analyses"][0]["Authorization"] = "Bearer abcdefghijklmnop"
    with pytest.raises(ledger.PartnerAnalysisError):
        notebook.build_partner_notebook_projection(pack)


def test_notebook_path_is_fixed_relative_and_rejects_traversal(monkeypatch):
    monkeypatch.setenv("WOLFRAM_PARTNER_NOTEBOOK_PATH", "Sovereign/Wolfram-CAG/Partner-Analysis.nb")
    assert notebook._selected_notebook_path().endswith("Partner-Analysis.nb")
    monkeypatch.setenv("WOLFRAM_PARTNER_NOTEBOOK_PATH", "../escape.nb")
    with pytest.raises(notebook.WolframCloudNotebookError) as exc:
        notebook._selected_notebook_path()
    assert exc.value.family == "NOTEBOOK_PATH"


def test_private_notebook_sync_requires_exact_hash_readback(monkeypatch):
    monkeypatch.setattr(notebook, "_cloud_credentials", lambda: ("consumer-key-value", "consumer-secret-value"))
    session = _Session()
    captured = {}

    def credentials_factory(key, secret):
        captured["key"] = key
        captured["secret"] = secret
        return object()

    result = notebook.sync_partner_notebook(
        _pack(),
        session_factory=lambda credentials: session,
        credentials_factory=credentials_factory,
        wl_factory=_WL(),
    )
    assert result["status"] == "WOLFRAM_CLOUD_NOTEBOOK_SYNC_VERIFIED"
    assert result["notebookExpressionSha256"] == result["cloudReadbackSha256"]
    assert result["permissions"] == "Private"
    assert result["secretValuesReturned"] is False
    assert session.deploy_calls == 1
    assert session.terminated is True
    assert "consumer-key-value" not in repr(result)
    assert "consumer-secret-value" not in repr(result)
    assert captured == {"key": "consumer-key-value", "secret": "consumer-secret-value"}


def test_private_notebook_sync_fails_closed_on_hash_mismatch(monkeypatch):
    monkeypatch.setattr(notebook, "_cloud_credentials", lambda: ("key", "secret"))
    session = _Session(expected="a" * 64, observed="b" * 64)
    with pytest.raises(notebook.WolframCloudNotebookError) as exc:
        notebook.sync_partner_notebook(
            _pack(),
            session_factory=lambda credentials: session,
            credentials_factory=lambda key, secret: object(),
            wl_factory=_WL(),
        )
    assert exc.value.family == "CLOUD_READBACK"
    assert session.terminated is True


def test_bitcoin_readback_is_allowlisted_read_only_and_hashed(monkeypatch):
    monkeypatch.setattr(blockchain, "_cloud_credentials", lambda: ("key", "secret"))
    session = _Session(result='{489059, "tx", 100}')
    txid = "c18ff55d09c596ffbad30321719171c0d5b4d677d3554fc6ab3d12167ea8b9d6"
    result = blockchain.run_bitcoin_readback(
        operation="transaction",
        identifier=txid,
        properties=["BlockNumber", "Confirmations", "TotalOutput"],
        session_factory=lambda credentials: session,
        credentials_factory=lambda key, secret: object(),
        wl_factory=_WL(),
    )
    assert result["status"] == "WOLFRAM_BITCOIN_READBACK_SUCCEEDED"
    assert result["network"] == "Bitcoin-Mainnet"
    assert result["operation"] == "transaction"
    assert result["readOnly"] is True
    assert result["transactionMutationAvailable"] is False
    assert len(result["resultSha256"]) == 64
    assert session.terminated is True


def test_bitcoin_readback_rejects_mutation_shaped_or_invalid_requests_before_cloud_auth(monkeypatch):
    def no_credentials():
        raise AssertionError("cloud credentials must not be touched for invalid input")

    monkeypatch.setattr(blockchain, "_cloud_credentials", no_credentials)
    with pytest.raises(blockchain.WolframBlockchainReadbackError):
        blockchain.run_bitcoin_readback(operation="submit", identifier="x", wl_factory=_WL())
    with pytest.raises(blockchain.WolframBlockchainReadbackError):
        blockchain.run_bitcoin_readback(
            operation="transaction",
            identifier="x" * 64,
            properties=["PrivateKey"],
            wl_factory=_WL(),
        )


def test_new_wolfram_modules_and_runtime_mirrors_are_byte_equal_and_compile():
    pairs = [
        (
            ROOT / "backend" / "agent_runtime" / "wolfram_partner_notebook.py",
            ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "wolfram_partner_notebook.py",
        ),
        (
            ROOT / "backend" / "agent_runtime" / "wolfram_blockchain_readback.py",
            ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "wolfram_blockchain_readback.py",
        ),
        (
            ROOT / "backend" / "wolfram_cag_runtime.py",
            ROOT / "scripts" / "sovereign-backend" / "wolfram_cag_runtime.py",
        ),
    ]
    for canonical_path, mirror_path in pairs:
        canonical = canonical_path.read_bytes()
        mirror = mirror_path.read_bytes()
        assert canonical == mirror
        compile(canonical, str(canonical_path), "exec")
        compile(mirror, str(mirror_path), "exec")
