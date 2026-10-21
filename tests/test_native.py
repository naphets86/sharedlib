"""Echte Ende-zu-Ende-Tests: C-Code kompilieren, als .sl packen, ueber den Loader nutzen."""
import ctypes
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

import sl
import sl.cli as cli
from sl.build import build_native, build_sl
from sl.codegen import generate_all, generate_python_binding
from sl.container import unpack
from sl.errors import SLError, SLStatus
from sl.metadata import Metadata, Target

_cc_candidate = os.environ.get("CC")
_found_cc = (
    shutil.which(_cc_candidate)
    if _cc_candidate
    else (shutil.which("gcc") or shutil.which("clang") or shutil.which("cc"))
)

CAN_BUILD = bool(_found_cc)
skip = pytest.mark.skipif(not CAN_BUILD, reason="needs a working C compiler in PATH")

pytestmark = pytest.mark.native

IMPL = """
#include "wsat.h"
static int counter = 0;
int wsat_init(void) { counter = 10; return 0; }
int wsat_fini(void) { return 0; }
int wsat_solve(const int *xs, unsigned int n) {
    int s = counter; for (unsigned int i = 0; i < n; i++) s += xs[i]; return s; }
const char *wsat_name(void) { return "wsat"; }
int wsat_hidden(void) { return 1; }
"""
DEP = '__attribute__((visibility("default"))) int dep_call(void) { return 5; }\n'


def _meta(host, **overrides):
    base = dict(
        name="wsat",
        version="1.2.0",
        abi_version=1,
        targets=(host,),
        exports=("wsat_solve", "wsat_name"),
        signatures={
            "wsat_solve": "int wsat_solve(const int *xs, unsigned int n)",
            "wsat_name": "const char *wsat_name(void)",
        },
        init="wsat_init",
        fini="wsat_fini",
    )
    base.update(overrides)
    return Metadata(**base)


@pytest.fixture
def built(tmp_path):
    host = Target(sl.platform_info.current_platform(), sl.platform_info.current_arch())
    meta = _meta(host)
    gen = tmp_path / "gen"
    generate_all(meta, gen)
    (tmp_path / "impl.c").write_text(IMPL)
    libdir = tmp_path / "lib"
    libdir.mkdir()
    out = build_sl(
        meta,
        [str(gen / "wsat_sl.c"), str(tmp_path / "impl.c")],
        libdir / "wsat.sl",
        include_dirs=[str(gen)],
    )
    return SimpleNamespace(host=host, meta=meta, gen=gen, libdir=libdir, sl_file=out)


@skip
def test_real_library_roundtrip(built):
    loader = sl.Loader(env={"SL_PATH": str(built.libdir)})
    with sl.open("wsat", loader=loader) as lib:
        solve = lib.symbol(
            "wsat_solve",
            [ctypes.POINTER(ctypes.c_int), ctypes.c_uint],
            ctypes.c_int,
        )
        values = (ctypes.c_int * 3)(1, 2, 3)
        assert solve(values, 3) == 16  # init hat counter auf 10 gesetzt
        name = lib.symbol("wsat_name", restype=ctypes.c_char_p)
        assert name() == b"wsat"
        with pytest.raises(SLError, match="not exported"):
            lib.symbol("wsat_hidden")
        assert lib.info["version"] == "1.2.0"


@skip
def test_generated_python_binding_against_real_library(built):
    namespace = {}
    exec(compile(generate_python_binding(built.meta), "binding", "exec"), namespace)
    loader = sl.Loader(env={"SL_PATH": str(built.libdir)})
    lib, funcs = namespace["load"](loader=loader)
    values = (ctypes.c_int * 2)(4, 5)
    assert funcs["wsat_solve"](values, 2) == 19 and funcs["wsat_name"]() == b"wsat"
    lib.close()


@skip
def test_generated_header_compiles_strictly(built):
    cc = _found_cc
    result = subprocess.run(
        [
            cc,
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fsyntax-only",
            "-x",
            "c",
            str(built.gen / "wsat.h"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@skip
def test_real_dependency_and_errors(built, tmp_path):
    (tmp_path / "dep.c").write_text(DEP)
    meta = Metadata(
        name="wsatdep",
        version="1.0.0",
        abi_version=1,
        targets=(built.host,),
        dependencies={"wsat": ">=1.0.0,<2.0.0"},
        exports=("dep_call",),
    )
    build_sl(meta, [str(tmp_path / "dep.c")], built.libdir / "wsatdep.sl")
    loader = sl.Loader(env={"SL_PATH": str(built.libdir)})
    lib = sl.open("wsatdep", loader=loader)
    assert lib.info["dependencies"] == ["wsat"]
    assert lib.symbol("dep_call", restype=ctypes.c_int)() == 5
    lib.close()
    wrong_arch = sl.Loader(
        env={"SL_PATH": str(built.libdir)},
        arch="arm" if built.host.arch != "arm" else "x86",
    )
    with pytest.raises(SLError) as info:
        wrong_arch.open("wsat")
    assert info.value.status is SLStatus.ARCH_MISMATCH


@skip
def test_fat_container_and_cli_build(built, tmp_path, capsys):
    # Dynamisches Fremd-Target waehlen, abhaengig vom Host
    other_platform = "linux" if built.host.platform == "windows" else "windows"
    other = Target(other_platform, "x86_64")
    foreign_name = "foreign.so" if other_platform == "linux" else "foreign.dll"
    foreign = tmp_path / foreign_name
    foreign.write_bytes(b"MZ-not-loaded-here")
    meta_file = tmp_path / "meta.json"
    meta_file.write_text((built.gen / "wsat.json").read_text())
    out = tmp_path / "cli" / "wsat.sl"
    out.parent.mkdir()
    rc = cli.main(
        [
            "build",
            "--meta",
            str(meta_file),
            "--source",
            str(built.gen / "wsat_sl.c"),
            "--source",
            str(tmp_path / "impl.c"),
            "-I",
            str(built.gen),
            "--extra",
            f"{other_platform}:x86_64={foreign}",
            "-o",
            str(out),
        ]
    )
    assert rc == 0
    container = unpack(out.read_bytes())
    assert other in container.targets and built.host in container.targets
    assert cli.main(["info", str(out)]) == 0


@skip
def test_build_native_failures(tmp_path):
    ext = ".dll" if sys.platform == "win32" else ".so"
    (tmp_path / "bad.c").write_text("int broken( {")
    with pytest.raises(SLError, match="compilation failed"):
        build_native([str(tmp_path / "bad.c")], tmp_path / f"x{ext}")
    with pytest.raises(SLError, match="cannot run compiler"):
        build_native([str(tmp_path / "bad.c")], tmp_path / f"x{ext}", compiler="/nonexistent/cc")