# FreeLLM-Router- und Scanner-Musterbewertung

Datum: 2026-07-25

## Verbindliche Grenze

Sovereign Studio ATO besitzt zwei getrennte LLM-Wahrheitspfade:

1. **Free:** direkter verwalteter FreeLLM-Transport mit Free-Kontingentvertrag, echter Doppel-Completion-Canary, eigenem Quota-Scope und revisionsgebundenem Receipt.
2. **Paid:** direkter OpenRouter-Transport mit eigener Preis-, Guthaben- und Abrechnungslogik.

Der Free-Routen-Scanner liest keine OpenRouter-Modelle, keine Preise, keine Kostenfelder und keine Paid-Kontingente. Öffentliche Listen sind Kandidaten-Evidence, niemals Routing-Wahrheit.

## Übernommene Quellenmuster

### mnfst/awesome-free-llm-apis

Quellen:

- https://github.com/mnfst/awesome-free-llm-apis/blob/main/README.md
- https://raw.githubusercontent.com/mnfst/awesome-free-llm-apis/refs/heads/main/README.md
- https://github.com/mnfst/awesome-free-llm-apis/blob/main/data.json

Übernommen:

- regelmäßiger Abruf des exakt angegebenen Raw-README;
- strukturierter Abruf von `data.json`;
- Modell-IDs und Rate-Limit-/Kontingenthinweise als begrenzte Evidence;
- kanonische GitHub-URL als menschlich lesbare Herkunft, Raw-URL nur als Fetch-Transport.

Nicht übernommen:

- Preis- oder Kostenfelder;
- OpenRouter-Einträge;
- Trial-, Signup-Credit-, Spend- oder Top-up-Angebote;
- automatische Aktivierung.

Nutzen für Sovereign:

Das strukturierte Datenformat reduziert fehleranfällige Freitextauswertung. README und JSON desselben Repositories zählen jedoch als dieselbe Quellenautorität und können nicht gegenseitig einen unabhängigen Konsens vortäuschen.

### AnonymoDGH/ultimate-free-llm-resources

Quelle:

- https://github.com/AnonymoDGH/ultimate-free-llm-resources

Übernommen:

- klare Trennung zwischen dauerhaft kostenfreien Kontingenten und zeitlich/finanziell begrenzten Trials;
- Smoke-Test-, Latenzvergleich- und Kapazitätsbegriff als Evidence-Dimensionen;
- periodische Neubewertung, weil Free-Angebote und Limits veränderlich sind.

Nicht übernommen:

- OpenRouter-Free-Modelle in den FreeLLM-Scanner;
- fremde Skripte oder Zugangsdatenverwaltung;
- ungeprüfte Kapazitätswerte als Routingfreigabe.

Nutzen für Sovereign:

Die Free-versus-Trial-Klassifikation verhindert, dass einmalige Startguthaben als dauerhaft kostenlose Route erscheinen. Latenz ist nur ein Tie-Breaker nach Receipt-, Quota- und Least-Recently-Used-Prüfung.

### yenanjing/awesome-model-routing

Quelle:

- https://github.com/yenanjing/awesome-model-routing

Übernommen:

- Taxonomie für Router, Gateways, Load-Balancer und Auswahlkriterien;
- getrennte Betrachtung von Verfügbarkeit, Latenz, Qualität, Komplexität und Kosten;
- Nutzung als Architektur- und Kandidatenrecherche, nicht als Providerkatalog.

Nicht übernommen:

- externe Router-Laufzeiten;
- deren Kostenrouter oder Modellbewertungen;
- automatische Auswahl aus README-Einträgen.

Nutzen für Sovereign:

Die Taxonomie hilft, Auswahlmerkmale sauber zu trennen. Im Free-Revolver gilt die Reihenfolge: gültiges Receipt, verfügbarer Quota-Scope, Least-Recently-Used, dann Canary-Latenz.

### rohansx/nvidia-litellm-router

Übernommen:

- gemessene Latenz als nachrangiger Tie-Breaker;
- 429 als lokaler, retryfähiger Cooldown statt globaler Providerdefekt.

Nicht übernommen:

- LiteLLM;
- fremde Provider- oder Aliasverwaltung;
- NVIDIA-spezifische Bindung.

Nutzen für Sovereign:

Gleichwertige und unbenutzte Free-Routen können anhand realer Canary-Latenz geordnet werden, ohne den Receipt- oder Quota-Vertrag zu umgehen.

### spacepirate15/quantum-free-router

Übernommen:

- konservative Zertifizierungszustände;
- eine Route ist erst nach dem vollständigen Evidence-Vertrag `certified`.

Nicht übernommen:

- fremder Runtime- oder Routingcode;
- deklarative Behauptungen ohne aktuelle Canaries.

Nutzen für Sovereign:

`certified` ist kein Name oder UI-Farbwert, sondern wird an Doppel-Canary, Free-Kontingentvertrag, Runtime-Revision und Image-Digest gebunden.

### wotai-dev/woterclip

Übernommen:

- lease-gebundener periodischer Lauf;
- persistierter Heartbeat/Run-Readback und strukturierte Fehlerfamilien.

Nicht übernommen:

- Bifrost- oder Persona-spezifische Laufzeit;
- fremde Agentensteuerung.

Nutzen für Sovereign:

Ein Scanner-Lauf besitzt Start, Abschluss, Lease, Quellenanzahl, Findings und einen kanonischen Evidence-Hash. Ein hängender Worker kann dadurch nicht still als aktueller Lauf gelten.

### APILayer Scrapestack

Quelle:

- https://apilayer.com/products/scrapestack/

Übernommen:

- Transportabstraktion zwischen kanonischer Quelle und Fetch-URL;
- begrenzte Antwortgrößen;
- strukturierte HTTP-, Timeout-, Decode- und Transportfehler;
- nachvollziehbare Retry-/Fehlerfamilien.

Nicht übernommen:

- Scrapestack als Produktionsabhängigkeit;
- API-Key, Proxy-, CAPTCHA-, JavaScript- oder Geolocation-Funktion im Routing-Wahrheitspfad;
- Nutzung des begrenzten Gratisplans für periodische Kernfunktion.

Nutzen für Sovereign:

Die robusten Fetch-Prinzipien sind sinnvoll, eine externe Scraping-Abhängigkeit wäre für öffentliche Raw-GitHub-Dateien jedoch unnötig. Sovereign ruft diese Quellen direkt, begrenzt und fail-closed ab. `scrapestackDependency` bleibt daher ausdrücklich `false`.

## Endgültige Aktivierungskette

Eine öffentliche Fundstelle kann höchstens folgende Kette starten:

1. explizit ausgeschriebener HTTPS-Completion-Endpunkt oder strukturierter OpenAI-kompatibler Base-Endpunkt;
2. Ausschluss von OpenRouter, Trial-, Paid- und privaten Zielen;
3. zwei feste Scanner-Canaries ohne echten Benutzerprompt;
4. unabhängiger Quellenautoritätskonsens;
5. Erstellung einer **deaktivierten** Provider-Onboarding-Karte;
6. verwalteter FreeLLM-Katalog und Credential-/Keyless-Vertrag;
7. zwei echte produktive Completion-Canaries;
8. eigener Quota-Scope, Retry- und Cooldown-Vertrag;
9. Receipt für exakt die laufende Source-Revision und den Image-Digest;
10. erst dann Revolver-Eignung.

Keine öffentliche Liste, kein Satz, kein Badge und kein HTTP-200 allein kann eine produktive Route erzeugen.
