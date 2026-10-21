import pytest

import sl
import sl.loader as loader_module
from sl.errors import SLError, SLStatus


def test_open_symbol_info_close(loader, adapter, write_sl):
    write_sl("demo", exports=("f",))
    adapter.symbols["demo"] = {"f": lambda: 42}
    handle = loader.open("demo")
    assert loader.symbol(handle, "f")() == 42
    info = loader.info(handle)
    assert info["name"] == "demo" and info["exports"] == ["f"] and info["dependencies"] == []
    loader.close(handle)
    assert adapter.unmapped == ["demo"] and handle.closed


def test_default_construction():
    default = sl.Loader()
    assert default.platform in ("linux", "macos", "windows")
    assert default.adapter.platform == default.platform


def test_refcount_shares_handle(loader, adapter, write_sl):
    write_sl("demo")
    first, second = loader.open("demo"), loader.open("demo")
    assert first is second and first.refcount == 2 and adapter.mapped == ["demo"]
    loader.close(first)
    assert adapter.unmapped == []
    loader.close(second)
    assert adapter.unmapped == ["demo"]


def test_closed_handle_is_rejected(loader, write_sl):
    write_sl("demo", exports=("f",))
    handle = loader.open("demo")
    loader.close(handle)
    for call in (lambda: loader.close(handle), lambda: loader.symbol(handle, "f"),
                 lambda: loader.info(handle)):
        with pytest.raises(SLError) as info:
            call()
        assert info.value.status is SLStatus.INTERNAL


def test_only_exported_symbols_are_visible(loader, adapter, write_sl):
    write_sl("demo", exports=("f", "ghost"))
    adapter.symbols["demo"] = {"f": lambda: 1, "hidden": lambda: 2}
    handle = loader.open("demo")
    with pytest.raises(SLError, match="not exported"):
        loader.symbol(handle, "hidden")
    with pytest.raises(SLError) as info:
        loader.symbol(handle, "ghost")  # exportiert, aber im Payload nicht vorhanden
    assert info.value.status is SLStatus.SYMBOL_NOT_FOUND


def test_not_found_and_invalid_name(loader):
    with pytest.raises(SLError) as info:
        loader.open("absent")
    assert info.value.status is SLStatus.NOT_FOUND and info.value.searched
    with pytest.raises(SLError):
        loader.open("libabsent.so")


def test_abi_and_arch_mismatch(adapter, tmp_path, write_sl):
    write_sl("demo", abi_version=2)
    env = {"SL_PATH": str(tmp_path)}
    strict = sl.Loader(adapter, env=env, platform="linux", arch="x86_64")
    with pytest.raises(SLError) as info:
        strict.open("demo")
    assert info.value.status is SLStatus.ABI_MISMATCH
    relaxed = sl.Loader(adapter, env=env, platform="linux", arch="x86_64", abi_range=(1, 2))
    relaxed.close(relaxed.open("demo"))
    other_arch = sl.Loader(adapter, env=env, platform="linux", arch="aarch64", abi_range=(1, 2))
    with pytest.raises(SLError) as info:
        other_arch.open("demo")
    assert info.value.status is SLStatus.ARCH_MISMATCH


def test_requester_dir_and_hardened(adapter, tmp_path, write_sl):
    sub = tmp_path / "plugin"
    sub.mkdir()
    write_sl("demo", directory=sub)
    plain = sl.Loader(adapter, env={}, platform="linux", arch="x86_64")
    with pytest.raises(SLError):
        plain.open("demo")
    scoped = sl.Loader(adapter, env={}, platform="linux", arch="x86_64", requester_dir=str(sub),
                       hardened=True)
    scoped.close(scoped.open("demo"))


def test_dependency_chain_and_release(loader, adapter, write_sl):
    write_sl("base")
    write_sl("mid", dependencies={"base": ">=1.0.0"})
    write_sl("top", dependencies={"mid": "*"})
    handle = loader.open("top")
    assert adapter.mapped == ["base", "mid", "top"]       # Abhaengigkeiten zuerst
    assert loader.info(handle)["dependencies"] == ["mid"]
    loader.close(handle)
    assert adapter.unmapped == ["top", "mid", "base"]


def test_shared_dependency_is_refcounted(loader, adapter, write_sl):
    write_sl("base")
    write_sl("one", dependencies={"base": "*"})
    write_sl("two", dependencies={"base": "*"})
    one, two = loader.open("one"), loader.open("two")
    loader.close(one)
    assert "base" not in adapter.unmapped
    loader.close(two)
    assert adapter.unmapped.count("base") == 1


