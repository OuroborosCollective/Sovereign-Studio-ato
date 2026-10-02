"""Bounded Bitcoin Core JSON-RPC source adapter.

This adapter is the live source boundary for the canonical graph pipeline.
Credentials are read only at call time from the process environment and are
never included in exceptions, receipts or persisted objects.

The adapter fetches blocks/transactions only. Prevout resolution is injected
into block_from_rpc so large historical imports can use a local canonical
UTXO store instead of issuing one RPC request per input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import base64
import json
import os
import re
from typing import Any, Iterable, Mapping
from urllib import error, parse, request


class BitcoinCoreRpcError(RuntimeError):
    """Raised when Bitcoin Core cannot satisfy a bounded RPC request."""


@dataclass(frozen=True, slots=True)
class BitcoinCoreRpcConfig:
    endpoint: str = field(repr=False)
    username_env: str = "BITCOIN_RPC_USER"
    password_env: str = "BITCOIN_RPC_PASSWORD"
    timeout_seconds: int = 30
    auth_mode: str = "basic"

    def __post_init__(self) -> None:
        endpoint = str(self.endpoint or "").strip()
        if not endpoint.startswith(("http://", "https://")):
            raise BitcoinCoreRpcError("RPC endpoint must use HTTP(S)")
        try:
            url = parse.urlsplit(endpoint)
            port = url.port
        except ValueError:
            raise BitcoinCoreRpcError("RPC endpoint is invalid") from None
        if not url.hostname or url.username or url.password or url.fragment:
            raise BitcoinCoreRpcError("RPC endpoint is invalid")
        if self.auth_mode not in ("basic", "quicknode"):
            raise BitcoinCoreRpcError("RPC auth_mode must be basic or quicknode")
        if self.auth_mode == "quicknode":
            if url.scheme != "https" or port not in (None, 443):
                raise BitcoinCoreRpcError("QuickNode requires HTTPS on port 443")
            if not url.hostname.lower().endswith(".quiknode.pro"):
                raise BitcoinCoreRpcError("QuickNode requires a quiknode.pro endpoint")
            if url.query or not re.fullmatch(r"/[A-Za-z0-9_-]+/?", url.path):
                raise BitcoinCoreRpcError("QuickNode requires a protected token endpoint")
        object.__setattr__(self, "endpoint", endpoint)
        if self.auth_mode == "basic" and (not self.username_env or not self.password_env):
            raise BitcoinCoreRpcError("Bitcoin Core credential environment names are required")
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, int):
            raise BitcoinCoreRpcError("timeout_seconds must be an integer")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 120:
            raise BitcoinCoreRpcError("timeout_seconds must be in 1..120")


class _RejectRpcRedirects(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BitcoinCoreRpcError("Bitcoin Core RPC redirects are forbidden")


class BitcoinCoreRpcClient:
    """Minimal JSON-RPC client for read-only blockchain ingestion."""

    def __init__(self, config: BitcoinCoreRpcConfig) -> None:
        self._config = config
        self._opener = request.build_opener(_RejectRpcRedirects())

    def _authorization(self) -> str | None:
        if self._config.auth_mode == "quicknode":
            return None
        username = os.environ.get(self._config.username_env, "")
        password = os.environ.get(self._config.password_env, "")
        if not username or not password:
            raise BitcoinCoreRpcError("Bitcoin Core RPC credentials are unavailable")
        token = base64.b64encode((username + ":" + password).encode("utf-8")).decode("ascii")
        return "Basic " + token

    def call(self, method: str, params: Iterable[Any] = ()) -> Any:
        if method not in {"getblockcount", "getblockhash", "getblock", "getblockchaininfo"}:
            raise BitcoinCoreRpcError("RPC method is not allowed for read-only ingestion")
        body = json.dumps(
            {"jsonrpc": "2.0" if self._config.auth_mode == "quicknode" else "1.0",
             "id": "sovereign-bitcoin", "method": method, "params": list(params)},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        authorization = self._authorization()
        if authorization is not None:
            headers["Authorization"] = authorization
        req = request.Request(
            self._config.endpoint,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with self._opener.open(req, timeout=self._config.timeout_seconds) as response:
                raw = response.read()
        except (error.URLError, TimeoutError):
            raise BitcoinCoreRpcError("Bitcoin Core RPC transport failed") from None

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise BitcoinCoreRpcError("Bitcoin Core RPC returned invalid JSON") from None

        if not isinstance(payload, Mapping) or payload.get("id") != "sovereign-bitcoin":
            raise BitcoinCoreRpcError("Bitcoin Core RPC returned an invalid envelope")
        if payload.get("error") is not None:
            error_payload = payload["error"]
            code = error_payload.get("code") if isinstance(error_payload, Mapping) else None
            suffix = " (" + str(code) + ")" if type(code) is int else ""
            # Provider messages can echo the credential-bearing endpoint.
            raise BitcoinCoreRpcError("Bitcoin Core RPC returned an error" + suffix)
        if "result" not in payload:
            raise BitcoinCoreRpcError("Bitcoin Core RPC returned an invalid envelope")
        return payload.get("result")

    def get_block_count(self) -> int:
        result = self.call("getblockcount")
        if isinstance(result, bool) or not isinstance(result, int) or result < 0:
            raise BitcoinCoreRpcError("getblockcount returned an invalid height")
        return result

    def get_block_hash(self, height: int) -> str:
        if isinstance(height, bool) or not isinstance(height, int) or height < 0:
            raise BitcoinCoreRpcError("height must be a non-negative integer")
        result = self.call("getblockhash", (height,))
        if not isinstance(result, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", result):
            raise BitcoinCoreRpcError("getblockhash returned an invalid hash")
        return result.lower()

    def get_block(self, height: int) -> Mapping[str, Any]:
        block_hash = self.get_block_hash(height)
        result = self.call("getblock", (block_hash, 2))
        if not isinstance(result, Mapping):
            raise BitcoinCoreRpcError("getblock returned a non-object result")
        if int(result.get("height", -1)) != height:
            raise BitcoinCoreRpcError("getblock height does not match request")
        if str(result.get("hash", "")).lower() != block_hash:
            raise BitcoinCoreRpcError("getblock hash does not match request")
        return result

    def iter_blocks(
        self,
        start_height: int = 0,
        end_height: int | None = None,
    ) -> Iterable[Mapping[str, Any]]:
        latest = self.get_block_count()
        if end_height is None:
            end_height = latest
        if start_height < 0 or end_height < start_height:
            raise BitcoinCoreRpcError("invalid block range")
        if end_height > latest:
            raise BitcoinCoreRpcError("requested end_height exceeds chain tip")
        for height in range(start_height, end_height + 1):
            yield self.get_block(height)


__all__ = ["BitcoinCoreRpcError", "BitcoinCoreRpcConfig", "BitcoinCoreRpcClient"]
