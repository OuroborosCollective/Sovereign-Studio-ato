# Sovereign Studio

Workflow Fehleranalyse + Runtime Check + Test Plan

LOCAL PATTERN: [tags: llm-runtime, brain-gated-providers-prevent-preview-only-prs., repository-tree-analysis-must-happen-before-file-generation., launch-readiness-scoring-catches-missing-ci-and-docs-before-merge.]
Aha: Classify request, analyze repo tree, score launch readiness, produce concrete files, validate package, then push through GitHub PR flow. (proof-backed success).

## Runtime goals

- Provider output is never trusted blindly.
- Each result must pass the Sovereign five-layer brain contract.
- README requests must update README/docs, not only generated preview artifacts.
- GitHub push uses real repo tree analysis before branch creation.
- Workflows are surfaced to the user before final approval.

## Architecture

node repo, README=yes, workflows=yes, tests=yes, runtime=yes

## Launch readiness

target/repository: 78/100 HEALTHY

## Provider order

1. mlvoca - Existing Mlvoca route
2. pollinations - Existing Pollinations route
3. groq - Groq route
4. huggingface - HuggingFace route
5. together - Together AI route
6. openrouter - OpenRouter route
7. optional-user-keys - Optional user-key routes
8. ovh-anonymous-code-chat - OVHcloud anonymous code_chat@latest
9. ovh-anonymous-fixed-model - OVHcloud anonymous pinned model
10. puter-js-opt-in - Puter.js opt-in route
11. hf-curated-public-space - Curated Hugging Face public Space
