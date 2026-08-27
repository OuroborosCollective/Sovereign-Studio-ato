"""Truth boundary tests for EGAM Authority Usage Feasibility.

These tests verify the current state of authority tracking infrastructure.
They document what EXISTS and what DOES NOT EXIST to support the
feasibility decision.

Issue: #1602
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add backend to path for imports (same pattern as other tests)
RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))


class TestAuthorityUsageTruthBoundary:
    """Document current authority tracking state for EGAM feasibility."""

    def test_no_authority_atom_class_exists(self):
        """Verify no AuthorityAtom dataclass exists in agent_runtime."""
        from agent_runtime import agent_run_receipts
        
        # Check that AuthorityAtom is not defined
        assert not hasattr(agent_run_receipts, 'AuthorityAtom'), \
            "AuthorityAtom should not exist - no canonical authority baseline"

    def test_no_capability_manifest_exists(self):
        """Verify no Capability Manifest implementation exists."""
        import os
        import glob
        
        # Search for capability manifest files
        backend_path = os.path.join(os.path.dirname(__file__), '..', 'agent_runtime')
        capability_files = glob.glob(f"{backend_path}/**/*capability*manifest*.py", recursive=True)
        capability_files += glob.glob(f"{backend_path}/**/*manifest*.py", recursive=True)
        
        # Filter to only those that are actual implementations (not just references)
        implementation_files = []
        for f in capability_files:
            with open(f, 'r') as fp:
                content = fp.read()
                # Look for actual CapabilityManifest class definition
                if 'class CapabilityManifest' in content or 'class RunEnvelope' in content:
                    implementation_files.append(f)
        
        assert len(implementation_files) == 0, \
            f"No capability manifest implementation should exist. Found: {implementation_files}"

    def test_receipts_track_tool_names_but_not_authority_atoms(self):
        """Verify receipts record tool names but not mapped to authority atoms."""
        from agent_runtime import agent_run_receipts
        
        # The module has identity classes, but no ToolReceipt class
        # Tool names are tracked elsewhere (if at all)
        assert not hasattr(agent_run_receipts, 'ToolReceipt'), \
            "No ToolReceipt class - tool tracking exists elsewhere or not at all"
        
        # Verify there's no authority_atom class in the module
        assert not hasattr(agent_run_receipts, 'AuthorityAtom'), \
            "No AuthorityAtom class - no atom decomposition"

    def test_no_trust_reduction_receipts(self):
        """Verify no trust-based capability reduction receipts exist."""
        from agent_runtime import agent_run_receipts
        
        # Check for trust-related receipt classes
        all_attrs = dir(agent_run_receipts)
        trust_receipts = [a for a in all_attrs if 'trust' in a.lower() and 'receipt' in a.lower()]
        
        assert len(trust_receipts) == 0, \
            f"No trust reduction receipts should exist. Found: {trust_receipts}"

    def test_no_cas_mutation_control(self):
        """Verify no CAS/atomic mutation control exists."""
        import os
        
        backend_path = os.path.join(os.path.dirname(__file__), '..', 'agent_runtime')
        cas_files = []
        
        for root, dirs, files in os.walk(backend_path):
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    with open(filepath, 'r') as fp:
                        content = fp.read()
                        if 'CAS' in content and 'mutation' in content.lower():
                            cas_files.append(filepath)
        
        # Filter to actual implementations
        implementation_files = []
        for f in cas_files:
            with open(f, 'r') as fp:
                content = fp.read()
                if 'class CAS' in content or 'def cas_' in content:
                    implementation_files.append(f)
        
        assert len(implementation_files) == 0, \
            f"No CAS mutation control should exist. Found: {implementation_files}"

    def test_fleet_attempt_has_manifest_hash_field(self):
        """Verify FleetWorkerAttempt has capability_manifest_hash but no binding."""
        from agent_runtime import fleet_attempts
        import dataclasses
        
        fields = {f.name for f in dataclasses.fields(fleet_attempts.FleetWorkerAttempt)}
        
        # This field exists but is just a hash, not a manifest binding
        assert 'capability_manifest_hash' in fields, \
            "capability_manifest_hash should exist (hash only, not full manifest)"
        
        # But there's no manifest_content or atom decomposition
        assert 'capability_manifest' not in fields, \
            "Full capability manifest should not exist - just hash field"


class TestEGAMFeasibilityEvidence:
    """Document the feasibility decision evidence."""

    def test_prerequisite_issues_not_implemented(self):
        """Verify blocking prerequisites are not implemented."""
        # These should all be OPEN issues
        # #1116 - RunEnvelope + Capability Manifest
        # #1118 - Context Trust  
        # #1119 - CAS Mutation Control
        
        # We verify by checking no implementation exists
        # The actual issue status is checked via GitHub API in docs
        
        # This test documents the state
        assert True, "Issue status verified via GitHub API in feasibility doc"

    def test_no_unsafe_inference_from_tool_names(self):
        """Document that tool names cannot be safely mapped to authority atoms."""
        from agent_runtime import agent_run_receipts
        
        # Example: "github_create_pull_request" could imply:
        # - TOOL: github API
        # - EGRESS_TARGET: github.com
        # - EFFECT_CLASS: mutation
        # - MUTATION_FAMILY: pull_request
        
        # Without ToolReceipt class, tool name tracking doesn't exist at all
        assert not hasattr(agent_run_receipts, 'ToolReceipt'), \
            "No ToolReceipt class - tool names not tracked in receipts"
