import json

import pytest

from sl.codegen import (ctype_expr, generate_all, generate_c_source, generate_cmake,
                        generate_header, generate_python_binding, parse_signature)


@pytest.fixture
def api_meta(make_meta):
    return make_meta(name="wsat", exports=("wsat_solve", "wsat_name", "wsat_ping"),
                     signatures={"wsat_solve": "int wsat_solve(const int *xs, unsigned int n)",
                                 "wsat_name": "const char *wsat_name(void);"},
                     init="wsat_init", fini="wsat_fini")


def test_parse_signature():
    assert parse_signature("int f(void)", "f") == ("int", [])
    assert parse_signature("void f()", "f") == ("void", [])
    assert parse_signature("const char *f(void);", "f") == ("const char *", [])
    assert parse_signature("int f(const int *xs, unsigned int n, double d)", "f") == (
        "int", ["const int *", "unsigned int", "double"])
    assert parse_signature("int f(int, char *)", "f") == ("int", ["int", "char *"])
    assert parse_signature("unsigned f(unsigned)", "f") == ("unsigned", ["unsigned"])


@pytest.mark.parametrize("signature", ["garbage", "int other(void)"])
def test_parse_signature_rejects(signature):
    with pytest.raises(ValueError, match="does not declare"):
        parse_signature(signature, "f")


def test_ctype_expr():
    assert ctype_expr("void") == "None"
    assert ctype_expr("unsigned int") == "ctypes.c_uint"
    assert ctype_expr("const char *") == "ctypes.c_char_p"
    assert ctype_expr("double*") == "ctypes.c_void_p"
    assert ctype_expr("uint64_t") == "ctypes.c_uint64"
    with pytest.raises(ValueError, match="unsupported"):
        ctype_expr("struct foo")


def test_header(api_meta, make_meta):
    text = generate_header(api_meta)
    assert "#ifndef WSAT_SL_H" in text and "#define WSAT_ABI_VERSION 1" in text
    assert "SL_EXPORT int wsat_solve(const int *xs, unsigned int n);" in text
    assert "SL_EXPORT const char *wsat_name(void);" in text
    assert "SL_EXPORT void wsat_ping(void);" in text          # Standard ohne Signatur
    assert "SL_EXPORT int wsat_init(void);" in text and "SL_EXPORT int wsat_fini(void);" in text
    plain = generate_header(make_meta())
    assert "demo_init" not in plain and "demo_abi_version" in plain


def test_c_source(api_meta, make_meta):
    text = generate_c_source(api_meta)
    assert '#include "wsat.h"' in text and '"wsat_solve", "wsat_name"' in text
    assert "wsat_sl_metadata" in text and "\\\"name\\\": \\\"wsat\\\"" in text
    assert "{ 0 }" in generate_c_source(make_meta())


def test_cmake(api_meta):
    text = generate_cmake(api_meta)
    assert "function(wsat_add_sl_library target)" in text
    assert "WSAT_SL_BUILDING" in text and "wsat.sl" in text


def test_python_binding_is_valid_and_loadable(api_meta, loader, adapter, write_sl):
    text = generate_python_binding(api_meta)
    namespace = {}
    exec(compile(text, "wsat_binding.py", "exec"), namespace)
    assert namespace["NAME"] == "wsat" and namespace["ABI_VERSION"] == 1
    args, ret = namespace["SIGNATURES"]["wsat_solve"]
    assert len(args) == 2 and ret is not None
    assert namespace["SIGNATURES"]["wsat_ping"] == ([], None)
    write_sl("wsat", exports=api_meta.exports)
    adapter.symbols["wsat"] = {s: (lambda *a: 0) for s in api_meta.exports}
    lib, funcs = namespace["load"](loader=loader)
    assert set(funcs) == set(api_meta.exports)
    lib.close()


def test_generate_all(api_meta, tmp_path):
    written = generate_all(api_meta, tmp_path / "nested" / "gen")
    names = [p.name for p in written]
    assert names == sorted(names) and "wsat.h" in names and "build_matrix.json" in names
    assert json.loads((tmp_path / "nested" / "gen" / "wsat.json").read_text())["name"] == "wsat"
    matrix = json.loads((tmp_path / "nested" / "gen" / "build_matrix.json").read_text())
    assert matrix[0]["output"] == "wsat.so"
