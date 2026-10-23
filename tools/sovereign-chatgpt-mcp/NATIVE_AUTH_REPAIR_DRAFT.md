# Aurion Native-Auth-Reparatur — Repository-Entwurf

Basis: `9341b5151b9476e95186a03e6ee3deb5fd8cdfa9`.
Vertragsquelle: Echoes_of_Aurion `7a4d28a1ab207ed4875e8a33fdd1531335fba826`:
Migration `drizzle/0075_aurion_native_auth_sessions.sql`, `docker-compose.traefik.yml`,
Promoter, Environment-Template und Native-Auth-HTTP-/Startvertrag.

Die drei `aurion_native_auth_plan/apply/readback`-Werkzeuge verwenden die bestehende
Broker-/Host-Worker-Grenze. Nur Apply ist mutationsfähig. Parameter sind ausschließlich
Revision bzw. servergenerierte Operations-ID. Die private Owner-/Aurion-Operator-Grenze
bleibt erforderlich; allgemeine Compose- und SSH-Freigaben bleiben unverändert.

Die authentifizierte Seite `/owner-aurion-native-auth` zeigt den frischen Plan und
Risiken. Nur eine same-origin Owner-Anfrage kann ihn erneut lesen, seinen Hash
bestätigen und eine fünf Minuten gültige Einmalaktion erzeugen. MCP-Argumente oder
das Credential-Widget können diese Freigabe nicht ausstellen. Die Queue enthält nur
die Operations-ID; beim Worker werden Ablauf, Plan und sämtliche Identitäten erneut
geprüft. Die Freigabe wird vor Effekten verbraucht.

Der Host-Adapter löst den aktiven Releasepfad aus Docker-Labels und rootgeschützten
privaten/öffentlichen Deployment-Receipts auf. Manifest, Compose-Hash, Digestvariablen,
Image, Revision, Routing, vorhandene Volumes und Healthz müssen übereinstimmen.
Die feste SQL-Prüfung führt nur `SELECT 1` und Information-Schema-Leseabfragen in einer
Read-only-Transaktion aus. Alle vier Tabellen, Spaltentypen/Nullbarkeit und Indizes
werden mit Migration 0075 verglichen; Abweichung blockiert ohne Migration.
Der vorhandene DB-Verifier und der vollständige Promoter werden niemals gestartet.

Nur die beiden Native-Auth-Einstellungen werden atomar ersetzt. Die ursprüngliche
Datei bleibt als rootgeschützte Sicherung erhalten. Ein gültiger Schlüssel bleibt
unverändert; nur eine konkret genehmigte Neuanlage erzeugt 32 lokale Zufallsbytes.
Ein rootgeschütztes Compose-Override setzt ausschließlich die bereits geprüfte
Image-ID. `up --no-build --pull never --no-deps --force-recreate aurion` erhält
Projekt und aktiven kanonischen Compose-Pfad. Konfigurationsprüfung geht voran.
Ein fehlendes Volume blockiert, statt es implizit anzulegen.

Der einmalige Apply-Starttest erzeugt über die Anwendung eine kurzlebige Transaktion;
er führt keinen Tokenaustausch aus. Körper, Cookies und Transaktions-/Tokenwerte
werden nicht ausgegeben. Spätere Readbacks senden ausschließlich GET und lesen
Docker/Dateien sowie die gespeicherten Starttest-Prädikate. Kein Wiederholungs-POST.
Bei identitätsgebundenem Ausfall ist die Rücknahme an Backup und zuletzt geschriebenen
Konfigurationsfingerprint gebunden und erhält einen unabhängigen Readback.

Der vollständige Intent ist vor dem Receipt dauerhaft auffindbar. Ein Abbruch genau
zwischen beiden Writes ist nachweislich vor Target-Effekten und wird beim Readback
als `NO_EFFECT_PREPARATION_INCOMPLETE` angezeigt. Nur eine neue authentifizierte
Planfreigabe darf diesen belegten Vorbereitungsfall mit dauerhaftem Abschlussbeleg
zurückstellen. Unklare spätere Phasen blockieren neue Mutationen; Wiederzustellung
liest ausschließlich. Ein unklarer Ausgang benötigt separate Untersuchung, keine
automatische erneute Ausführung.

Rootverzeichnis und alle Vorfahren müssen root-eigen und nicht gruppen-/weltweit
schreibbar sein. Unter der Sperre wird derselbe Dirfd verwendet. Dateien benötigen
root:root und 0600; neu erzeugte Dateien erhalten explizit diese Eigentümer auch bei
abweichender Worker-Gruppe. Andere privilegierte Konfigurationswriter müssen die
Operationssperre beachten: keine systemweite Dateisystem-CAS-Garantie.
Das vorbereitete Worker-Unit ergänzt ausschließlich `/opt/echoes-of-aurion` als
schreibbares Verzeichnis für atomaren Austausch. Diese Unit wurde nicht installiert.

Nach erfolgreicher Neuerzeugung bleibt der originale Deployment-Receipt historisch
an den vorherigen Container gebunden. Der Operations-Readback ist deshalb über seine
ID verfügbar; eine neue Reparaturplanung akzeptiert keinen dadurch veralteten
Deployment-Receipt. Kein automatisches Umschreiben kanonischer Release-Belege.

## Evidence und verbleibende Grenzen

```sh
python -m unittest discover -s tools/sovereign-chatgpt-mcp/tests -p 'test_aurion_native_auth_*.py' -q
git diff --check
```

50 lokale Tests bestanden; echte temporäre Dateien, Inodes, Symlinks und Sperren.
Root-Metadaten sowie Docker/HTTP/DB werden an externen Testgrenzen simuliert.
Flask, requests und pytest fehlen lokal; nichts wurde installiert. Authentifizierte
HTTP-, Broker-/Queue- und echte Registry-Tests laufen in den vorhandenen CI-Gates.
Kein Testfixture belegt eine installierte Funktion oder Produktionswirkung.

Runtime, Browser-/Android-Callback, Tokenaustausch, Zonenticket, WebSocket,
Welcome und Welt-Snapshot bleiben **UNVERIFIED**. Kein Merge/Install/Deploy.
