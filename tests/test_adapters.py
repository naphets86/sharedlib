import os
from types import SimpleNamespace

import _ctypes
import pytest

from sl.adapters import (DarwinAdapter, LinuxAdapter, NativeLib, WindowsAdapter, get_adapter)
from sl.errors import SLError, SLStatus


@pytest.mark.parametrize("platform,cls,suffix", [("linux", LinuxAdapter, ".so"),
                                                  ("macos", DarwinAdapter, ".dylib"),
                                                  ("windows", WindowsAdapter, ".dll")])
def test_get_adapter(platform, cls, suffix):
    adapter = get_adapter(platform)
    assert type(adapter) is cls and adapter.native_suffix == suffix


def test_get_adapter_default():
    assert get_adapter().platform in ("linux", "macos", "windows")


def test_system_dirs():
    assert LinuxAdapter().system_dirs({}) == ["/usr/local/lib/sl", "/usr/lib/sl"]
    assert "/opt/homebrew/lib/sl" in DarwinAdapter().system_dirs({})
    win = WindowsAdapter()
    assert win.system_dirs({}) == []
    assert win.system_dirs({"ProgramData": "C:\\PD", "ProgramFiles": "C:\\PF"}) == [
        os.path.join("C:\\PD", "sl"), os.path.join("C:\\PF", "sl")]


def test_map_payload_success_and_failure(monkeypatch):
    adapter = LinuxAdapter()
    monkeypatch.setattr(adapter, "_open", lambda path: SimpleNamespace(path=path))
    native = adapter.map_payload(b"bytes", "demo")
    assert open(native.path, "rb").read() == b"bytes" and native.path.endswith("demo.so")

    def fail(path):
        raise OSError(8, "bad")

    monkeypatch.setattr(adapter, "_open", fail)
    with pytest.raises(OSError):
        adapter.map_payload(b"x", "demo")


def test_lookup(tmp_path):
    adapter = LinuxAdapter()
    native = NativeLib(SimpleNamespace(f=123), "p", str(tmp_path))
    assert adapter.lookup(native, "f") == 123
    with pytest.raises(SLError) as info:
        adapter.lookup(native, "g")
    assert info.value.status is SLStatus.SYMBOL_NOT_FOUND


@pytest.mark.parametrize("adapter,hook", [(LinuxAdapter(), "dlclose"), (DarwinAdapter(), "dlclose"),
                                          (WindowsAdapter(), "FreeLibrary")])
def test_unmap_releases_and_cleans(adapter, hook, tmp_path, monkeypatch):
    released = []
    monkeypatch.setattr(_ctypes, hook, lambda handle: released.append(handle), raising=False)
    folder = tmp_path / "mapped"
    folder.mkdir()
    adapter.unmap(NativeLib(SimpleNamespace(_handle=99), "p", str(folder)))
    assert released == [99] and not folder.exists()
