import subprocess
from types import SimpleNamespace

import pytest

import sl.build as build
from sl.container import unpack
from sl.errors import SLError, SLStatus
from sl.metadata import Target

LIN = Target("linux", "x86_64")
WIN = Target("windows", "x86_64")


def test_toolchain_flags():
    assert "-fPIC" in build.toolchain_flags("linux", "x86_64")
    assert build.toolchain_flags("windows", "x86_64") == ["-shared"]
    assert build.toolchain_flags("macos", "aarch64")[-2:] == ["-arch", "arm64"]
    assert build.toolchain_flags("macos", "x86_64")[-1] == "x86_64"
    with pytest.raises(ValueError, match="not supported"):
        build.toolchain_flags("macos", "arm")


def test_build_matrix(make_meta):
    meta = make_meta(targets=(LIN, WIN))
    rows = build.build_matrix(meta, compiler="gcc")
    assert [r["output"] for r in rows] == ["demo.so", "demo.dll"]
    assert rows[0]["compiler"] == "gcc"


def test_compile_command():
    cmd = build.compile_command("cc", ["a.c", "b.c"], "out.so", "linux", "x86_64",
                                include_dirs=["inc"], defines=["X=1"])
    assert cmd[0] == "cc" and "-Iinc" in cmd and "-DX=1" in cmd
    assert cmd[-4:] == ["-o", "out.so", "a.c", "b.c"]


def test_find_compiler():
    assert build.find_compiler({"CC": "mycc"}) == "mycc"
    assert build.find_compiler({}, which=lambda c: "/bin/" + c if c == "gcc" else None) == "/bin/gcc"
    assert build.find_compiler({}, which=lambda c: "/bin/cc") == "/bin/cc"
    with pytest.raises(SLError, match="no C compiler"):
        build.find_compiler({}, which=lambda c: None)
    assert build.find_compiler()


def test_build_native_outcomes(monkeypatch, tmp_path):
    monkeypatch.setattr(build.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stderr=""))
    out = build.build_native(["a.c"], tmp_path / "o.so", compiler="cc",
                             platform="linux", arch="x86_64")
    assert out == tmp_path / "o.so"
    monkeypatch.setattr(build.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=1, stderr="boom"))
    with pytest.raises(SLError, match="boom") as info:
        build.build_native(["a.c"], tmp_path / "o.so", compiler="cc")
    assert info.value.native_error == 1

    def missing(*a, **k):
        raise FileNotFoundError(2, "no such file")

    monkeypatch.setattr(build.subprocess, "run", missing)
    with pytest.raises(SLError) as info:
        build.build_native(["a.c"], tmp_path / "o.so", compiler="nocc")
    assert info.value.status is SLStatus.INTERNAL and info.value.native_error == 2


def test_pack_files_makes_fat_container(make_meta, tmp_path):
    (tmp_path / "l.bin").write_bytes(b"L")
    (tmp_path / "w.bin").write_bytes(b"W")
    out = build.pack_files(make_meta(), {WIN: tmp_path / "w.bin", LIN: tmp_path / "l.bin"},
                           tmp_path / "demo.sl")
    container = unpack(out.read_bytes())
    assert container.targets == [LIN, WIN]
    assert container.payload_for("windows", "x86_64") == b"W"


def test_build_sl_adds_host_to_extra_payloads(make_meta, tmp_path, monkeypatch):
    def fake(sources, output, **kwargs):
        output.write_bytes(b"HOST")
        return output

    monkeypatch.setattr(build, "build_native", fake)
    (tmp_path / "w.bin").write_bytes(b"W")
    out = build.build_sl(make_meta(), ["a.c"], tmp_path / "d.sl", platform="linux",
                         arch="x86_64", extra_files={WIN: tmp_path / "w.bin"})
    container = unpack(out.read_bytes())
    assert container.payload_for("linux", "x86_64") == b"HOST"
    assert container.payload_for("windows", "x86_64") == b"W"
    solo = build.build_sl(make_meta(), ["a.c"], tmp_path / "s.sl")
    assert len(unpack(solo.read_bytes()).targets) == 1
