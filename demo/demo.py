#!/usr/bin/env python3
"""Demo der sl-Kommandozeile: stellt jeden Befehl mit Erklaerung dar.

Diese Demo zeigt nur an, was die Befehle tun. Sie wurde vom Autor NICHT
ausgefuehrt oder getestet (Wunsch: nur Darstellung). Rueckmeldungen der
Befehle werden unveraendert angezeigt; schlaegt ein Schritt fehl, wird der
Fehler dargestellt und die Demo laeuft weiter.

Verwendung:
    python demo.py                 # alle Schritte nacheinander
    python demo.py --list          # Schritte auflisten
    python demo.py --step gen      # nur einen Schritt (mehrfach moeglich)
    python demo.py --dry-run       # nur die Befehle zeigen, nichts ausfuehren
    python demo.py --no-color      # ohne ANSI-Farben
    python demo.py --pause         # nach jedem Schritt auf Enter warten

Voraussetzung: das Paket sl ist installiert (pip install -e <sharedlib>),
und ein C-Compiler (gcc/clang) steht fuer die Schritte build und pack bereit.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import shlex
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

ROOT = Path(__file__).resolve().parent
GEN = ROOT / "gen"
OUT = ROOT / "out"
META = ROOT / "wsat.json"
META_FAT = ROOT / "wsat_fat.json"
IMPL = ROOT / "demo" / "src" / "impl.c"

# --------------------------------------------------------------------------
# Darstellung
# --------------------------------------------------------------------------
USE_COLOR = sys.stdout.isatty()


def c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def bold(t): return c("1", t)
def dim(t): return c("2", t)
def red(t): return c("31", t)
def green(t): return c("32", t)
def yellow(t): return c("33", t)
def blue(t): return c("34", t)
def cyan(t): return c("36", t)


WIDTH = min(100, os.get_terminal_size().columns) if sys.stdout.isatty() else 100


def banner(title: str, subtitle: str = "") -> None:
    line = "=" * WIDTH
    print()
    print(cyan(line))
    print(cyan("  ") + bold(title))
    if subtitle:
        print(cyan("  ") + dim(subtitle))
    print(cyan(line))


def section(title: str) -> None:
    print()
    print(bold(blue(f"-- {title} ")) + blue("-" * max(0, WIDTH - len(title) - 4)))


def note(text: str) -> None:
    for line in textwrap.wrap(text, WIDTH - 4):
        print("  " + line)


def table(rows: List[List[str]], header: List[str]) -> None:
    widths = [max(len(str(r[i])) for r in rows + [header]) for i in range(len(header))]
    def fmt(r): return "  " + "  ".join(str(x).ljust(w) for x, w in zip(r, widths))
    print(bold(fmt(header)))
    print("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        print(fmt(r))


def show_file(path: Path, language: str = "") -> None:
    print(dim(f"  --- {path.relative_to(ROOT)} ---"))
    text = path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        print(dim(f"  {i:3d} | ") + line)


def show_tree(path: Path) -> None:
    if not path.exists():
        print(dim(f"  ({path.name}/ existiert nicht)"))
        return
    for p in sorted(path.rglob("*")):
        rel = p.relative_to(path)
        depth = len(rel.parts) - 1
        size = f"  {p.stat().st_size:>8d} B" if p.is_file() else ""
        print("  " + "  " * depth + ("- " if p.is_file() else "+ ") + str(rel.name) + dim(size))


@dataclass
class Result:
    code: int
    out: str
    err: str
    seconds: float


def run(cmd: List[str], dry: bool) -> Optional[Result]:
    """Befehl mit Prompt-Zeile anzeigen und ausfuehren (ausser bei --dry-run)."""
    shown = " ".join(shlex.quote(x) for x in cmd)
    print()
    print(green("  $ ") + bold(shown))
    if dry:
        print(dim("  (Trockenlauf: nicht ausgefuehrt)"))
        return None
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    except FileNotFoundError as e:
        print(red(f"  Programm nicht gefunden: {e.filename}"))
        return Result(127, "", str(e), 0.0)
    dt = time.perf_counter() - t0
    for label, stream, colour in (("stdout", p.stdout, lambda s: s), ("stderr", p.stderr, red)):
        if stream.strip():
            print(dim(f"  [{label}]"))
            for line in stream.rstrip().splitlines():
                print("    " + colour(line))
    status = green("Exit-Code 0") if p.returncode == 0 else red(f"Exit-Code {p.returncode}")
    print(f"  {status}  {dim(f'({dt * 1000:.0f} ms)')}")
    return Result(p.returncode, p.stdout, p.stderr, dt)


def sl(*args: str) -> List[str]:
    """sl-Aufruf ueber den aktuellen Interpreter: python -m sl ..."""
    return [sys.executable, "-m", "sl", *args]


def host_target() -> str:
    system = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}.get(platform.system(), "linux")
    machine = platform.machine().lower()
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64",
            "i386": "x86", "i686": "x86", "x86": "x86"}.get(machine, machine)
    return f"{system}:{arch}"


# --------------------------------------------------------------------------
# Schritte
# --------------------------------------------------------------------------
def step_intro(dry: bool) -> None:
    banner("sl - Kommandozeilen-Demo",
           "Container, Metadaten, Codegenerierung, Build, Pack, Info, Matrix")
    note("Diese Demo fuehrt durch alle Befehle der sl-Kommandozeile am Beispiel der "
         "Bibliothek 'wsat'. Jeder Schritt zeigt die Eingaben, den Befehl und die Ausgabe.")
    section("Befehlsuebersicht")
    table([
        ["sl info DATEI.sl", "Metadaten und enthaltene Payloads anzeigen"],
        ["sl gen --meta M.json -o DIR", "Header, C-Quelle, CMake, Python-Binding, Build-Matrix erzeugen"],
        ["sl build --meta M.json --source A.c [-I DIR] [-D X=1] [--extra P:A=DATEI] -o OUT.sl",
         "Fuer das Host-Target kompilieren, vorgebaute Payloads ergaenzen"],
        ["sl pack --meta M.json --payload P:A=DATEI ... -o OUT.sl", "Vorhandene Binaries zu einem Fat-.sl packen"],
        ["sl matrix --meta M.json", "Build-Matrix als JSON ausgeben"],
    ], ["Befehl", "Zweck"])
    print()
    note("Plattformen: linux, macos, windows.  Architekturen: x86_64, aarch64, x86, arm.  "
         "Fehler erscheinen einheitlich als 'sl: error: ...' auf stderr mit Exit-Code 2.")
    section("Dieser Rechner")
    table([[platform.system(), platform.machine(), sys.version.split()[0], host_target()]],
          ["System", "Architektur", "Python", "Host-Target (Plattform:Arch)"])


def step_meta(dry: bool) -> None:
    banner("Schritt 1: Die Metadaten", "Eine JSON-Datei beschreibt die Bibliothek")
    show_file(META)
    section("Felder")
    table([
        ["name / version", "Name und dreiteilige Version (Haupt.Neben.Fix)"],
        ["abi_version", "Version der binaeren Schnittstelle; der Loader vergleicht sie"],
        ["targets", "Plattform/Architektur-Paare, fuer die Payloads existieren"],
        ["dependencies", "Abhaengigkeiten: Name -> Versionsbereich (hier leer)"],
        ["exports", "Liste der exportierten Symbole"],
        ["signatures", "C-Signaturen; daraus entsteht das Python-Binding"],
        ["init / fini", "Namen der Haken beim Laden und Entladen (optional)"],
    ], ["Feld", "Bedeutung"])
    section("Die Datei auf Gueltigkeit lesen (nur Python, ohne sl)")
    data = json.loads(META.read_text(encoding="utf-8"))
    print(f"  Schluessel: {', '.join(data)}")
    print(f"  Exporte   : {', '.join(data['exports'])}")
    print(f"  Ziele     : {', '.join(t['platform'] + ':' + t['arch'] for t in data['targets'])}")


def step_gen(dry: bool) -> None:
    banner("Schritt 2: sl gen", "Aus den Metadaten entstehen die Schichten fuer die Nutzung")
    note("Der Generator schreibt C-Header (mit SL_EXPORT), C-Quelle (Tabelle der Exporte), "
         "ein CMake-Modul, das Python-Binding und die Build-Matrix in das Zielverzeichnis. "
         "Alles sind reine Funktionen der Metadaten: gleiche Metadaten, gleiche Dateien.")
    run(sl("gen", "--meta", str(META), "-o", str(GEN)), dry)
    section("Erzeugte Dateien")
    show_tree(GEN)
    for pattern in ("*.h", "*.cmake", "*binding*.py", "*matrix*.json"):
        for f in sorted(GEN.glob(pattern)):
            print()
            show_file(f)
            break


def step_matrix(dry: bool) -> None:
    banner("Schritt 3: sl matrix", "Build-Matrix: ein Eintrag je Ziel")
    note("Die Matrix nennt fuer jedes deklarierte Ziel, was gebaut werden muss. Hier fuer eine "
         "Bibliothek mit einem Ziel und fuer eine mit vier Zielen (wsat_fat.json).")
    section("Ein Ziel")
    r = run(sl("matrix", "--meta", str(META)), dry)
    section("Vier Ziele (Linux x86_64 und aarch64, macOS aarch64, Windows x86_64)")
    r2 = run(sl("matrix", "--meta", str(META_FAT)), dry)
    for res in (r, r2):
        if res and res.code == 0:
            try:
                data = json.loads(res.out)
                print()
                print(dim(f"  Die Ausgabe ist gueltiges JSON ({type(data).__name__}, "
                          f"{len(data)} Eintraege)."))
            except json.JSONDecodeError:
                print(dim("  Die Ausgabe ist kein reines JSON."))


def find_header() -> Optional[Path]:
    hs = sorted(GEN.glob("*.h"))
    return hs[0] if hs else None


def step_build(dry: bool) -> None:
    banner("Schritt 4: sl build", "Kompilieren fuer das Host-Target und in einen Container packen")
    note("sl build ruft den C-Compiler (GCC/Clang) auf, baut den Payload fuer das Host-Target "
         "und schreibt ihn mit den Metadaten in einen .sl-Container. Die vom Generator "
         "erzeugte C-Quelle wird mitkompiliert; mit -I findet der Compiler den Header.")
    OUT.mkdir(exist_ok=True)
    gen_c = sorted(GEN.glob("*.c"))
    if not gen_c and not dry:
        print(yellow("  Hinweis: gen/ enthaelt keine C-Quelle; zuerst --step gen ausfuehren."))
    src_gen = str(gen_c[0]) if gen_c else str(GEN / "wsat_sl.c")
    run(sl("build", "--meta", str(META),
           "--source", src_gen, "--source", str(IMPL),
           "-I", str(GEN), "-D", "WSAT_DEMO=1",
           "-o", str(OUT / "wsat.sl")), dry)
    section("Optionen im Beispiel")
    table([
        ["--meta", "Metadatendatei"],
        ["--source", "C-Quelle (mehrfach angebbar)"],
        ["-I DIR", "Include-Verzeichnis (hier gen/ fuer den erzeugten Header)"],
        ["-D X=1", "Praeprozessor-Definition"],
        ["--extra P:A=DATEI", "Vorgebauten Payload eines anderen Targets ergaenzen (Fat-Container)"],
        ["-o", "Ausgabedatei"],
    ], ["Option", "Bedeutung"])
    section("Beispiel mit --extra (nur Anzeige, wird nicht ausgefuehrt)")
    print(dim("  $ ") + "python -m sl build --meta wsat_fat.json --source gen/wsat_sl.c --source src/impl.c \\")
    print(dim("      ") + "-I gen --extra windows:x86_64=prebuilt/wsat.dll -o out/wsat_fat.sl")


def host_shared_name() -> str:
    return {"windows": "wsat.dll", "macos": "libwsat.dylib"}.get(host_target().split(":")[0], "libwsat.so")


def step_pack(dry: bool) -> None:
    banner("Schritt 5: sl pack", "Vorhandene Binaries zu einem Fat-Container packen")
    note("sl pack baut nichts: Es nimmt fertige Binaries (je Plattform:Architektur) und "
         "legt sie mit den Metadaten in einen Container. Zur Demo wird ein Payload mit dem "
         "System-Compiler vorab gebaut und dann gepackt.")
    OUT.mkdir(exist_ok=True)
    payload = OUT / host_shared_name()
    section("Payload mit dem System-Compiler bauen")
    cc = os.environ.get("CC", "gcc")
    cmd = [cc, "-shared", "-fPIC", "-O2", "-I", str(GEN), "-o", str(payload),
           str(IMPL)] + [str(p) for p in sorted(GEN.glob("*.c"))]
    run(cmd, dry)
    section("Packen")
    run(sl("pack", "--meta", str(META), "--payload", f"{host_target()}={payload}",
           "-o", str(OUT / "wsat_packed.sl")), dry)
    note("Fuer einen echten Fat-Container wuerde man --payload mehrfach angeben, etwa "
         "linux:x86_64=..., linux:aarch64=..., macos:aarch64=..., windows:x86_64=... "
         "und die Metadaten wsat_fat.json verwenden.")


def step_info(dry: bool) -> None:
    banner("Schritt 6: sl info", "Metadaten und Payloads eines Containers anzeigen")
    for name in ("wsat.sl", "wsat_packed.sl"):
        p = OUT / name
        if not p.exists() and not dry:
            print(yellow(f"  {name} fehlt; zuerst build bzw. pack ausfuehren."))
            continue
        run(sl("info", str(p)), dry)


def step_errors(dry: bool) -> None:
    banner("Schritt 7: Fehlerdarstellung", "Einheitliche Meldungen und Exit-Code 2")
    note("Alle Fehler der Kommandozeile erscheinen als 'sl: error: ...' auf stderr, der "
         "Exit-Code ist 2. Drei absichtlich fehlerhafte Aufrufe:")
    section("Datei existiert nicht")
    run(sl("info", str(OUT / "gibt_es_nicht.sl")), dry)
    section("Ungueltiger Container (Textdatei statt .sl)")
    bogus = OUT / "kein_container.sl"
    if not dry:
        OUT.mkdir(exist_ok=True)
        bogus.write_text("das ist kein Container\n", encoding="utf-8")
    run(sl("info", str(bogus)), dry)
    section("Metadaten fehlen")
    run(sl("matrix", "--meta", str(ROOT / "nicht_da.json")), dry)


def step_api(dry: bool) -> None:
    banner("Schritt 8: Dieselbe Bibliothek in Python laden", "Die Bibliotheks-API neben der CLI")
    note("Der erzeugte Container wird mit sl.open geladen. Die Suche findet ihn ueber "
         "SL_PATH (hier: der Ordner out/). Die C-artige Statusschnittstelle liefert "
         "(status, wert, fehlerinfo) statt Ausnahmen.")
    code = textwrap.dedent("""\
        import ctypes, sl

        with sl.open("wsat") as lib:
            solve = lib.symbol("wsat_solve",
                               argtypes=[ctypes.POINTER(ctypes.c_int), ctypes.c_uint],
                               restype=ctypes.c_int)
            print("Summe:", solve((ctypes.c_int * 3)(1, 2, 3), 3))

        status, handle, err = sl.sl_open("gibt_es_nicht")
        print("Status:", status, "| failed_name:", getattr(err, "failed_name", None))
    """)
    print(dim("  --- Python-Beispiel ---"))
    for i, line in enumerate(code.splitlines(), 1):
        print(dim(f"  {i:3d} | ") + line)
    env_note = f"SL_PATH={OUT}"
    print()
    print(green("  $ ") + bold(f"{env_note} python -c '<Beispiel>'"))
    if dry:
        print(dim("  (Trockenlauf: nicht ausgefuehrt)"))
        return
    env = dict(os.environ, SL_PATH=str(OUT))
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=ROOT)
    for line in p.stdout.rstrip().splitlines():
        print("    " + line)
    for line in p.stderr.rstrip().splitlines():
        print("    " + red(line))
    print("  " + (green("Exit-Code 0") if p.returncode == 0 else red(f"Exit-Code {p.returncode}")))
    section("Suchreihenfolge (Kurzfassung)")
    table([
        ["1", "Expliziter Pfad (dann nur dieser)"],
        ["2", "SL_PATH (':' unter POSIX, ';' unter Windows; \\: und \\\\ als Escapes)"],
        ["3", "Verzeichnis des Aufrufers und dessen Unterverzeichnis sl/"],
        ["4", "Anwendungsverzeichnis"],
        ["5", "Systemverzeichnisse des Plattformadapters"],
    ], ["Rang", "Ort"])
    print()
    note("Nie durchsucht werden das Arbeitsverzeichnis, PATH, LD_LIBRARY_PATH und DYLD_LIBRARY_PATH.")


def step_status(dry: bool) -> None:
    banner("Anhang: Fehlermodell", "Statuswerte von SLStatus")
    table([
        ["OK", "0", "Erfolg"], ["NOT_FOUND", "1", "Bibliothek nicht gefunden"],
        ["DEPENDENCY_MISSING", "2", "Abhaengigkeit fehlt"], ["ARCH_MISMATCH", "3", "Plattform/Architektur passt nicht"],
        ["ABI_MISMATCH", "4", "ABI-Version passt nicht"], ["INVALID_CONTAINER", "5", "Container oder Metadaten ungueltig"],
        ["SYMBOL_NOT_FOUND", "6", "Symbol nicht exportiert"], ["INIT_FAILED", "7", "Init-Haken meldet Fehler"],
        ["CYCLE", "8", "Abhaengigkeitszyklus"], ["ACCESS_DENIED", "9", "Zugriff verweigert (z. B. gehaerteter Modus)"],
        ["INTERNAL", "10", "Interner oder nativer Fehler"],
    ], ["Status", "Wert", "Bedeutung"])


STEPS: List[tuple] = [
    ("intro", "Ueberblick ueber alle Befehle", step_intro),
    ("meta", "Metadaten (wsat.json)", step_meta),
    ("gen", "sl gen", step_gen),
    ("matrix", "sl matrix", step_matrix),
    ("build", "sl build", step_build),
    ("pack", "sl pack", step_pack),
    ("info", "sl info", step_info),
    ("errors", "Fehlerdarstellung", step_errors),
    ("api", "Python-API neben der CLI", step_api),
    ("status", "Anhang: Fehlermodell", step_status),
]


def main(argv: Optional[List[str]] = None) -> int:
    global USE_COLOR
    ap = argparse.ArgumentParser(description="Demo der sl-Kommandozeile",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("--step", action="append", choices=[s[0] for s in STEPS],
                    help="nur diesen Schritt ausfuehren (mehrfach moeglich)")
    ap.add_argument("--list", action="store_true", help="Schritte auflisten")
    ap.add_argument("--dry-run", action="store_true", help="Befehle nur anzeigen")
    ap.add_argument("--no-color", action="store_true", help="ohne ANSI-Farben")
    ap.add_argument("--pause", action="store_true", help="nach jedem Schritt Enter abwarten")
    args = ap.parse_args(argv)

    if args.no_color or os.environ.get("NO_COLOR"):
        USE_COLOR = False
    if args.list:
        table([[k, desc] for k, desc, _ in STEPS], ["Schritt", "Inhalt"])
        return 0

    wanted = set(args.step) if args.step else None
    for key, _desc, fn in STEPS:
        if wanted and key not in wanted:
            continue
        fn(args.dry_run)
        if args.pause and sys.stdin.isatty():
            input(dim("\n  [Enter fuer den naechsten Schritt] "))
    print()
    print(green(bold("  Ende der Demo.")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
