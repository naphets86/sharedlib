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

**Neu:** Die [zweite Fassung der wissenschaftlichen Arbeit](#wissenschaftliche-arbeit-zweite-fassung) (18 Kapitel, 15 Befunde, eigene Prüfläufe, sehr ausführlicher Ausblick) liegt als einzelne LaTeX-Datei [`science/sharedlib.tex`](science/sharedlib.tex) mit [PDF](science/sharedlib.pdf) vor; die Prüfskripte stehen unter [`science/pruef/`](science/pruef/).

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
* [Wissenschaftliche Arbeit, zweite Fassung](#wissenschaftliche-arbeit-zweite-fassung)
  * [Fragestellung](#fragestellung)
  * [Gliederung der zweiten Fassung](#gliederung-der-zweiten-fassung)
  * [Das formale Modell](#das-formale-modell)
  * [Bewiesene Aussagen (Auswahl)](#bewiesene-aussagen-auswahl-1)
  * [Befunde der zweiten Fassung (B1 bis B15)](#befunde-der-zweiten-fassung-b1-bis-b15)
  * [Prüfung und Messung](#prüfung-und-messung)
  * [Konformität von Proposal und Implementierung](#konformität-von-proposal-und-implementierung)
  * [Anwendung auf Gen-DB und Subgraph-SAT-Solver](#anwendung-auf-gen-db-und-subgraph-sat-solver)
  * [Ausblick (Kapitel 17)](#ausblick-kapitel-17)
  * [Prüfskripte reproduzieren](#prüfskripte-reproduzieren)
  * [Offene Punkte der zweiten Fassung](#offene-punkte-der-zweiten-fassung)
  * [Kompilieren der zweiten Fassung](#kompilieren-der-zweiten-fassung)
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
- Ergänzung aus der zweiten Fassung der Arbeit (Kapitel 13 bis 15, mit eigenen Prüfläufen unter Linux, Details im Abschnitt [Prüfung und Messung](#prüfung-und-messung)): Die Testsuite des Repositories wurde dabei nicht ausgeführt; die Angabe „126 Tests“ ist nicht nachgeprüft. Es gibt elf Testdateien mit 85 Testfunktionen (statisch gezählt, parametrisierte Fälle nicht eingerechnet). Der Abdeckungsbericht weist 99,5 % Anweisungs- und 98 % Zweigabdeckung aus. Fünfzehn Befunde mit Beleg und Verbesserung stehen in [Befunde der zweiten Fassung](#befunde-der-zweiten-fassung-b1-bis-b15); die drei schwersten betreffen die Sperre während `init` (B5), unaufgelöste native Symbolabhängigkeiten (B7) und die fehlende Authentizität der Metadaten (B10). Die Nummerierung weicht von der Liste oben (erste Fassung) ab.

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

## Wissenschaftliche Arbeit, zweite Fassung

> **Hinweis zu den Fassungen.** Der Abschnitt [Wissenschaftliche Arbeit](#wissenschaftliche-arbeit) oben
> beschreibt die **erste Fassung** (75 Seiten, vier Dateien `sl_teil*.tex`, Befunde B1 bis B14,
> Kapitelnummern 1 bis 16). Die **zweite Fassung** unten ist eine Neuerarbeitung auf Grundlage der
> Vorarbeit `csubgraph` und des Entwurfs `proposal.md`: 18 Kapitel in einer einzigen LaTeX-Datei, 106 Seiten
> (in der mitgelieferten Satzumgebung), 15 Befunde B1 bis B15 mit **anderer Nummerierung**, eigene
> Prüfläufe am Quelltext (Skripte `pruef1.py` bis `pruef7.py`) und ein sehr ausführlicher Ausblick.
> Kapitel- und Befundnummern in den älteren Abschnitten dieser README beziehen sich auf die erste Fassung;
> die Nummern in diesem Abschnitt auf die zweite.

**Titel:** „Einheitliche Shared Libraries (`.sl`) – Wiederverwendung des Ladeverfahrens. Von den Ladeverfahren in
Gen-DB und `subgraph-sat-solver-econ` über das Proposal zur Referenzimplementierung `sharedlib`: formales Modell,
Beweise, Prüfung und Ausblick“ (Stephan Epp, 21. Oktober 2026).

Die Arbeit nimmt das Kapitel zum Laden der C/C++-Bibliothek aus der Vorarbeit
([`csubgraph`](https://github.com/naphets86/csubgraph), dort Kapitel 13) wieder auf, führt es anhand des Proposals und
dieser Referenzimplementierung weit aus und belegt alle tragenden Aussagen formal. Sie folgt der Vorlage
`csubgraph.tex` (Teile, Theorem-Umgebungen `definition`, `beispiel`, `satz`, `lemma`, `bemerkung`, `korollar`,
Kurzfassung, Inhaltsverzeichnis).

| Datei | Inhalt |
|---|---|
| `science/sharedlib.tex` | Die gesamte Arbeit als **eine** kompilierbare Datei (Teile I bis V, Anhänge, Literatur) |
| `science/sharedlib.pdf` | Die Arbeit als PDF (106 Seiten) |
| `science/pruef/pruef1.py` bis `pruef7.py` | Prüfskripte der Arbeit (Zufalls-, Modell- und Reproduktionsläufe, Messung) |

### Fragestellung

Die Arbeit beantwortet zehn Fragen: Welche Plattformunterschiede betreffen das Laden, und welche davon sind
Plattformcode ohne Fachlogik? Was lässt sich vereinheitlichen, und was beweisbar nicht? Wie lässt sich die
Ladeprozedur als mathematisches Modell fassen? Welche Garantien folgen für Namensauflösung, Container,
Versionsbereiche und den Loader-Kern? Wie weit ist der Kern vom Betriebssystem unabhängig? Was leisten
Codegenerierung und Build? Was ändert sich in Gen-DB und `subgraph-sat-solver-econ`, und was kostet es? Wo
weicht die Implementierung vom Proposal ab?

### Gliederung der zweiten Fassung

| Teil | Kapitel |
|---|---|
| I Ausgangslage | 1 Einführung, 2 Formale Grundlagen, 3 Projektlandschaft und Wiederverwendungsformen |
| II Das Problem | 4 Der Ist-Zustand des Ladens, 5 Grenzen der Vereinheitlichung |
| III Das Konzept: Modell und Beweise | 6 Das formale Modell der Ladeprozedur, 7 Namensauflösung und Suchordnung, 8 Container, Metadaten und Versionsbereiche, 9 Der Loader-Kern, 10 Plattformadapter, Binding und Schnittstelle, 11 Codegenerierung und Build |
| IV Prüfung und Anwendung | 12 Anwendung auf Gen-DB und Subgraph-SAT-Solver, 13 Prüfung und Messung, 14 Befunde, 15 Konformität von Proposal und Implementierung |
| V Schluss | 16 Zusammenfassung, 17 Ausblick |
| Anhang | A Beweisindex (jede Aussage mit Quelltextbezug und Prüfung), B Prüfskripte |

### Das formale Modell

Das Modell besteht aus einem Dateisystem als partieller Abbildung von Pfaden auf Bytes, der Umgebung, einer
Konfiguration `C` und einem Zustand `Γ = (L, S)` aus der Ladetabelle `L` (Schlüssel auf Knoten
`(μ, d, rc, ν)`: Metadaten, Abhängigkeiten, Referenzzähler, native Referenz) und dem Stapel `S` der gerade ladenden
Bibliotheken. Der Plattformadapter ist ein Parameter mit den Operationen `lookup`, `map_payload`, `system_dirs`,
`unmap`. Eine Invariante aus vier Teilen (I1 bis I4) hält fest, dass der Referenzzähler jedes Knotens der Summe aus
Verweisen von Clients, von abhängigen Knoten und von noch laufenden Öffnungen („unterwegs“) entspricht. Die Sätze
über Rollback, Lebenszyklus und Fehlerursache sind Folgerungen aus dieser Invariante.

### Bewiesene Aussagen (Auswahl)

Das Beweisverzeichnis im Anhang A listet jede Aussage mit Quelltextbezug und stützender Prüfung. Eine Auswahl:

| Gegenstand | Aussage |
|---|---|
| Grenzen | Maschinencode lässt sich zwischen Aufrufkonventionen nicht vereinheitlichen (Windows x64 `rcx` gegen System V `rdi`); Typbreiten (LP64, LLP64, ILP32) verlangen feste Breiten an der Schnittstelle |
| Suche | Die Kandidatenliste hat eine feste Struktur; **erster Treffer gewinnt**; die Suche hängt unter einer Bedingung **nicht vom Arbeitsverzeichnis** ab; der gehärtete Modus schließt `SL_PATH` aus (fail closed) |
| `SL_PATH` | **Exakte Rundreisebedingung**: `Dec(Enc(L)) = L` genau dann, wenn kein Eintrag die Laufwerksform `X:\…` hat und kein Eintrag das Trennzeichen enthält; sonst gibt es Gegenbeispiele |
| Versionen | Versionsbereiche über `N³` (lexikographisch) sind **konvex**; die kleinste erfüllende Version ist die untere Grenze, falls der Bereich nicht leer ist |
| Container | `unpack ∘ pack = id` (Rundreise), Injektivität von `pack`, Integrität der Payloads durch SHA-256, **keine Authentizität** der Metadaten, Totalität des Lesers (nur `SLError` oder Erfolg), Nichtkanonizität (angehängte Bytes ändern nichts) |
| Loader | **Terminierung** mit höchstens `|E_r| + 1` Aufrufen; **Korrektheit und Vollständigkeit der Zykluserkennung**; Invariante der Referenzzählung; **Atomarität (Rollback)** eines fehlgeschlagenen Öffnens; Init nach Abhängigkeiten und Fini vor ihnen (Abhängige zuerst entladen); Fehlerkausalität (`failed_name` nennt den Verursacher für fehlende Abhängigkeiten) |
| Adapter | Der Kern ist **adapterparametrisch**, aber nicht hostunabhängig (Pfadkonvention des Hosts, Dateisystem); Öffnen kostet linear in der Dateigröße; der Aufruf gebundener Funktionen hat keinen Zusatzaufwand |
| Codegenerierung | Signaturparser korrekt für die Teilsprache der Metadaten; Typabbildung; Build-Matrix; Fat-Container |
| Anwendung | Migrationssatz: Unter vier Bedingungen M1 bis M4 führen `ctypes.CDLL(p)` und `sl.open(n)` denselben nativen Code aus; Speicherbedarf eines Prozess-Pools |
| Ausblick | Korrektheit einer SAT-Kodierung der Abhängigkeitsauflösung (vollständig bewiesen); Authentizität des Containers mit Merkle-Struktur (Beweisskizze) |

Insgesamt enthält die Arbeit mehr als fünfzig nummerierte Sätze, Lemmata und Korollare. Jede Aussage trägt eine
Kennzeichnung: *bewiesen*, *aus dem Quelltext gelesen*, *geprüft* oder *offen* (im PDF rot).

### Befunde der zweiten Fassung (B1 bis B15)

Jeder Befund hat Beobachtung, Beleg (Satz, Quelltext oder Reproduktion), Folge und Verbesserungsvorschlag
(Kapitel 14). Die Schwere ist eine Einschätzung des Verfassers.

| Nr. | Befund | Beleg | Schwere |
|---|---|---|---|
| B1 | `SL_PATH`: Die Laufwerksheuristik macht die Rundreise formabhängig | bewiesen, reproduziert | mittel |
| B2 | `SL_PATH`: Der Semikolonmodus ist nicht rundreisefähig; der Modus hängt vom Inhalt ab | bewiesen, reproduziert | mittel |
| B3 | Versionsbereiche des Proposals (`>=1.2,<2`) werden abgelehnt (dreiteilige Versionen verlangt) | geprüft | niedrig |
| B4 | Die Suche hängt vom Host ab (`isabs`, Arbeitsverzeichnis bei relativen Pfaden) | bewiesen, reproduziert | mittel |
| B5 | Die Sperre während `init` blockiert nebenläufiges `open` (**Widerspruch zum Proposal**) | reproduziert | hoch |
| B6 | `symbol` und `close` sind nicht atomar verschränkt | aus dem Quelltext | mittel |
| B7 | **Native Symbolabhängigkeit** zwischen Bibliotheken bleibt unaufgelöst | reproduziert | hoch |
| B8 | Instanz je Datei statt je Name; doppeltes `close` desselben Handles wird angenommen | reproduziert | mittel |
| B9 | Das Metadatenfeld `runtime` (`"external"`) hat im Loader keine Semantik | aus dem Quelltext | niedrig |
| B10 | Metadaten **nicht authentifiziert**; `failed_name` leer bei Containerfehlern von Abhängigkeiten; Rekursionsfehler bei tiefem JSON; nichtkanonische Container | bewiesen, reproduziert | hoch |
| B11 | Temporäre Dateien bleiben bei Prozessende ohne `close` liegen | reproduziert | mittel |
| B12 | Init/Fini-Haken sind Symbole der Bibliothek, aber nicht auffindbar (Spezifikationslücke) | reproduziert | niedrig |
| B13 | Codegenerator: `long` nicht zurückgewiesen, Warnungen (`-Wunused-const-variable`), Build-Matrix mit gleichem Dateinamen für verschiedene Ziele, Lücken im CMake-Modul | reproduziert | mittel |
| B14 | Binding: Funktionsobjekte nicht stabil (`L["f"] is L["f"]` ist falsch), `argtypes` wird geteilt, Namen mit doppelten Unterstrichen nur per Elementzugriff | reproduziert | niedrig |
| B15 | Der **Legacy-Modus** des Proposals (gewöhnliche `.dll`/`.so`/`.dylib` über dieselbe API) fehlt | aus dem Quelltext | mittel |

Hoch gewichtet sind B5, B7 und B10: Korrektheit unter Nebenläufigkeit, das Kernversprechen der
Abhängigkeitsauflösung und die Vertrauensgrenze. Die übrigen Befunde sind lokal behebbar; keine der
Verbesserungen ändert das Modell. Kernideen der Verbesserungen:

- **B1/B2/B4:** eine einzige Kodierung für alle Plattformen mit Fluchtzeichen (`\\` für `\`, `\:` für das
  Trennzeichen), keine Laufwerksheuristik; dann gilt `Dec ∘ Enc = id` ohne Vorbedingung. Absolutheit wird nach der
  Konvention des Ziels entschieden, nicht des Hosts.
- **B5:** Status je Schlüssel (`absent`, `init`, `ready`, `fini`) und Bedingungsvariable; `init` läuft **ohne**
  globale Sperre; Zyklen über zwei Threads brauchen eine globale Ordnung (Auflösung der gesamten
  Abhängigkeitsmenge vor jedem `init`).
- **B7:** Variante V2: alle Payloads einer Abhängigkeitsgruppe in **ein** Verzeichnis mit den Namen extrahieren,
  die der native Lader erwartet (alternativ `RTLD_GLOBAL` oder ein eigener Abbilder).
- **B10:** Hash über Kopf, Metadaten, Tabelle und Payloads (Merkle-Struktur), Signatur über die Wurzel,
  Tiefenschranke beim Parsen, Kanonizität erzwingen (Länge gleich Dateigröße).

### Prüfung und Messung

Alle Läufe geschahen unter Linux (Python 3.13, GCC 13.3); Zufallsprüfungen haben feste Startwerte.

| Nr. | Gegenstand | Ergebnis |
|---|---|---|
| P1 | `SL_PATH`-Rundreise | 300 000 zufällige Listen, 0 Abweichungen von der Bedingung des Satzes |
| P2, P2b | Versionsbereiche | 3 000 beziehungsweise 20 000 Zufallsbereiche, 0 Verletzungen (Konvexität, kleinste Version) |
| P3 | Container-Rundreise | 2 000 Zufallscontainer, `unpack ∘ pack = id` |
| P3b | Bitänderungen | alle 80 Änderungen im Datenbereich erkannt; bei Kopf, Metadaten und Tabelle 4 von 439 als andere Metadaten akzeptiert |
| P3c, P3d | Totalität, Kanonizität | 20 000 Mutationen nur `SLError` oder Erfolg; `RecursionError` bei 100 000 Klammern; angehängte Bytes ohne Wirkung |
| P4 | Signaturparser | 100 000 Signaturen, 0 Abweichungen |
| P5 | Modellläufe des Loaders | 3 000 Läufe mit zufälligen Graphen (Zyklen, defekte Dateien): 12 181 erfolgreiche und 4 621 gescheiterte Öffnungen, 22 559 Invariantenprüfungen **ohne Verletzung**, Rollback in 4 621 von 4 621 Fällen |
| P6 | Adapterzugriffe | statische Analyse des Syntaxbaums von `loader.py` und `search.py` bestätigt die Parametrizität |

**Kosten des Öffnens** (gemessen in drei Läufen, Median von je 300 Wiederholungen; Bibliotheken von 15 KiB bis
4 MiB): `ctypes.CDLL` ist von der Dateigröße unabhängig (etwa 34 bis 60 µs); `sl.open` wächst linear mit der
Größe, `t(s) ≈ a + b·s` mit `a = 0,16 bis 0,39 ms` und `b = 1,0 bis 3,4 ms/MiB` (R² ≥ 0,999 in jedem Lauf, die
Steigung streut zwischen den Läufen um den Faktor 3,4). Der Aufruf einer gebundenen Funktion kostet nicht mehr
(Größenordnung 300 bis 650 ns, ohne gleichbleibenden Unterschied). Für Bibliotheken, die einmal je Prozess geöffnet
und danach oft aufgerufen werden, ist das gering; für Dienste, die je Anfrage öffnen, wäre es der dominierende
Posten.

**Grenzen der Prüfung:** Nur Linux; die Adapter für macOS und Windows sind nicht ausgeführt. Die Modellläufe
nutzen einen Fake-Adapter (wie die Suite des Repositories). Die Testsuite des Repositories wurde für die Arbeit
**nicht ausgeführt** (`pytest` ließ sich in der Arbeitsumgebung nicht installieren); die 126 Tests des Abzeichens
oben sind nicht nachgeprüft. Der mitgelieferte Abdeckungsbericht (Windows-Lauf) weist 780 Anweisungen mit 4 nicht
erreichten und 200 Zweige mit 4 teilweise gedeckten aus; das entspricht 99,5 % Anweisungs- und 98 %
Zweigabdeckung und weicht von der Angabe „Zeilenabdeckung 100 %, Zweigabdeckung nicht gemessen“ im Abschnitt
[Status und Grenzen](#status-und-grenzen) ab.

### Konformität von Proposal und Implementierung

Kapitel 15 stellt 17 Zusagen des Proposals der Implementierung gegenüber: **5 erfüllt**, **10 teilweise erfüllt**
(jeweils mit Befund), **2 fehlend** (Legacy-Modus, entkoppelte Initialisierung).

| Zusage des Proposals | Stand |
|---|---|
| Container mit Metadaten, Tabelle, SHA-256 je Payload | teilweise (Metadaten nicht gehasht, B10) |
| Feste Suchordnung, nie Arbeitsverzeichnis, `PATH`, `LD_LIBRARY_PATH` | teilweise (Host-Abhängigkeit, B4) |
| Gehärteter Modus fail closed | teilweise (Eigentumsprüfung fehlt) |
| Abhängigkeiten vor der Bibliothek auflösen | teilweise (native Symbole nicht, B7) |
| Zyklen erkennen | erfüllt |
| Referenzzählung, Entladen beim letzten `close` | teilweise (doppeltes `close`, B8) |
| Atomares Öffnen | erfüllt |
| Init: Abhängigkeiten zuerst, Fini zuletzt | erfüllt |
| `failed_name` nennt den Verursacher | teilweise (B10) |
| Nebenläufige Öffnungen sperren sich nicht bei `init` | **fehlt** (B5) |
| Eine Instanz je Bibliothek | teilweise (je Datei, B8) |
| Versionsbereiche `>=1.2,<2` | teilweise (B3) |
| Feste Typbreiten in der Schnittstelle | teilweise (B13) |
| Codegenerierung (Header, C-Quelle, CMake, Binding, Matrix) | teilweise (B13) |
| Plattformadapter austauschbar | erfüllt (Linux belegt) |
| Legacy-Modus | **fehlt** (B15) |
| Keine Laufzeitabhängigkeiten | erfüllt |

### Anwendung auf Gen-DB und Subgraph-SAT-Solver

Kapitel 12 vergleicht die zwei Ladeverfahren der Projekte (vier Dateinamen je `sys.platform`, `add_dll_directory`,
Makro `CSUB_EXPORT`, statisch gelinkte MinGW-Laufzeit) mit der einheitlichen Schicht. Kern ist der
**Migrationssatz**: Erfüllt die Migration M1 bis M4, so führen `CDLL(p)` und `sl.open(n)` denselben nativen Code aus.

- **M1** Der Payload für das Ziel des Hosts im Container ist byteweise gleich der bisherigen Bibliothek.
- **M2** Der Payload hängt nicht von seinem eigenen Ablageort ab (kein `$ORIGIN` im `RUNPATH`, kein `@loader_path`).
- **M3** Der Payload braucht von anderen Bibliotheken nur solche, die das System des Hosts findet.
- **M4** Die Suchordnung findet den Container am vorgesehenen Ort.

Dazu kommen ein Zählsatz für Testfälle (Plattformen mal Architekturen mal Fehlerklassen), ein Speichermodell für
den Prozess-Pool von Gen-DB (`N · s` bei getrennter Extraktion je Prozess) und ein Migrationsplan mit
Abnahmekriterien. Fünf neue Wiederverwendungen **W19 bis W23** ergänzen die Systematik der Vorarbeit (W1 bis
W18); sie sind Kandidaten, die Migration ist nicht durchgeführt.

### Ausblick (Kapitel 17)

Der Ausblick leitet aus Befunden, offenen Stellen und Entwurfsfragen ein Arbeitsprogramm in vier Stufen ab
(Aufwandsschätzungen des Verfassers):

| Stufe | Vorhaben | Aufwand |
|---|---|---|
| A | Befunde B1 bis B15 beheben, je ein Regressionstest; Testsuite ausführen; Windows und macOS prüfen | Tage bis Wochen |
| B | Verbessertes Sperrprotokoll (B5) mit Neubeweis und Modellprüfung; Konformitätssuite aus dem Modell; native Abhängigkeiten lösen (B7); authentifizierter Container mit Signaturen (B10) | Wochen |
| C | Resolver mit SAT oder PubGrub; Loader-Kern in C oder Rust; Bindings für weitere Sprachen; mechanisierte Beweise (Coq, Isabelle, TLA⁺) | Monate |
| D | Eigener Abbilder für ELF, PE und Mach-O; Standardisierung und Governance | Jahre |

Wichtige Linien:

- **Mechanisierte Beweise:** Zustandsmaschine in TLA⁺ oder Alloy (erschöpfende Prüfung bis zu einer Schranke),
  Beweisassistent für beliebig große Graphen (vier Beweisverpflichtungen: Sicherheit, Lebendigkeit, Atomarität,
  Ordnung), Verfeinerung zu einem verifizierten Kern in Rust oder C, dauerhaftes Fuzzing des Container-Lesers.
- **Spezifikation und Konformitätssuite:** normative Fassung in drei Schichten (Format, Verfahren, Schnittstelle);
  Testvektoren aus dem Modell, die jede Implementierung einliest; Klärung der Identität einer Instanz (Datei,
  Name oder Inhaltshash).
- **Laden:** native Abhängigkeiten (drei Varianten V1 bis V3), inhaltsadressierte gemeinsame Ablage, Laden ohne
  Extraktion über `memfd_create` und seitenausgerichtete Payloads, eigener Abbilder, Threads und Entladen,
  C++-Ausnahmen über die Grenze.
- **Nebenläufigkeit:** Protokoll ohne Sperre während `init` mit Beweisverpflichtungen, feinere Sperren,
  Linearisierbarkeit.
- **Sicherheit:** Merkle-Struktur und Signatur über den ganzen Container, gehärteter Modus mit Eigentum und
  Rechten (TOCTOU-sicher über Dateideskriptoren), Isolation (Prozess, Sandbox, WebAssembly), reproduzierbare
  Builds und SBOM.
- **Abhängigkeitsauflösung:** SAT-Kodierung mit bewiesener Korrektheit, kompaktere Ordnungskodierung aufgrund der
  Konvexität der Versionsbereiche, Anschluss an die Subgraph-SAT-Kette der Vorarbeit.
- **Weitere Sprachen und Betrieb:** C++, Rust, Go, Java, C#; WebAssembly-Komponenten; Build-Matrix mit eigenem
  Ausgabepfad je Ziel; Anschluss an Paketverwaltungen (PyPI, Conan, vcpkg, Cargo, OCI).
- **Standardisierung:** Referenzimplementierung mit offener Spezifikation, Zweitimplementierung, Regeln für
  Änderungen, Lizenz und Medientyp; jeder Änderungsvorschlag nennt, welche Sätze des Modells er berührt.
- **Bedrohungen der Gültigkeit:** Modell gegen Wirklichkeit, nur eine Plattform, ein Prüfer, Annahmen des
  Adaptervertrags, kleine Stichproben, fehlender Wortlaut des Vorarbeits-Kapitels.

Der empfohlene nächste Schritt ist ein Änderungssatz aus drei Teilen: (1) Container mit Hash über alle Teile und
erzwungener Kanonizität (B10), solange es kaum Container gibt, (2) Pfadkodierung mit Fluchtzeichen (B1, B2),
(3) die Testvektoren aus P3 und P5 als Dateien für künftige Implementierungen.

### Prüfskripte reproduzieren

Die Skripte benutzen nur die Standardbibliothek und das Paket `sl`. Aufruf aus dem Verzeichnis der Skripte, mit
isoliertem Interpreter, damit keine Datei des Arbeitsverzeichnisses importiert wird:

```bash
python3 -I pruefN.py <Pfad zu sharedlib/src>
```

| Skript | Inhalt |
|---|---|
| `pruef1.py` | Pfadkodierung (P1), Versionen (P2, P2b), Container (P3 bis P3d), `ctypes`-Zwischenspeicher |
| `pruef2.py` | modellbasierter Loader-Test (P5), Parametrizität (P6), Messung der Öffnungskosten |
| `pruef3.py` | Diamant, doppeltes `close`, Verlust von Handles |
| `pruef4.py` | Signaturparser (P4), native Abhängigkeit, Abdeckung, Testzählung |
| `pruef5.py` | doppeltes `close`, `failed_name`, Verklemmung |
| `pruef6.py` | Codegenerator: Warnungen, Matrix, Ziele |
| `pruef7.py` | Versionssatz Teil (b) |

Die Läufe sind mit festen Startwerten wiederholbar; Laufzeiten und Messwerte hängen von der Maschine ab.

### Offene Punkte der zweiten Fassung

- Der Wortlaut von Kapitel 13 der Vorarbeit (Datei `p3.tex`) lag bei der Erstellung nicht vor; das Kapitel wurde
  aus dem Proposal rekonstruiert. Der Abgleich steht aus.
- Die Testsuite dieses Repositories (126 Tests laut Abzeichen) wurde nicht ausgeführt.
- Windows und macOS wurden nicht getestet; die Quellen von Gen-DB, `subgraph-sat-solver-econ` und `csubgraph`
  wurden nicht erneut geprüft, ihre Angaben stammen aus der Vorarbeit.
- Das Protokoll von B5 braucht einen Neubeweis der Invariante.
- Die Messungen stammen aus drei Läufen mit großer Streuung und sind Größenordnungen.

### Kompilieren der zweiten Fassung

```bash
cd science
pdflatex sharedlib.tex   # dreimal ausführen, damit Verzeichnisse und Verweise stimmen
pdflatex sharedlib.tex
pdflatex sharedlib.tex
```

Benötigt werden eine TeX-Distribution mit `ngerman`, `lmodern`, `tikz`, `listings`, `tabularx`, `longtable`,
`booktabs`, `float`, `enumitem` und `microtype`. Die beigelegte PDF wurde mit XeLaTeX und Ersatzschriften (DejaVu)
ohne deutsche Silbentrennung gesetzt, weil `ngerman` und `lmodern` in der Erzeugungsumgebung fehlten; mit
`ngerman` kann der Zeilenumbruch abweichen.

## Erwerb

Der Preis für diese Software beträgt 15.455.000,00 EUR.

### Zahlungsinformationen

Name: Stephan Epp  
IBAN: DE24 5003 1900 0012 5603 20
BIC: BBVADEFFXXX
