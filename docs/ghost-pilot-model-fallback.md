# Ghost Pilot Model Fallback

Model order:

1. repository variable `GEMINI_MODEL`, when set,
2. `gemini-2.5-flash`,
3. `gemini-2.5-flash-lite`,
4. `gemini-flash-latest`.

When all model attempts fail or return a weak sequence, Ghost Pilot uses the deterministic fallback script.
