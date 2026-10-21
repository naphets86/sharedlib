import os
import stat

import pytest

from sl.adapters import LinuxAdapter
from sl.errors import SLError, SLStatus
from sl.search import candidates, locate, resolve_name, split_sl_path


def _locate(name, tmp_path, **kw):
    args = {"env": {}, "requester_dir": None, "app_dir": None, "adapter": LinuxAdapter()}
    args.update(kw)
    return locate(name, **args)


def test_split_sl_path():
    assert split_sl_path("") == []
    assert split_sl_path("/a:/b::/c") == ["/a", "/b", "/c"]
    assert split_sl_path("/a\\:b:/c") == ["/a:b", "/c"]
    assert split_sl_path("/a\\\\b") == ["/a\\b"]
    assert split_sl_path("/a\\x") == ["/a\\x"]
    assert split_sl_path("/a\\") == ["/a\\"]


def test_resolve_name():
    assert resolve_name("wsat") == ("wsat.sl", False)
    assert resolve_name("wsat.sl") == ("wsat.sl", False)
    assert resolve_name("/opt/x/wsat") == ("/opt/x/wsat.sl", True)
    assert resolve_name("dir\\wsat.sl") == ("dir\\wsat.sl", True)
    for bad in ("libwsat.so", "wsat.dll", "1x", ""):
        with pytest.raises(SLError) as info:
            resolve_name(bad)
        assert info.value.status is SLStatus.NOT_FOUND


def test_candidate_order_and_filters():
    common = {"requester_dir": "/req", "app_dir": "/app", "adapter": LinuxAdapter()}
    env = {"SL_PATH": "/one:relative:/two", "PATH": "/ignored", "LD_LIBRARY_PATH": "/ignored"}
    got = candidates("x.sl", False, env=env, hardened=False, **common)
    assert got == ["/one/x.sl", "/two/x.sl", "/req/x.sl", "/req/sl/x.sl", "/app/x.sl",
                   "/usr/local/lib/sl/x.sl", "/usr/lib/sl/x.sl"]
    hardened = candidates("x.sl", False, env=env, hardened=True, **common)
    assert hardened[0] == "/req/x.sl"
    assert candidates("/p/x.sl", True, env=env, hardened=False, **common) == ["/p/x.sl"]
    bare = candidates("x.sl", False, env={}, requester_dir=None, app_dir=None,
                      adapter=LinuxAdapter(), hardened=False)
    assert bare == ["/usr/local/lib/sl/x.sl", "/usr/lib/sl/x.sl"]


def test_locate_hits_by_priority(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir(), second.mkdir()
    (first / "lib.sl").write_bytes(b"1")
    (second / "lib.sl").write_bytes(b"2")
    env = {"SL_PATH": f"{second}:{first}"}
    path, tried = _locate("lib", tmp_path, env=env)
    assert path == str(second / "lib.sl") and tried == [path]
    path, _ = _locate(str(first / "lib"), tmp_path)
    assert path == str(first / "lib.sl")
    path, _ = _locate("lib", tmp_path, requester_dir=str(first))
    assert path == str(first / "lib.sl")


def test_cwd_is_never_searched(tmp_path, monkeypatch):
    (tmp_path / "lib.sl").write_bytes(b"1")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SLError) as info:
        _locate("lib", tmp_path)
    assert info.value.status is SLStatus.NOT_FOUND
    assert "/usr/lib/sl/lib.sl" in info.value.searched


def test_hardened_rejects_world_writable(tmp_path):
    folder = tmp_path / "open"
    folder.mkdir()
    (folder / "lib.sl").write_bytes(b"1")
    safe = tmp_path / "safe"
    safe.mkdir()
    (safe / "lib.sl").write_bytes(b"1")
    os.chmod(folder, os.stat(folder).st_mode | stat.S_IWOTH)
    os.chmod(safe, 0o755)
    with pytest.raises(SLError) as info:
        _locate(str(folder / "lib"), tmp_path, hardened=True)
    assert info.value.status is SLStatus.ACCESS_DENIED
    path, _ = _locate(str(safe / "lib"), tmp_path, hardened=True)
    assert path == str(safe / "lib.sl")
    path, _ = _locate(str(folder / "lib"), tmp_path, hardened=False)
    assert path == str(folder / "lib.sl")
