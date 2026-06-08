# Ghost Pilot Final Notes

The branch focuses on CI hardening only.

The previous failure mode was a missing or invalid Gemini response producing an almost empty ADB sequence. The new flow validates generated sequences and falls back to a deterministic interaction path.

The workflow keeps repository guard commands ahead of emulator execution and stores enough artifacts to diagnose degraded runs.
