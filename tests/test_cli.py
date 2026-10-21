import json
import runpy
import sys

import pytest

import sl.cli as cli
from sl.container import unpack


@pytest.fixture
def meta_file(make_meta, tmp_path):
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(make_meta(exports=("f",)).to_dict()))
    return path


def test_pack_and_info(meta_file, tmp_path, capsys):
    payload = tmp_path / "p.bin"
    payload.write_bytes(b"P")
    out = tmp_path / "demo.sl"
    assert cli.main(["pack", "--meta", str(meta_file), "--payload",
                     f"linux:x86_64={payload}", "-o", str(out)]) == 0
    capsys.readouterr()
    assert unpack(out.read_bytes()).payload_for("linux", "x86_64") == b"P"
    assert cli.main(["info", str(out)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["name"] == "demo" and data["payloads"] == ["linux:x86_64"]


def test_gen_and_matrix(meta_file, tmp_path, capsys):
    assert cli.main(["gen", "--meta", str(meta_file), "-o", str(tmp_path / "g")]) == 0
    assert "demo.h" in capsys.readouterr().out
    assert (tmp_path / "g" / "demo_binding.py").exists()
    assert cli.main(["matrix", "--meta", str(meta_file)]) == 0
    assert json.loads(capsys.readouterr().out)[0]["platform"] == "linux"


def test_build_command_delegates(meta_file, tmp_path, monkeypatch, capsys):
    seen = {}

    def fake(meta, sources, output, extra_files, include_dirs, defines):
        seen.update(sources=sources, extra=extra_files, inc=include_dirs, defs=defines)
        return output

    monkeypatch.setattr(cli, "build_sl", fake)
    extra = tmp_path / "x.bin"
    assert cli.main(["build", "--meta", str(meta_file), "--source", "a.c", "--extra",
                     f"windows:x86_64={extra}", "-I", "inc", "-D", "X=1",
                     "-o", str(tmp_path / "o.sl")]) == 0
    assert seen["sources"] == ["a.c"] and len(seen["extra"]) == 1
    assert seen["inc"] == ["inc"] and seen["defs"] == ["X=1"]


@pytest.mark.parametrize("spec", ["nonsense", "linux=file", "beos:x86_64=file"])
def test_bad_payload_spec(spec, meta_file, tmp_path, capsys):
    with pytest.raises(SystemExit) as info:
        cli.main(["pack", "--meta", str(meta_file), "--payload", spec, "-o", "x"])
    assert info.value.code == 2


def test_errors_return_two(meta_file, tmp_path, capsys):
    assert cli.main(["info", str(tmp_path / "absent.sl")]) == 2
    assert "sl: error" in capsys.readouterr().err
    broken = tmp_path / "broken.json"
    broken.write_text("{nope")
    assert cli.main(["matrix", "--meta", str(broken)]) == 2
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"name": "1x"}))
    assert cli.main(["matrix", "--meta", str(invalid)]) == 2
    bad_sig = tmp_path / "sig.json"
    bad_sig.write_text(json.dumps({"name": "a", "version": "1.0.0", "abi_version": 1,
                                   "targets": [{"platform": "linux", "arch": "x86_64"}],
                                   "exports": ["f"], "signatures": {"f": "struct s f(void)"}}))
    assert cli.main(["gen", "--meta", str(bad_sig), "-o", str(tmp_path / "o")]) == 2


def test_module_entry_point(meta_file, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["sl", "matrix", "--meta", str(meta_file)])
    with pytest.raises(SystemExit) as info:
        runpy.run_module("sl", run_name="__main__")
    assert info.value.code == 0
