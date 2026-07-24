from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from output_contracts import ExternalWriteOutput, ToolOutputEnvelope


class GitHubIssueLabel(BaseModel):
    """Secret-free label metadata returned by the GitHub Issues API."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Exact GitHub label name.")
    color: str = Field(description="Six-character GitHub label color without a leading hash.")
    description: str | None = Field(description="Optional GitHub label description.")


class GitHubIssueActor(BaseModel):
    """Bounded public actor identity from GitHub readback."""

    model_config = ConfigDict(extra="forbid")

    login: str = Field(description="GitHub login returned by the API.")
    type: str = Field(description="GitHub actor type, for example User or Bot.")
    url: str = Field(description="Canonical GitHub profile URL.")


class GitHubIssueSummary(BaseModel):
    """Canonical issue summary used by list and single-issue readback."""

    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1, description="Positive GitHub issue number.")
    title: str = Field(min_length=1, description="Exact current issue title.")
    state: Literal["open", "closed"] = Field(description="Current GitHub issue state.")
    stateReason: str | None = Field(description="Current GitHub state reason when available.")
    labels: list[GitHubIssueLabel] = Field(description="Current labels from GitHub readback.")
    author: GitHubIssueActor | None = Field(description="Issue author when GitHub returns one.")
    assignees: list[GitHubIssueActor] = Field(description="Current issue assignees.")
    comments: int = Field(ge=0, description="Current issue comment count.")
    locked: bool = Field(description="Whether GitHub currently marks the issue as locked.")
    createdAt: str = Field(min_length=1, description="GitHub creation timestamp.")
    updatedAt: str = Field(min_length=1, description="GitHub last-update timestamp used for stale-write protection.")
    closedAt: str | None = Field(description="GitHub closure timestamp when closed.")
    url: str = Field(min_length=1, description="Canonical GitHub issue URL.")


class GitHubIssueDetail(GitHubIssueSummary):
    """Full issue contract with the current Markdown body."""

    body: str = Field(description="Exact current GitHub issue body, normalized from null to an empty string.")


class RepositoryIssueListOutput(ToolOutputEnvelope):
    """Strict output schema for authenticated open-issue listing."""

    repository: str | None = Field(default=None, description="Authenticated repository full name when readback succeeded.")
    queryState: Literal["open"] = Field(default="open", description="The enforced issue-state filter.")
    count: int = Field(default=0, ge=0, description="Number of non-PR issues returned.")
    issues: list[GitHubIssueSummary] = Field(default_factory=list, description="Current open issues, excluding pull requests.")
    readbackVerified: bool = Field(description="True only after authenticated GitHub API readback.")


class RepositoryIssueReadOutput(ToolOutputEnvelope):
    """Strict output schema for one authenticated issue readback."""

    repository: str | None = Field(default=None, description="Authenticated repository full name when readback succeeded.")
    issue: GitHubIssueDetail | None = Field(default=None, description="Current issue state and full body when readback succeeded.")
    readbackVerified: bool = Field(description="True only after authenticated GitHub API readback.")


class RepositoryIssueCloseOutput(ExternalWriteOutput):
    """Strict output schema for stale-safe issue closure with authoritative readback."""

    repository: str | None = Field(default=None, description="Authenticated repository full name when readback succeeded.")
    issueNumber: int | None = Field(default=None, ge=1, description="Closed GitHub issue number on success.")
    title: str | None = Field(default=None, description="Issue title confirmed by final GitHub readback.")
    state: Literal["closed"] | None = Field(default=None, description="Final GitHub issue state on success.")
    stateReason: Literal["completed"] | None = Field(default=None, description="Final GitHub issue state reason on success.")
    expectedUpdatedAt: str | None = Field(default=None, description="Caller-confirmed pre-mutation update timestamp.")
    actualUpdatedAt: str | None = Field(default=None, description="Final update timestamp from GitHub readback.")
    url: str | None = Field(default=None, description="Canonical GitHub issue URL on success.")
