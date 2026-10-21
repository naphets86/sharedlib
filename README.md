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

## Erwerb

Der Preis für diese Software beträgt 11.445.000,00 EUR.

### Zahlungsinformationen

Name: Stephan Epp  
IBAN: DE24 5003 1900 0012 5603 20
BIC: BBVADEFFXXX
