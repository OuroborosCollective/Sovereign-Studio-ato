# Sovereign Evidence Observatory: vierstufige signierte Runs

## Eigentümerschaften

- Aktuelles Repository: https://github.com/OuroborosCollective/Sovereign-Studio-ato
- Hugging Face: persönliches Konto Thorsu, nicht Organisation ouroboroscollective.
- Space: https://huggingface.co/spaces/Thorsu/sovereign-evidence-observatory
- Dataset: https://huggingface.co/datasets/Thorsu/sovereign-evidence-observatory
- Notion: https://app.notion.com/p/3eb5a669363581b79a77ece4841a1d41

## Code- und Sicherheitsflächen

- Core: scripts/sovereign-backend/evidence_observatory_four_layer.py ist der reine Validator für Ed25519, SHA-256, formales Replay, Quellenkontext und Evidence-Record v1.
- Runtime-/Effektgrenze: scripts/sovereign-backend/evidence_observatory_live_runner.py liest den bestehenden Thorsu-Gradio-Space, ruft ausschließlich den bestehenden geschützten Wolfram-CAG-Compute-Transport auf und prüft die Space-Revision erneut.
- Persistenz und Veröffentlichung: Der vorhandene evidence_observatory_publisher.py bleibt kanonisch. Kein zweiter Publisher, keine direkten main/master-Schreibaktionen; nur staging-atlas mit geprüften Rechten, Privacy-Gate, Duplikatprüfung, Commit und SHA-Readback.
- Tests: Die beiden neuen test_evidence_observatory_* Module arbeiten mit temporären Testschlüsseln und ausschließlich ausdrücklich simulierten Netzwerkantworten. Tests sind kein Runtime-Nachweis.
- Notion: Menschlich lesbarer Evidence-Index, ausdrücklich keine Runtime- oder Wahrheitsquelle.

## Vier-Schichten-Pfad

Observatory (echte signierte Ausführungsquittung) -> Wolfram CAG (unabhängige berechenbare Referenz) -> alphaXiv (methodischer Forschungskontext, nicht Primzahlbeweis) -> Notion (Belegindex).

Die V1-Formalfälle sind '173 is prime' und '174 is prime' sowie dieselbe begrenzte Primzahlgrammatik für ganze Zahlen unter 2^64. Das ist kein Nachweis einer Identität oder universellen Systemkorrektheit.

Die Ed25519-Key-ID ist auf den geprüften öffentlichen Anchor gepinnt. Der Proof-Router signiert die Claim-Ausführung, nicht die Git-Revision des Space. Diese wird durch separate Live-Hub-Readbacks vor/nach dem Aufruf gebunden. Ein Versionswechsel oder fehlerhafte Signatur blockiert. Eine unbestätigte neue Key-ID darf niemals automatisch übernommen werden.

Der Wolfram-Providertransport muss SUCCEEDED_UNVERIFIED liefern und einen exakt auswertbaren booleschen PrimeQ-Wert. Das bedeutet einen bestätigten Transport, aber keine allgemeine semantische Wahrheit oder kryptographische Provider-Signatur. Die formale Aussage wird unabhängig deterministisch nachgerechnet.

alphaXiv-Verweise werden als METHODOLOGICAL_CONTEXT_ONLY / Peer-Review UNVERIFIED geführt. Ihre Verlinkung ist keine neue Prüfung der kompletten Paper-Dateien.

## Befehle im bestehenden Backend-Environment

Die Backend-Abhängigkeit gradio_client ist in requirements.txt ergänzt. Kein neuer HF Job, keine Sandbox, kein Hardware-Upgrade.

```bash
cd scripts/sovereign-backend
python3 evidence_observatory_live_runner.py --claim "173 is prime"
python3 evidence_observatory_live_runner.py --claim "174 is prime"
```

Nur für ein ausdrücklich gültig freigegebenes staging-atlas-Paket mit vorhandener owner-managed Rights-Datei und Transportidentität:

```bash
python3 evidence_observatory_live_runner.py --claim "173 is prime" --publish-staging
```

Der bestehende Publisher blockiert fehlende Freigabe, falsche Case-ID, Main-Schreibzugriff und Hash-/Readback-Fehler. Das Notion-Index-Objekt kann erst nach einem tatsächlichen Publish-/Readback-Ergebnis als veröffentlicht gekennzeichnet werden; die Notion-Schreibaktion selbst ist Aufgabe des verbundenen Notion-Connectors.

## Abnahme

1. Python Regressionen aller neuen und vorhandenen Observatory/CAG/Publisher-Tests auf einem exakten Workspace-SHA.
2. GitHub-CI auf endgültigem PR-Head; keine statischen Scannerfunde als Runtime-Nachweis ausgeben.
3. Öffentliches Thorsu-Space RUNNING, zweimaliger identischer Hub-Commit-SHA und Gradio-API-Live-Receipt.
4. Verifizierte Ed25519-Signatur gegen den festen Revisions-Trust-Anchor, positiver und negativer Mathematikfall, CAG-Providerresponse und eindeutiges Bundle.
5. Public-safe Rights-, Privacy-, Dedup- und staging-atlas-Publisher-Gates; exakte Daten-/Manifest-Hashes vom Commit lesen.
6. Sovereign-Persistenz-Receipt erst nach Target-Readback; echter Notion-Schreib-/Lesenachweis als getrennter Schritt.

Externer Befund am 2026-10-08: Huggi dynamic_space zeigte HTTP 503 beim Observatory und Explorer. Kein neuer Live-End-to-End-Run, kein gemergter GitHub-Code, keine neue Hub-Publikation oder neue Notion-Claim-Seite wird aus diesem Codeblock behauptet.

Truth Boundary: CODE_REGRESSION_VERIFIED != DEPLOYED_RUNTIME_VERIFIED != HF_PUBLISHED_VERIFIED != NOTION_INDEX_READBACK_VERIFIED.
