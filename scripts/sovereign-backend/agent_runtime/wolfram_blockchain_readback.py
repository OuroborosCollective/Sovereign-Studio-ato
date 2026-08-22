"""Bounded read-only Bitcoin evidence through an authenticated Wolfram Cloud session.

The public contract deliberately omits transaction construction, signing,
private-key handling and BlockchainTransactionSubmit.  It supports only fixed
Bitcoin-mainnet chain, block and transaction reads with allowlisted properties.
Historical/identity claims about Satoshi Nakamoto remain a separate source-
evidence problem; blockchain data can verify transaction facts but cannot by
itself establish a person's identity.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Sequence

from agent_runtime.wolfram_partner_notebook import (
    WolframCloudNotebookError,
    _cloud_credentials,
)

READBACK_SCHEMA_VERSION = "sovereign.wolfram-bitcoin-readback.v1"
MAX_RESULT_CHARS = 131_072
_TXID = re.compile(r"^[0-9a-f]{64}$")

_NETWORK_PROPERTIES = ("Blocks", "LatestBlockHash", "MinimumFee")
_BLOCK_PROPERTIES = frozenset({
    "BlockHash",
    "BlockNumber",
    "Timestamp",
    "Confirmations",
    "PreviousBlockHash",
    "MerkleRoot",
    "TotalTransactions",
    "Size",
    "Nonce",
    "Version",
})
_TRANSACTION_PROPERTIES = frozenset({
    "TransactionID",
    "BlockHash",
    "BlockNumber",
    "Confirmations",
    "Timestamp",
    "LockTime",
    "Version",
    "TotalInput",
    "TotalOutput",
    "Fee",
    "Size",
    "Inputs",
    "Outputs",
})


class WolframBlockchainReadbackError(ValueError):
    def __init__(self, message: str, *, family: str) -> None:
        super().__init__(message)
        self.family = family


def _properties(values: Sequence[Any] | None, *, allowed: frozenset[str], defaults: tuple[str, ...]) -> list[str]:
    if values is None:
        return list(defaults)
    if isinstance(values, (str, bytes)) or not values or len(values) > 12:
        raise WolframBlockchainReadbackError("properties must be a bounded non-empty array", family="READBACK_SCHEMA")
    result: list[str] = []
    for item in values:
        selected = str(item or "").strip()
        if selected not in allowed:
            raise WolframBlockchainReadbackError("requested blockchain property is not allowlisted", family="READBACK_SCHEMA")
        if selected not in result:
            result.append(selected)
    return result


def _session_factories(session_factory: Any | None, credentials_factory: Any | None):
    if session_factory is not None and credentials_factory is not None:
        return session_factory, credentials_factory
    from wolframclient.evaluation import SecuredAuthenticationKey, WolframCloudSession  # type: ignore
    return (
        session_factory or (lambda credentials: WolframCloudSession(credentials=credentials)),
        credentials_factory or SecuredAuthenticationKey,
    )


def run_bitcoin_readback(
    *,
    operation: str,
    identifier: Any = None,
    properties: Sequence[Any] | None = None,
    session_factory: Any | None = None,
    credentials_factory: Any | None = None,
    wl_factory: Any | None = None,
) -> dict[str, Any]:
    """Execute one read-only Bitcoin-mainnet query and return bounded InputForm evidence."""
    selected_operation = str(operation or "").strip().casefold()
    if selected_operation not in {"network", "block", "transaction"}:
        raise WolframBlockchainReadbackError("unknown Bitcoin readback operation", family="READBACK_SCHEMA")

    if wl_factory is None:
        from wolframclient.language import wl as wl_factory  # type: ignore

    if selected_operation == "network":
        if identifier not in (None, "") or properties not in (None, []):
            raise WolframBlockchainReadbackError("network readback accepts no identifier or custom properties", family="READBACK_SCHEMA")
        selected_identifier = None
        selected_properties = list(_NETWORK_PROPERTIES)
        expression = wl_factory.BlockchainData(
            selected_properties,
            wl_factory.Rule(wl_factory.BlockchainBase, "Bitcoin"),
        )
    elif selected_operation == "block":
        if isinstance(identifier, bool):
            raise WolframBlockchainReadbackError("block identifier must be -1 or a non-negative height", family="READBACK_SCHEMA")
        try:
            selected_identifier = int(identifier)
        except (TypeError, ValueError) as exc:
            raise WolframBlockchainReadbackError("block identifier must be -1 or a non-negative height", family="READBACK_SCHEMA") from exc
        if selected_identifier < -1 or selected_identifier > 2_147_483_647:
            raise WolframBlockchainReadbackError("block identifier is outside the bounded range", family="READBACK_SCHEMA")
        selected_properties = _properties(
            properties,
            allowed=_BLOCK_PROPERTIES,
            defaults=("BlockHash", "BlockNumber", "Timestamp", "Confirmations", "MerkleRoot", "TotalTransactions"),
        )
        expression = wl_factory.BlockchainBlockData(
            selected_identifier,
            selected_properties,
            wl_factory.Rule(wl_factory.BlockchainBase, "Bitcoin"),
        )
    else:
        selected_identifier = str(identifier or "").strip().casefold()
        if not _TXID.fullmatch(selected_identifier):
            raise WolframBlockchainReadbackError("transaction identifier must be a lowercase 64-hex txid", family="READBACK_SCHEMA")
        selected_properties = _properties(
            properties,
            allowed=_TRANSACTION_PROPERTIES,
            defaults=("TransactionID", "BlockHash", "BlockNumber", "Confirmations", "Timestamp", "TotalInput", "TotalOutput", "Fee", "Size"),
        )
        expression = wl_factory.BlockchainTransactionData(
            selected_identifier,
            selected_properties,
            wl_factory.Rule(wl_factory.BlockchainBase, "Bitcoin"),
        )

    try:
        consumer_key, consumer_secret = _cloud_credentials()
    except WolframCloudNotebookError as exc:
        raise WolframBlockchainReadbackError(str(exc), family="CLOUD_AUTH") from exc
    session_factory, credentials_factory = _session_factories(session_factory, credentials_factory)
    credentials = credentials_factory(consumer_key, consumer_secret)
    session = session_factory(credentials)
    started = False
    try:
        session.start()
        started = True
        authorized = session.authorized() if callable(getattr(session, "authorized", None)) else bool(getattr(session, "authorized", False))
        if not authorized:
            raise WolframBlockchainReadbackError("Wolfram Cloud session is not authorized", family="CLOUD_AUTH")
        result = session.evaluate(wl_factory.ToString(expression, wl_factory.InputForm))
        if isinstance(result, bytes):
            result = result.decode("utf-8", errors="strict")
        result_text = str(result or "")
        if not result_text or len(result_text) > MAX_RESULT_CHARS:
            raise WolframBlockchainReadbackError("Wolfram blockchain result is empty or exceeds the bounded output", family="READBACK_OUTPUT")
        result_sha256 = hashlib.sha256(result_text.encode("utf-8")).hexdigest()
        return {
            "ok": True,
            "status": "WOLFRAM_BITCOIN_READBACK_SUCCEEDED",
            "schemaVersion": READBACK_SCHEMA_VERSION,
            "network": "Bitcoin-Mainnet",
            "operation": selected_operation,
            "identifier": selected_identifier,
            "properties": selected_properties,
            "resultInputForm": result_text,
            "resultSha256": result_sha256,
            "readOnly": True,
            "transactionMutationAvailable": False,
            "secretValuesReturned": False,
            "truthNotice": (
                "This receipt verifies a bounded read-only Wolfram blockchain response. "
                "It can support transaction or chain-state claims but cannot by itself establish Satoshi Nakamoto identity attribution."
            ),
        }
    finally:
        if started:
            terminator = getattr(session, "terminate", None) or getattr(session, "stop", None)
            if callable(terminator):
                terminator()


__all__ = [
    "READBACK_SCHEMA_VERSION",
    "WolframBlockchainReadbackError",
    "run_bitcoin_readback",
]
