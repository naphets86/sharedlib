from types import SimpleNamespace

import pytest

import sl
from sl.adapters import PlatformAdapter
from sl.container import pack
from sl.errors import SLError, SLStatus
from sl.metadata import Metadata, Target

LINUX = Target("linux", "x86_64")


class FakeAdapter(PlatformAdapter):
    """Plattformunabhaengiger Adapter: keine echten nativen Bibliotheken."""

    platform = "linux"

    def __init__(self):
        self.symbols = {}
        self.mapped = []
        self.unmapped = []
        self.fail_map = None

    def system_dirs(self, env):
        return []

    def _release(self, cdll):
        pass

    def map_payload(self, payload, name):
        if self.fail_map is not None:
            raise self.fail_map
        self.mapped.append(name)
        return SimpleNamespace(name=name, payload=payload)

    def lookup(self, native, symbol):
        table = self.symbols.get(native.name, {})
        if symbol not in table:
            raise SLError(SLStatus.SYMBOL_NOT_FOUND, f"no {symbol}", failed_name=symbol)
        return table[symbol]

    def unmap(self, native):
        self.unmapped.append(native.name)


@pytest.fixture
def make_meta():
    def factory(**overrides):
        base = {"name": "demo", "version": "1.0.0", "abi_version": 1, "targets": (LINUX,)}
        base.update(overrides)
        return Metadata(**base)
    return factory


@pytest.fixture
def write_sl(tmp_path):
    def writer(name, directory=None, **overrides):
        overrides.setdefault("targets", (LINUX,))
        meta = Metadata(name=name, version=overrides.pop("version", "1.0.0"),
                        abi_version=overrides.pop("abi_version", 1), **overrides)
        path = (directory or tmp_path) / f"{name}.sl"
        path.write_bytes(pack(meta, {t: name.encode() for t in meta.targets}))
        return path
    return writer


@pytest.fixture
def adapter():
    return FakeAdapter()


@pytest.fixture
def loader(adapter, tmp_path):
    return sl.Loader(adapter, env={"SL_PATH": str(tmp_path)}, platform="linux", arch="x86_64")
