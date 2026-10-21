import pytest

from sl.errors import SLError, SLStatus
from sl.metadata import Metadata, Target, parse_version, satisfies
from sl.platform_info import current_arch, current_platform


def test_status_names_and_error_str():
    assert SLStatus.OK.c_name == "SL_OK"
    assert SLStatus.CYCLE.c_name == "SL_ERR_CYCLE"
    err = SLError(SLStatus.NOT_FOUND, "missing", searched=["a", "b"])
    assert str(err) == "SL_ERR_NOT_FOUND: missing"
    assert err.searched == ("a", "b") and err.native_error == 0


@pytest.mark.parametrize("raw,expected", [("linux", "linux"), ("linux2", "linux"),
                                          ("darwin", "macos"), ("win32", "windows"),
                                          ("cygwin", "windows")])
def test_current_platform(raw, expected):
    assert current_platform(raw) == expected


def test_current_platform_default_and_unsupported():
    assert current_platform() in ("linux", "macos", "windows")
    with pytest.raises(SLError, match="unsupported platform"):
        current_platform("plan9")


@pytest.mark.parametrize("raw,expected", [("AMD64", "x86_64"), ("arm64", "aarch64"),
                                          ("i686", "x86"), ("armv7l", "arm")])
def test_current_arch(raw, expected):
    assert current_arch(raw) == expected


def test_current_arch_default_and_unsupported():
    assert current_arch() in ("x86_64", "aarch64", "x86", "arm")
    with pytest.raises(SLError, match="unsupported architecture"):
        current_arch("sparc")


def test_parse_version():
    assert parse_version("1.2.3") == (1, 2, 3)
    for bad in ("1.2", "x", 5):
        with pytest.raises(SLError):
            parse_version(bad)


@pytest.mark.parametrize("version,spec,ok", [
    ("1.5.0", "", True), ("1.5.0", "*", True), ("1.5.0", ">=1.0.0,<2.0.0", True),
    ("2.0.0", ">=1.0.0,<2.0.0", False), ("1.0.0", "==1.0.0", True),
    ("1.0.1", ">1.0.0", True), ("1.0.0", "<=1.0.0", True)])
def test_satisfies(version, spec, ok):
    assert satisfies(version, spec) is ok


@pytest.mark.parametrize("spec", ["~1.0", 5, ">=x"])
def test_satisfies_rejects_bad_range(spec):
    with pytest.raises(SLError):
        satisfies("1.0.0", spec)


def test_target_validation_and_str():
    assert str(Target("linux", "x86_64")) == "linux:x86_64"
    with pytest.raises(SLError, match="platform"):
        Target("beos", "x86_64")
    with pytest.raises(SLError, match="architecture"):
        Target("linux", "vax")


@pytest.mark.parametrize("overrides", [
    {"name": "1bad"}, {"version": "1"}, {"abi_version": 0}, {"abi_version": True},
    {"abi_version": "1"}, {"targets": ()}, {"dependencies": {"1x": "*"}},
    {"dependencies": {"ok": "~"}}, {"exports": ("a", "a")}, {"exports": ("a b",)},
    {"signatures": {"nope": "void nope(void)"}}, {"runtime": "other"},
    {"init": "bad name"}, {"fini": "1x"}])
def test_invalid_metadata(make_meta, overrides):
    with pytest.raises(SLError) as info:
        make_meta(**overrides)
    assert info.value.status is SLStatus.INVALID_CONTAINER


def test_duplicate_targets(make_meta):
    target = Target("linux", "x86_64")
    with pytest.raises(SLError):
        make_meta(targets=(target, target))


def test_roundtrip_and_with_targets(make_meta):
    meta = make_meta(dependencies={"b": ">=1.0.0"}, exports=("f",),
                     signatures={"f": "int f(void)"}, init="demo_init", fini="demo_fini",
                     runtime="embedded")
    assert Metadata.from_dict(meta.to_dict()) == meta
    two = meta.with_targets([Target("windows", "x86_64"), Target("linux", "x86_64")])
    assert [t.platform for t in two.targets] == ["linux", "windows"]


@pytest.mark.parametrize("data", [
    5, {"name": "a"}, {"name": "a", "version": "1.0.0", "abi_version": 1,
                       "targets": [], "extra": 1},
    {"name": "a", "version": "1.0.0", "abi_version": 1, "targets": [{"platform": "linux"}]},
    {"name": "a", "version": "1.0.0", "abi_version": 1, "targets": 7},
    {"name": "a", "version": "1.0.0", "abi_version": 1,
     "targets": [{"platform": "linux", "arch": "x86_64"}], "dependencies": 3}])
def test_from_dict_rejects(data):
    with pytest.raises(SLError):
        Metadata.from_dict(data)
