"""Agent Execution Transparency statement lane (SVET 1/5, Issue #1485).

This package is a read-only, privacy-minimized projection surface. It derives a
canonical, externally exportable ``AgentExecutionTransparencyStatement`` from an
already-verified internal receipt chain produced by
:mod:`agent_runtime.agent_run_receipts`.

It owns no effect truth, no second receipt chain, no external registration and no
signature effect. Removing the package must leave the canonical ATO runtime
unchanged (see ``test_execution_transparency_statement``).
"""

from .statement import (  # noqa: F401
    REDACTED_FIELDS,
    STATEMENT_SCHEMA_VERSION,
    AgentExecutionTransparencyStatement,
    TransparencyBlocked,
    build_transparency_statement,
    privacy_minimized_statement,
    statement_sha256,
)
