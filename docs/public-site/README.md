# Sovereign Studio ATO — public GitHub Pages site

## Purpose and scope

A standalone public, static portfolio/engineering-services landing page for **Sovereign Studio ATO**. It is not the Sovereign Live Workspace Monitor and never communicates with the private production backend. It does not modify the Vite, Capacitor, Android, Flask, MCP or database runtime. All included site files live in \`public-site/\`.

The site does not claim that GitHub repository features are runtime-verified. The linked public repositories have different licensing terms; the Sovereign application is proprietary.

## Exact inputs and boundaries

- Public project: \`OuroborosCollective/Sovereign-Studio-ato\`
- Product truth: \`docs/SOVEREIGN_PRODUCT_TRUTH.md\`
- Revision baseline at creation: \`5b0d686a03989f4228d9bfcd3c48400af70590ff\`
- No credentials, provider endpoints, customer data, unpublished screenshots or internal URLs belong in this site.
- Publication is a separate public-world effect; a PR and green source check do **not** prove the GitHub Pages site is live.

## Local review and reproducible regression

From the repository root, with Python 3.10+:

\`\`\`bash
python3 -m unittest discover -s tests -p 'test_public_site_contract.py' -v
python3 scripts/verify-public-site.py --root public-site --mode preview
python3 -m http.server 8765 --bind 127.0.0.1 --directory public-site
\`\`\`

Open \`http://127.0.0.1:8765/\` and review at desktop and mobile widths. Confirm keyboard navigation, focus visibility, links, readable text, no third-party resources, and reduced-motion behavior. There is no JavaScript bundle or site build dependency.

The PR-only validation workflow \`.github/workflows/sovereign-public-site-check.yml\` runs both static checks on the exact PR head. The manual publishing workflow is \`.github/workflows/sovereign-pages-publish.yml\`. Neither site previews nor successful workflows verify the Sovereign backend runtime.

## Publication blockers — MUST be resolved before the manual release

1. **Legally complete imprint:** Add the actual provider's ladungsfähige Anschrift, viable contact address, legal entity and other mandatory disclosures after owner/legal review. The current \`impressum.html\` is explicitly a draft.
2. **Privacy policy:** Verify actual GitHub Pages hosting practices and required GDPR disclosures, roles, legal bases, transfer and retention rules; complete the \`datenschutz.html\` draft.
3. **Contact route:** Replace or supplement the GitHub-organization link with a verified, deliberately public business contact channel. Avoid public issue forms that solicit secrets.
4. **Publication gates:** Remove \`PUBLICATION_BLOCKER\` markers only after legal review and remove all \`noindex, nofollow\` directives when the page is intentionally launch-ready. Never remove a blocker merely to get a green workflow.
5. **Approval:** Review the final changed HTML/CSS, licenses and outreach copy on an exact-head PR, run required repository/CI tests, and obtain owner-specific merge/publication authorization.
6. **Pages settings:** Set \`Settings → Pages → Build and deployment → Source: GitHub Actions\`. This step is not performed by adding the workflow file and must be read back.
7. **Manual release:** After the reviewed PR is merged to \`main\`, dispatch \`Sovereign Public Site - Publish GitHub Pages\` from \`main\`. Its release validator blocks unresolved legal placeholders or remaining \`noindex\` directives.
8. **Readback:** Confirm Pages deployment succeeded for the exact commit and test the real public URL over HTTPS: \`https://ouroboroscollective.github.io/Sovereign-Studio-ato/\`. Validate content, CSS, internal anchors, privacy/imprint, availability and correct link targets from an independent client. The URL is **expected**, not proof of publication.

Do **not** create an automatic push-to-main deployment, permit publication from a PR, or expose a rendered placeholder imprint. Do not enable GitHub Pages until these conditions are satisfied.

## Ownership and state

The website stays isolated to \`public-site/\`, a dedicated static validation script/test, the two GitHub Actions files, and this documentation. No migration, canonical/deployment mirror, application route or production environment is affected. Site availability must be verified from GitHub Pages, not inferred from this repository.
