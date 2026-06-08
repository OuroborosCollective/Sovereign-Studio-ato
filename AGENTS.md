# Repository Agent Rules

This repository is a free-first no-code code factory.

Before finishing any change, agents must run the full green gate from `sovereign.guard.json`:

- audit:sovereign
- type-check
- test:run
- build

Do not stop after fixing only the files touched in the latest change. If the current repository has older failures, fix those too before calling the work done.

Protect these product rules:

- left side: GitHub file tree and idea/order input
- center: chat, matrix-style file editor and live status
- right side: history log and plain-language analysis
- free-first routing before optional user keys
- visible fix loop on errors
- user confirmation before writing unless autonomous mode is active
