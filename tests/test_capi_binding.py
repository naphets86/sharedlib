import pytest

import sl
import sl.capi as capi
from sl.errors import SLStatus


def test_c_style_status_api(loader, adapter, write_sl):
    write_sl("demo", exports=("f",))
    adapter.symbols["demo"] = {"f": lambda: 7}
    status, handle, err = sl.sl_open("demo", 0, loader=loader)
    assert status is SLStatus.OK and err.code is SLStatus.OK
    status, func, _ = sl.sl_symbol(handle, "f")
    assert status is SLStatus.OK and func() == 7
    status, info, _ = sl.sl_info(handle)
    assert status is SLStatus.OK and info["name"] == "demo"
    status, err = sl.sl_close(handle)
    assert status is SLStatus.OK


def test_c_style_errors(loader, write_sl):
    status, handle, err = sl.sl_open("absent", loader=loader)
    assert status is SLStatus.NOT_FOUND and handle is None
    assert err.failed_name == "absent" and err.searched and err.message
    write_sl("demo")
    _, handle, _ = sl.sl_open("demo", loader=loader)
    assert sl.sl_symbol(handle, "nope")[0] is SLStatus.SYMBOL_NOT_FOUND
    sl.sl_close(handle)
    assert sl.sl_info(handle)[0] is SLStatus.INTERNAL
    assert sl.sl_close(handle)[0] is SLStatus.INTERNAL


def test_default_loader_management(monkeypatch):
    monkeypatch.setattr(capi, "_default_loader", None)
    created = sl.default_loader()
    assert isinstance(created, sl.Loader) and sl.default_loader() is created
    custom = sl.Loader(platform="linux", arch="x86_64")
    sl.set_default_loader(custom)
    assert sl.default_loader() is custom


def test_python_binding(loader, adapter, write_sl):
    write_sl("demo", exports=("f", "g"))
    adapter.symbols["demo"] = {"f": lambda x: x + 1, "g": lambda: 0}
    with sl.open("demo", loader=loader) as lib:
        assert lib.info["name"] == "demo"
        func = lib.symbol("f", argtypes=[int], restype=int)
        assert func(1) == 2 and func.argtypes == [int] and func.restype is int
        assert lib.symbol("g")() == 0
    assert adapter.unmapped == ["demo"]
    lib.close()  # idempotent


def test_binding_uses_default_loader(loader, write_sl, monkeypatch):
    write_sl("demo")
    monkeypatch.setattr(capi, "_default_loader", loader)
    lib = sl.open("demo")
    lib.close()
