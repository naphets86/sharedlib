# sharedlib

Referenzimplementierung der Schichten des einheitlichen Shared-Library-Formats **`.sl`**
mit standardisierter Ladeprozedur: Container, Loader-Kern, Plattformadapter,
Codegenerierung, Build-Orchestrierung und Kommandozeile. Das Repository heißt `sharedlib`,
das Python-Paket `sl` (Distribution `sl-framework`), benötigt Python ≥ 3.11 und hat keine Laufzeitabhängigkeiten.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-126%20passed-4c1)](tests/)
[![Test Coverage](https://img.shields.io/badge/Test%20Coverage-99%25-brightgreen)](doc/coverage/index.html)
[![scicov](https://img.shields.io/badge/scicov-!-ff69b4)](doc/coverage/index.html)

Idee: Dasselbe Programm sagt auf Windows, Linux und macOS „lade `wsat_shim`, finde
`wsat_solve`, rufe es auf“ und erhält dieselbe Suchreihenfolge, dieselben Fehlercodes und
dieselbe Lebenszyklussemantik. Alles Betriebssystemspezifische steckt im Plattformadapter.

Weiterführend: Der Diskussionsentwurf des Formats liegt auf oberster Ebene des Projekts
([`proposal.md`](https://github.com/naphets86/sharedlib/blob/main/proposal.md)), die formale Analyse dieser Referenzimplementierung unter
[`science/`](science/) ([PDF](science/sharedlib.pdf), [LaTeX-Hauptdatei](science/sharedlib.tex)).
Siehe [Entwurf und Spezifikation](#entwurf-und-spezifikation) und
[Wissenschaftliche Arbeit](#wissenschaftliche-arbeit).

## Inhaltsverzeichnis 

* [Architektur](#architektur)
* [Installation](#installation)
* [Schnellstart](#schnellstart)
* [Kommandozeile](#kommandozeile)
* [Suchreihenfolge](#suchreihenfolge)
* [Fehlermodell](#fehlermodell)
* [Tests](#tests)
* [Status und Grenzen](#status-und-grenzen)
* [Entwurf und Spezifikation](#entwurf-und-spezifikation)
* [Wissenschaftliche Arbeit](#wissenschaftliche-arbeit)
* [Erwerb](#erwerb)

## Architektur

```
  Anwendung / Sprachbindung      sl.open(...), sl_open(...)      sl.binding, sl.capi
  ---------------------------------------------------------------------------------
  Loader-Kern (identisch überall)  Auflösung, Validierung,       sl.loader, sl.search
                                   Abhängigkeiten, Init/Fini,
                                   Zyklen, Referenzzählung
  ---------------------------------------------------------------------------------
  Plattformadapter                 Linux / macOS / Windows       sl.adapters
  ---------------------------------------------------------------------------------
  Container                        Metadaten + Payload je        sl.container,
                                   Plattform/Architektur         sl.metadata
```

Zusätzlich erzeugt `sl.codegen` aus den Metadaten die Schichten für die Nutzung auf
verschiedenen Plattformen (C-Header, C-Quelle, CMake-Modul, Python-Binding,
Build-Matrix), und `sl.build` kompiliert und packt Fat-Container.

Die formale Beschreibung der Schichten (Importgraph in sieben Ebenen, Abschluss des
Laufzeitpfads, Adapter als Orakel) steht in der [wissenschaftlichen Arbeit](#wissenschaftliche-arbeit),
Kapitel 3 und 8; der Entwurf beschreibt sie in Abschnitt 5.2 von
[`proposal.md`](https://github.com/naphets86/sharedlib/blob/main/proposal.md).

## Installation

```bash
git clone https://github.com/naphets86/sharedlib.git
cd sharedlib
pip install -e ".[dev]"
```

## Schnellstart

Metadaten (`wsat.json`):

```
json
{
  "name": "wsat", "version": "1.2.0", "abi_version": 1,
  "targets": [{"platform": "linux", "arch": "x86_64"}],
  "dependencies": {},
  "exports": ["wsat_solve"],
  "signatures": {"wsat_solve": "int wsat_solve(const int *xs, unsigned int n)"},
  "init": "wsat_init", "fini": "wsat_fini"
}
```

Bauen und nutzen:

```bash
# Mit installiertem sl-CLI oder via python -m sl:
sl gen   --meta wsat.json -o gen/
sl build --meta wsat.json --source gen/wsat_sl.c --source impl.c -I gen -o wsat.sl
```

In Python laden:

```python
import ctypes
import sl

with sl.open("wsat") as lib:        # auf allen Plattformen identisch
    solve = lib.symbol("wsat_solve",
                       argtypes=[ctypes.POINTER(ctypes.c_int), ctypes.c_uint],
                       restype=ctypes.c_int)
    print(solve((ctypes.c_int * 2)(1, 2), 2))
```

Die C-artige Statusschnittstelle liefert `(status, wert, fehlerinfo)` statt Ausnahmen:
`sl_open`, `sl_symbol`, `sl_info`, `sl_close`.

## Kommandozeile

| Befehl | Zweck |
|---|---|
| `sl info DATEI.sl` | Metadaten und enthaltene Payloads anzeigen |
| `sl gen --meta M.json -o DIR` | Header, C-Quelle, CMake, Python-Binding, Build-Matrix erzeugen |
| `sl build --meta M.json --source A.c [-I DIR] [-D X=1] [--extra P:A=DATEI] -o OUT.sl` | Für das Host-Target kompilieren, vorgebaute Payloads anderer Targets ergänzen |
| `sl pack --meta M.json --payload P:A=DATEI ... -o OUT.sl` | Vorhandene Binaries zu einem Fat-`.sl` packen |
| `sl matrix --meta M.json` | Build-Matrix als JSON ausgeben |

Unterstützte Plattformen: `linux`, `macos`, `windows`.  
Unterstützte Architekturen: `x86_64`, `aarch64`, `x86`, `arm` .  
Fehler erscheinen einheitlich auf stderr als `sl: error: ...` mit Exit-Code 2 .

## Suchreihenfolge

1. Expliziter Pfad (dann ausschließlich dieser)
2. `SL_PATH` (Trennzeichen `:` unter POSIX oder `;` unter Windows; `\:` und `\\` als Escapes; Windows-Laufwerksbuchstaben wie `C:\` werden geschützt; nur absolute Einträge werden berücksichtigt)
3. Verzeichnis des Aufrufers (`requester_dir`) und dessen Unterverzeichnis `sl/`
4. Anwendungsverzeichnis (`app_dir`)
5. Systemweite Standardverzeichnisse des jeweiligen Plattformadapters

Nie durchsucht werden das aktuelle Arbeitsverzeichnis sowie `PATH`, `LD_LIBRARY_PATH`
und `DYLD_LIBRARY_PATH`. Mit `Loader(hardened=True)` wird `SL_PATH` ignoriert, und Treffer
in weltbeschreibbaren Verzeichnissen (`world-writable`) werden abgewiesen. Abhängigkeiten werden nach derselben
Reihenfolge aufgelöst.

Beweise zur Suchreihenfolge (Struktur der Kandidatenliste, Unabhängigkeit vom Arbeitsverzeichnis,
gehärteter Modus, Zerlegung von `SL_PATH`) stehen in Kapitel 6 der
[wissenschaftlichen Arbeit](#wissenschaftliche-arbeit); die Vorgabe des Entwurfs steht in
Abschnitt 5.4 von [`proposal.md`](https://github.com/naphets86/sharedlib/blob/main/proposal.md).

## Fehlermodell

`SLError` trägt `status` (`SLStatus`), `message`, `failed_name`, `searched` und
`native_error`. Statuswerte:
- `SLStatus.OK` (0)
- `SLStatus.NOT_FOUND` (1)
- `SLStatus.DEPENDENCY_MISSING` (2)
- `SLStatus.ARCH_MISMATCH` (3)
- `SLStatus.ABI_MISMATCH` (4)
- `SLStatus.INVALID_CONTAINER` (5)
- `SLStatus.SYMBOL_NOT_FOUND` (6)
- `SLStatus.INIT_FAILED` (7)
- `SLStatus.CYCLE` (8)
- `SLStatus.ACCESS_DENIED` (9)
- `SLStatus.INTERNAL` (10)

Das Fehlermodell entspricht Abschnitt 5.6 des Entwurfs
([`proposal.md`](https://github.com/naphets86/sharedlib/blob/main/proposal.md)).

## Tests

MinGW und Gcc setzen:
```bash
$env:PATH = "C:\Pfad\zu\mingw64\bin;C:\Pfad\zu\cmake\bin;" + $env:PATH
$env:CC = "gcc"
pytest
```

Tests ausführen:
```bash
pytest
```

Die meisten laufen mit einem Fake-Adapter ohne native Bibliotheken;
Tests mit Marker `native` kompilieren und laden eine echte Bibliothek und benötigen einen
C-Compiler auf einem POSIX-Host.

## Status und Grenzen

- Geprüft wurde unter Linux. Die Adapter für macOS und Windows sind über Mocks getestet, aber
  nicht auf echten Systemen.
- Die Zweigabdeckung wurde nicht gemessen; die Zeilenabdeckung lag bei 100 %.
- Der Loader hält während des Initialisierens ein reentrantes Lock.
- Signaturen für das Python-Binding unterstützen skalare C-Typen sowie `char *` und
  sonstige Zeiger (als `c_void_p`), keine Strukturen.
- Ergänzende Hinweise aus der [wissenschaftlichen Arbeit](#wissenschaftliche-arbeit), Kapitel 14
  (Befunde B1 bis B14, jeweils mit Beleg und Verbesserungsvorschlag):
  - Der Abdeckungsbericht unter [`doc/coverage`](doc/coverage/index.html) (21.10.2026, Windows-Lauf) weist
    99 % aus, mit Zweigabdeckung (`search.py`: 96 %). Er weicht von den beiden vorigen Punkten ab (B12).
  - `SL_PATH` wählt die Maskierungsregeln nach dem Inhalt (Semikolon vorhanden oder nicht); Einträge mit
    Semikolon sind nicht darstellbar, der Semikolon-Zweig ist ungetestet (B1).
  - Relative `requester_dir`/`app_dir` werden nicht normalisiert; dann hängt die Suche vom
    Arbeitsverzeichnis ab (B2).
  - Das globale Lock während des Initialisierens erlaubt einen Deadlock zwischen zwei Threads (B4).
  - Ausnahmen außer `SLError` in Hooks umgehen den Rollback (B5).
  - Abhängigkeiten stellen Reihenfolge von Init und Freigabe sicher; ob ihre nativen Symbole für die
    abhängige Bibliothek auflösbar sind, hängt vom Modus des Systemladers ab (B6, nicht ausgeführt geprüft).
  - Der Hash schützt Payloads nur gegen Zufall; der Container ist nicht kanonisch und nicht signiert (B7).
  - `sl build` kennt nur GCC/Clang-Flags und keine Angabe von Sprachstandard oder Bibliotheken (B9).

## Entwurf und Spezifikation

Der Diskussionsentwurf für das einheitliche Shared-Library-Format `.sl` liegt direkt auf oberster Ebene
des Projekts: [`proposal.md`](https://github.com/naphets86/sharedlib/blob/main/proposal.md). Er enthält die Begründung, die Zielarchitektur, die
standardisierte Ladeprozedur, die Suchordnung, das Fehlermodell, die Sicherheitsüberlegungen, einen
Fahrplan und offene Fragen. Dieses Repository ist die Referenzimplementierung der Schichten, die der Entwurf beschreibt.

| Abschnitt in [`proposal.md`](https://github.com/naphets86/sharedlib/blob/main/proposal.md) | Inhalt | Umsetzung im Paket `sl` |
|---|---|---|
| 2 | Plattformunterschiede (Endung, Binärformat, Lade-API, Sichtbarkeit, Suche, Init, Fehler) | `sl.adapters`, `sl.platform_info` |
| 5.2 | Schichten | siehe [Architektur](#architektur) |
| 5.3 | Ladeprozedur in neun Schritten | `sl.loader` |
| 5.4 | Suchordnung | `sl.search` |
| 5.5, 5.6 | API und Fehlermodell | `sl.capi`, `sl.binding`, `sl.errors` |
| 5.7 | Lebenszyklus und Nebenläufigkeit | `sl.loader` |
| 5.8 | Exportmodell | `sl.codegen` (`SL_EXPORT`), `Loader.symbol` |
| 5.9 | Konformitätssuite | `tests/` (Unit-Tests mit Fake-Adapter) |
| 6 | Metadaten und Container | `sl.metadata`, `sl.container` |
| 10 | Sicherheit | `Loader(hardened=True)`, SHA-256 je Payload |
| 12 | Beispiel Vorher/Nachher | siehe [Wissenschaftliche Arbeit](#wissenschaftliche-arbeit), Kapitel 12 |
| 13, 14 | Fahrplan, offene Fragen | siehe Kapitel 16 (Ausblick) der Arbeit |

Die Konformitätsmatrix der wissenschaftlichen Arbeit (Tabelle 4.1) stellt jede Forderung des Entwurfs dem
Quelltext gegenüber und bewertet sie als erfüllt, teilweise erfüllt, abweichend, nicht erfüllt oder fehlend.

## Wissenschaftliche Arbeit

Unter [`science/`](science/) liegt die wissenschaftliche Arbeit
**„Das einheitliche Shared-Library-Format `.sl` – Standardisierte Ladeprozedur: Formale Analyse der
Referenzimplementierung `sharedlib` und ihre Wiederverwendung in Gen-DB und Subgraph-SAT-Solver“**
(Stephan Epp, 21. Oktober 2026, 75 Seiten, LaTeX nach der Vorlage von `csubgraph.tex`).
Sie führt das Kapitel zum Laden der C/C++-Bibliothek aus der Arbeit zur Wiederverwendung des
Subgraph Algorithmus fort, verwendet den Entwurf [`proposal.md`](https://github.com/naphets86/sharedlib/blob/main/proposal.md) und weist die tragenden
Aussagen formal nach. Der Quelltext wurde für die Arbeit nur gelesen, nicht ausgeführt.

| Datei | Inhalt |
|---|---|
| [`science/sharedlib.pdf`](science/sharedlib.pdf) | Die Arbeit als PDF |
| [`science/sharedlib.tex`](science/sharedlib.tex) | Hauptdatei: Preamble, Titel, Kurzfassung, Teil I (Kapitel 1 bis 3), Literatur |
| [`science/sl_teil1.tex`](science/sl_teil1.tex) | Teil II: Anforderungen, Container, Suchordnung, Lader-Kern, Plattformadapter (Kapitel 4 bis 8) |
| [`science/sl_teil2.tex`](science/sl_teil2.tex) | Teil III: Codegenerierung, Versionen, Sicherheit, Anwendung (Kapitel 9 bis 12) |
| [`science/sl_teil3.tex`](science/sl_teil3.tex) | Teile IV und V: Berichtetes, Befunde, Zusammenfassung, Ausblick (Kapitel 13 bis 16) |

### Gliederung

| Teil | Kapitel |
|---|---|
| I Ausgangslage | 1 Einführung, 2 Plattformunterschiede und Problemlage, 3 Formale Grundlagen |
| II Das Verfahren | 4 Anforderungen und Konformitätsmatrix, 5 Das Container-Format, 6 Suchordnung, 7 Der Lader-Kern, 8 Plattformadapter und Schichtung |
| III Umfeld des Verfahrens | 9 Codegenerierung und Build, 10 Versionen: Konvexität und Komplexität, 11 Sicherheit, 12 Anwendung auf die Beispielprojekte |
| IV Prüfung | 13 Berichtete Ergebnisse, 14 Befunde und Verbesserungsvorschläge |
| V Schluss | 15 Zusammenfassung, 16 Ausblick |

### Bewiesene Aussagen (Auswahl)

| Gegenstand | Aussage |
|---|---|
| Nichtziel des Entwurfs | Kein Maschinencode-Block bedient zwei Aufrufkonventionen (Satz 2.1) |
| Container | Größenformel `18 + m + 80k + Summe der Payloads`, Rundreise `unpack(pack(M,P)) = (M,P)`, Integrität der Payloads, Nichtkanonizität (Kapitel 5) |
| Suchordnung | Struktur der Kandidatenliste, Abhängigkeit von der Umgebung nur über `SL_PATH` (und auf Windows zwei Systemvariablen), Freiheit vom Arbeitsverzeichnis unter Bedingung, erster Treffer gewinnt, gehärteter Modus fail closed, Zerlegung von `SL_PATH` (Kapitel 6) |
| Lader | Erfolg genau dann, wenn der Abhängigkeitsgraph azyklisch ist und lokale und Kantenbedingungen gelten; Init vor und Fini nach den Abhängigkeiten; Invariante der Referenzzählung; Rollback bei `SLError`; Deadlock durch das globale Lock (Kapitel 7) |
| Schichtung | Importgraph azyklisch in sieben Ebenen; Laufzeitpfad ohne Build, Codegenerierung und CLI; Adapter-Parametrizität mit benannten Ausnahmen (Kapitel 8) |
| Codegenerierung | Alle erzeugten Schichten sind reine Funktionen der Metadaten; ABI-Treue der Typabbildung unter einer Annahme über `ctypes` (Kapitel 9) |
| Versionen | Versionsbereiche sind Intervalle; die Auswahl unter mehreren Kandidaten ist NP-vollständig (Reduktion von 3-SAT); der Lader bleibt mit eindeutiger Auflösung polynomiell (Kapitel 10) |

### Befunde der Arbeit

Kapitel 14 der Arbeit nennt vierzehn Befunde mit Beleg und Vorschlag. Sie sind keine Fehlermeldungen
im strengen Sinn, sondern benennen Abweichungen vom Entwurf und Annahmen, unter denen die Beweise gelten.

| Nr. | Befund |
|---|---|
| B1 | `SL_PATH` mit zwei vom Inhalt gewählten Betriebsarten |
| B2 | Relative Verzeichnisse werden nicht normalisiert |
| B3 | Rechteprüfung im gehärteten Modus ist lückenhaft |
| B4 | Globales Lock über Init-Hooks (Deadlock möglich) |
| B5 | Ausnahmen außerhalb von `SLError` umgehen den Rollback |
| B6 | Native Abhängigkeiten und Symbolauflösung zwischen Bibliotheken |
| B7 | Container nicht kanonisch und ohne Echtheitsschutz |
| B8 | Eingabeprüfung der Metadaten (`exports` als Text) |
| B9 | Build-Werkzeug: nur GNU-Flags, keine C++-Laufzeit |
| B10 | Erzeugtes CMake-Modul setzt Variablen nicht |
| B11 | Felder und Daten ohne Wirkung (`runtime`, `flags`, unbenutzte Tabelle) |
| B12 | Dokumentationsstand (README und Abdeckungsbericht weichen ab) |
| B13 | Geteilte Handles: doppeltes `close` nimmt fremde Referenz zurück |
| B14 | Kleinere Abweichungen vom Entwurf |

### Arten von Aussagen und Kompilieren

Die Arbeit kennzeichnet vier Arten von Aussagen: *Bewiesen*, *Aus dem Quelltext gelesen*, *Berichtet*
(Angaben der README und des Abdeckungsberichts, nicht neu ermittelt) und *Offen*.

```bash
cd science
pdflatex sharedlib.tex   # zweimal ausführen, damit Verzeichnisse und Verweise stimmen
pdflatex sharedlib.tex
```

Benötigt werden eine TeX-Distribution mit `ngerman`, `lmodern`, `tikz`, `listings`, `tabularx`, `longtable`
und `microtype`. Die beigelegte PDF wurde ohne die deutsche Silbentrennung gesetzt (XeLaTeX mit Latin Modern),
weil diese Pakete in der Erzeugungsumgebung fehlten; mit `ngerman` kann der Zeilenumbruch abweichen.

## Erwerb

Der Preis für diese Software beträgt 15.455.000,00 EUR.

### Zahlungsinformationen

Name: Stephan Epp  
IBAN: DE24 5003 1900 0012 5603 20
BIC: BBVADEFFXXX
