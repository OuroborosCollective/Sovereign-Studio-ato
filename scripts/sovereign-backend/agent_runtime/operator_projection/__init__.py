"""Optional, fully-removable NocoDB operator projection lane (Issue #1174).

This package is an architecture study, not a runtime truth source. It produces a
rebuildable, read-only, redacting projection of canonical runtime records and a
strict, schema-bound command-request gateway. It never owns canonical data, never
holds write authority, and never executes effects directly. Removing the package
must leave the core ATO runtime unchanged (see ``test_operator_projection_removal``).
"""