def test_missing_dependency_rolls_back(loader, adapter, write_sl):
    write_sl("base")
    write_sl("top", dependencies={"base": "*", "ghost": "*"})
    with pytest.raises(SLError) as info:
        loader.open("top")
    assert info.value.status is SLStatus.DEPENDENCY_MISSING
    assert info.value.failed_name == "ghost" and info.value.searched
    assert adapter.unmapped == ["base"] and loader._loaded == {}


def test_dependency_version_mismatch_fresh_and_cached(loader, adapter, write_sl, tmp_path):
    write_sl("base", version="1.0.0")
    write_sl("top", dependencies={"base": ">=2.0.0"})
    with pytest.raises(SLError) as info:
        loader.open("top")
    assert info.value.status is SLStatus.DEPENDENCY_MISSING
    cached = loader.open("base")
    with pytest.raises(SLError) as info:
        loader.open("top")
    assert info.value.status is SLStatus.DEPENDENCY_MISSING and cached.refcount == 1


def test_broken_dependency_status_is_preserved(loader, tmp_path, write_sl):
    write_sl("top", dependencies={"base": "*"})
    (tmp_path / "base.sl").write_bytes(b"garbage-garbage-garbage")
    with pytest.raises(SLError) as info:
        loader.open("top")
    assert info.value.status is SLStatus.INVALID_CONTAINER


def test_cycle_is_detected(loader, adapter, write_sl):
    write_sl("a", dependencies={"b": "*"})
    write_sl("b", dependencies={"a": "*"})
    with pytest.raises(SLError) as info:
        loader.open("a")
    assert info.value.status is SLStatus.CYCLE
    assert loader._loading == [] and loader._loaded == {} and adapter.mapped == []


def test_init_runs_once_and_fini_on_close(loader, adapter, write_sl):
    calls = []
    write_sl("demo", init="demo_init", fini="demo_fini")
    adapter.symbols["demo"] = {"demo_init": lambda: calls.append("init") or 0,
                               "demo_fini": lambda: calls.append("fini") or 0}
    first, second = loader.open("demo"), loader.open("demo")
    assert calls == ["init"]
    loader.close(first)
    loader.close(second)
    assert calls == ["init", "fini"]


def test_missing_fini_does_not_block_unload(loader, adapter, write_sl):
    write_sl("demo", init="demo_init", fini="demo_fini")
    adapter.symbols["demo"] = {"demo_init": lambda: 0}
    loader.close(loader.open("demo"))
    assert adapter.unmapped == ["demo"]


def test_init_failure_rolls_back(loader, adapter, write_sl):
    write_sl("base")
    write_sl("demo", init="demo_init", dependencies={"base": "*"})
    adapter.symbols["demo"] = {"demo_init": lambda: 3}
    with pytest.raises(SLError) as info:
        loader.open("demo")
    assert info.value.status is SLStatus.INIT_FAILED and info.value.native_error == 3
    assert adapter.unmapped == ["demo", "base"] and loader._loaded == {}


def test_missing_init_entry_point(loader, adapter, write_sl):
    write_sl("demo", init="demo_init")
    with pytest.raises(SLError) as info:
        loader.open("demo")
    assert info.value.status is SLStatus.INIT_FAILED


@pytest.mark.parametrize("error,code", [(OSError(8, "bad format"), 8), (OSError("plain"), 0)])
def test_mapping_failure(loader, adapter, write_sl, error, code):
    write_sl("demo")
    adapter.fail_map = error
    with pytest.raises(SLError) as info:
        loader.open("demo")
    assert info.value.status is SLStatus.INTERNAL and info.value.native_error == code


def test_read_failures(loader, write_sl, monkeypatch):
    write_sl("demo")

    def deny(self):
        raise PermissionError(13, "denied")

    def broken(self):
        raise OSError(5, "io")

    monkeypatch.setattr(loader_module.Path, "read_bytes", deny)
    with pytest.raises(SLError) as info:
        loader.open("demo")
    assert info.value.status is SLStatus.ACCESS_DENIED and info.value.native_error == 13
    monkeypatch.setattr(loader_module.Path, "read_bytes", broken)
    with pytest.raises(SLError) as info:
        loader.open("demo")
    assert info.value.status is SLStatus.INTERNAL
    monkeypatch.setattr(loader_module.Path, "read_bytes", lambda self: b"")
    with pytest.raises(SLError):
        loader.open("demo")
