"""Plattformadapter: der einzige OS-spezifische Code (README Abschnitt 5.1)."""
from __future__ import annotations

import abc
import ctypes
import os
import shutil
import tempfile
from dataclasses import dataclass

import _ctypes

from .errors import SLError, SLStatus
from .platform_info import NATIVE_SUFFIX, current_platform


@dataclass(eq=False)
class NativeLib:
    cdll: object
    path: str
    tmpdir: str


class PlatformAdapter(abc.ABC):
    platform: str

    @property
    def native_suffix(self) -> str:
        return NATIVE_SUFFIX[self.platform]

    @abc.abstractmethod
    def system_dirs(self, env) -> list:
        """Systemweite Suchverzeichnisse, ausschliesslich diese."""

    @abc.abstractmethod
    def _release(self, cdll) -> None:
        """Gibt das native Handle frei (dlclose bzw. FreeLibrary)."""

    def _open(self, path: str):
        return ctypes.CDLL(path)

    def map_payload(self, payload: bytes, name: str) -> NativeLib:
        tmpdir = tempfile.mkdtemp(prefix="sl-")
        path = os.path.join(tmpdir, name + self.native_suffix)
        try:
            with open(path, "wb") as handle:
                handle.write(payload)
            return NativeLib(self._open(path), path, tmpdir)
        except OSError:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise

    def lookup(self, native: NativeLib, symbol: str):
        try:
            return getattr(native.cdll, symbol)
        except AttributeError as exc:
            raise SLError(SLStatus.SYMBOL_NOT_FOUND,
                          f"symbol '{symbol}' not found in native payload",
                          failed_name=symbol) from exc

    def unmap(self, native: NativeLib) -> None:
        self._release(native.cdll)
        shutil.rmtree(native.tmpdir, ignore_errors=True)


class _PosixAdapter(PlatformAdapter):
    def _release(self, cdll) -> None:
        _ctypes.dlclose(cdll._handle)


class LinuxAdapter(_PosixAdapter):
    platform = "linux"

    def system_dirs(self, env) -> list:
        return ["/usr/local/lib/sl", "/usr/lib/sl"]


class DarwinAdapter(_PosixAdapter):
    platform = "macos"

    def system_dirs(self, env) -> list:
        return ["/usr/local/lib/sl", "/opt/homebrew/lib/sl"]


class WindowsAdapter(PlatformAdapter):
    platform = "windows"

    def system_dirs(self, env) -> list:
        roots = [env[key] for key in ("ProgramData", "ProgramFiles") if env.get(key)]
        return [os.path.join(root, "sl") for root in roots]

    def _release(self, cdll) -> None:
        _ctypes.FreeLibrary(cdll._handle)


_ADAPTERS = {"linux": LinuxAdapter, "macos": DarwinAdapter, "windows": WindowsAdapter}


def get_adapter(platform=None) -> PlatformAdapter:
    return _ADAPTERS[platform or current_platform()]()
