from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class GitHubContractError(ValueError):
    pass


class GitHubVerdict(str, Enum):
    PLANNED = "PLANNED"
    SUCCEEDED_UNVERIFIED = "SUCCEEDED_UNVERIFIED"
    VERIFIED = "VERIFIED"
    CONTRADICTED = "CONTRADICTED"
    BLOCKED_BY_MISSING_EVIDENCE = "BLOCKED_BY_MISSING_EVIDENCE"


class RetryDecision(str, Enum):
    SAFE_TO_RETRY = "SAFE_TO_RETRY"
    READBACK_REQUIRED = "READBACK_REQUIRED"
    DO_NOT_RETRY = "DO_NOT_RETRY"


@dataclass(frozen=True, slots=True)
class GitHubEndpointContract:
    capability_id: str
    method: str
    endpoint_id: str
    mutates: bool
    high_risk: bool = False


GITHUB_CAPABILITY_MAP: Mapping[str, GitHubEndpointContract] = {
    "github.repository.read": GitHubEndpointContract("github.repository.read", "GET", "repos.get", False),
    "github.contents.read": GitHubEndpointContract("github.contents.read", "GET", "repos.getContent", False),
    "github.contents.write": GitHubEndpointContract("github.contents.write", "PUT", "repos.createOrUpdateFileContents", True),
    "github.git.ref.read": GitHubEndpointContract("github.git.ref.read", "GET", "git.getRef", False),
    "github.git.ref.write": GitHubEndpointContract("github.git.ref.write", "PATCH", "git.updateRef", True, True),
    "github.commit.create": GitHubEndpointContract("github.commit.create", "POST", "git.createCommit", True),
    "github.issue.read": GitHubEndpointContract("github.issue.read", "GET", "issues.get", False),
    "github.issue.create": GitHubEndpointContract("github.issue.create", "POST", "issues.create", True),
    "github.issue.update": GitHubEndpointContract("github.issue.update", "PATCH", "issues.update", True),
    "github.issue.comment.create": GitHubEndpointContract("github.issue.comment.create", "POST", "issues.createComment", True),
    "github.pull.read": GitHubEndpointContract("github.pull.read", "GET", "pulls.get", False),
    "github.pull.create_draft": GitHubEndpointContract("github.pull.create_draft", "POST", "pulls.create", True),
    "github.pull.review.request": GitHubEndpointContract("github.pull.review.request", "POST", "pulls.requestReviewers", True),
    "github.pull.merge": GitHubEndpointContract("github.pull.merge", "PUT", "pulls.merge", True, True),
    "github.actions.read": GitHubEndpointContract("github.actions.read", "GET", "actions.getWorkflowRun", False),
    "github.actions.rerun": GitHubEndpointContract("github.actions.rerun", "POST", "actions.reRunWorkflow", True, True),
    "github.artifact.read": GitHubEndpointContract("github.artifact.read", "GET", "actions.getArtifact", False),
    "github.ruleset.read": GitHubEndpointContract("github.ruleset.read", "GET", "repos.getRepoRuleset", False),
    "github.ruleset.write": GitHubEndpointContract("github.ruleset.write", "PUT", "repos.updateRepoRuleset", True, True),
}

_HASH = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True, slots=True)
class SovereignGitHubRequestV1:
    capability_id: str
    owner: str
    repository: str
    method: str
    endpoint_id: str
    path_params: Mapping[str, str | int]
    query_hash: str = ""
    body_hash: str = ""
    expected_repository_revision: str = ""
    expected_resource_version: str = ""
    idempotency_key: str = ""
    permission_receipt_hash: str = ""

    def validate(self) -> GitHubEndpointContract:
        contract = GITHUB_CAPABILITY_MAP.get(self.capability_id)
        if contract is None:
            raise GitHubContractError("unknown GitHub capability")
        if self.method != contract.method or self.endpoint_id != contract.endpoint_id:
            raise GitHubContractError("endpoint and method do not match capability map")
        if not _NAME.fullmatch(self.owner) or not _NAME.fullmatch(self.repository):
            raise GitHubContractError("owner and repository must be canonical identifiers")
        if any(key.lower() in {"url", "endpoint", "token", "authorization"} for key in self.path_params):
            raise GitHubContractError("free URL or credential parameters are forbidden")
        for value in (self.query_hash, self.body_hash, self.permission_receipt_hash):
            if value and not _HASH.fullmatch(value):
                raise GitHubContractError("request hashes must be lowercase SHA-256")
        if self.expected_repository_revision and not _REVISION.fullmatch(self.expected_repository_revision):
            raise GitHubContractError("expected repository revision must be a full commit SHA")
        if contract.mutates:
            if not self.permission_receipt_hash:
                raise GitHubContractError("mutations require a permission receipt")
            if not self.idempotency_key:
                raise GitHubContractError("mutations require an idempotency key")
            if not self.expected_resource_version and not self.expected_repository_revision:
                raise GitHubContractError("mutations require an expected resource or repository version")
        return contract

    @property
    def request_hash(self) -> str:
        payload = {
            "schemaVersion": "sovereign-github-request.v1",
            "capabilityId": self.capability_id,
            "owner": self.owner,
            "repository": self.repository,
            "method": self.method,
            "endpointId": self.endpoint_id,
            "pathParams": dict(sorted(self.path_params.items())),
            "queryHash": self.query_hash,
            "bodyHash": self.body_hash,
            "expectedRepositoryRevision": self.expected_repository_revision,
            "expectedResourceVersion": self.expected_resource_version,
            "idempotencyKey": self.idempotency_key,
            "permissionReceiptHash": self.permission_receipt_hash,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class GitHubExecutionReceipt:
    run_id: str
    workflow_step: str
    skill_id: str
    manifest_hash: str
    capability_id: str
    adapter_revision: str
    api_version: str
    principal_identity_hash: str
    repository_identity: str
    request_hash: str
    permission_receipt_hash: str
    response_status: int
    response_hash: str
    expected_readback: str
    verdict: GitHubVerdict = GitHubVerdict.SUCCEEDED_UNVERIFIED

    def validate(self) -> None:
        hashes = (
            self.manifest_hash,
            self.principal_identity_hash,
            self.request_hash,
            self.permission_receipt_hash,
            self.response_hash,
        )
        if any(not _HASH.fullmatch(value) for value in hashes):
            raise GitHubContractError("receipt identities must be SHA-256 values")
        if self.verdict is GitHubVerdict.VERIFIED:
            raise GitHubContractError("transport receipts cannot self-assert VERIFIED")
        if not self.expected_readback:
            raise GitHubContractError("an independent readback must be declared")


def retry_decision(
    request: SovereignGitHubRequestV1,
    *,
    transport_failed_or_timed_out: bool,
    independent_readback_completed: bool,
    effect_observed: bool,
) -> RetryDecision:
    contract = request.validate()
    if not transport_failed_or_timed_out:
        return RetryDecision.DO_NOT_RETRY
    if not contract.mutates:
        return RetryDecision.SAFE_TO_RETRY
    if not independent_readback_completed:
        return RetryDecision.READBACK_REQUIRED
    return RetryDecision.DO_NOT_RETRY if effect_observed else RetryDecision.SAFE_TO_RETRY
