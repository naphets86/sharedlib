"""Loader-Kern: die standardisierte Prozedur aus README Abschnitt 5.2."""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .adapters import PlatformAdapter, get_adapter
from .container import unpack
from .errors import SLError, SLStatus
from .metadata import Metadata, satisfies
from .platform_info import current_arch, current_platform
from .search import locate


@dataclass(eq=False)
class Handle:
    name: str
    path: str
    metadata: Metadata
    native: object
    loader: "Loader"
    deps: list = field(default_factory=list)
    refcount: int = 1
    closed: bool = False


class Loader:
    def __init__(self, adapter: PlatformAdapter | None = None, *, env=None,
                 requester_dir=None, app_dir=None, hardened=False,
                 abi_range=(1, 1), platform=None, arch=None):
        self.platform = platform or current_platform()
        self.arch = arch or current_arch()
        self.adapter = adapter or get_adapter(self.platform)
        self.env = os.environ if env is None else env
        self.requester_dir = requester_dir
        self.app_dir = app_dir
        self.hardened = hardened
        self.abi_range = abi_range
        self._loaded = {}
        self._loading = []
        self._lock = threading.RLock()

    # --- oeffentliche Operationen -------------------------------------------------
    def open(self, name_or_path: str, flags: int = 0) -> Handle:
        with self._lock:
            return self._open(name_or_path, None, self.requester_dir)

    def symbol(self, handle: Handle, name: str):
        self._require_open(handle)
        if name not in handle.metadata.exports:
            raise SLError(SLStatus.SYMBOL_NOT_FOUND,
                          f"symbol '{name}' is not exported by '{handle.name}'",
                          failed_name=name)
        return self.adapter.lookup(handle.native, name)

    def info(self, handle: Handle) -> dict:
        self._require_open(handle)
        meta = handle.metadata
        return {"name": meta.name, "version": meta.version, "abi_version": meta.abi_version,
                "path": handle.path, "dependencies": [d.name for d in handle.deps],
                "exports": list(meta.exports)}

    def close(self, handle: Handle) -> None:
        with self._lock:
            self._require_open(handle)
            self._release(handle)

    # --- Prozedur -----------------------------------------------------------------
    def _require_open(self, handle: Handle) -> None:
        if handle.closed:
            raise SLError(SLStatus.INTERNAL, f"handle for '{handle.name}' is already closed",
                          failed_name=handle.name)

    @staticmethod
    def _check_range(meta: Metadata, spec) -> None:
        if spec is not None and not satisfies(meta.version, spec):
            raise SLError(SLStatus.DEPENDENCY_MISSING,
                          f"'{meta.name}' {meta.version} does not satisfy '{spec}'",
                          failed_name=meta.name)

    def _open(self, name_or_path, spec, requester_dir) -> Handle:
        path, _tried = locate(name_or_path, env=self.env, requester_dir=requester_dir,
                              app_dir=self.app_dir, adapter=self.adapter,
                              hardened=self.hardened)
        key = os.path.realpath(path)
        if key in self._loading:
            raise SLError(SLStatus.CYCLE, f"cyclic dependency through '{name_or_path}'",
                          failed_name=name_or_path)
        handle = self._loaded.get(key)
        if handle is not None:
            self._check_range(handle.metadata, spec)
            handle.refcount += 1
            return handle
        self._loading.append(key)
        try:
            handle = self._load(key, spec)
        finally:
            self._loading.pop()
        self._loaded[key] = handle
        return handle

    def _read(self, path: str) -> bytes:
        try:
            return Path(path).read_bytes()
        except PermissionError as exc:
            raise SLError(SLStatus.ACCESS_DENIED, f"cannot read '{path}'",
                          failed_name=path, native_error=exc.errno or 0) from exc
        except OSError as exc:
            raise SLError(SLStatus.INTERNAL, f"cannot read '{path}'",
                          failed_name=path, native_error=exc.errno or 0) from exc

    def _load(self, path: str, spec) -> Handle:
        container = unpack(self._read(path))                      # Schritt 3
        meta = container.metadata
        low, high = self.abi_range
        if not low <= meta.abi_version <= high:
            raise SLError(SLStatus.ABI_MISMATCH,
                          f"'{meta.name}' has ABI {meta.abi_version}, supported {low}..{high}",
                          failed_name=meta.name)
        payload = container.payload_for(self.platform, self.arch)
        self._check_range(meta, spec)
        deps, native = [], None
        try:
            for dep, dep_spec in meta.dependencies.items():       # Schritt 4
                deps.append(self._open_dependency(meta, dep, dep_spec, path))
            try:
                native = self.adapter.map_payload(payload, meta.name)  # Schritt 5
            except OSError as exc:
                raise SLError(SLStatus.INTERNAL, f"mapping '{meta.name}' failed: {exc}",
                              failed_name=meta.name, native_error=exc.errno or 0) from exc
            handle = Handle(meta.name, path, meta, native, self, deps)
            if meta.init:                                         # Schritt 6
                self._run_init(handle)
            return handle
        except SLError:
            if native is not None:
                self.adapter.unmap(native)
            for dep_handle in deps:
                self._release(dep_handle)
            raise

    def _open_dependency(self, meta, dep, dep_spec, path) -> Handle:
        try:
            return self._open(dep, dep_spec, os.path.dirname(path))
        except SLError as exc:
            if exc.status is not SLStatus.NOT_FOUND:
                raise
            raise SLError(SLStatus.DEPENDENCY_MISSING,
                          f"dependency '{dep}' of '{meta.name}' not found",
                          failed_name=dep, searched=exc.searched) from exc

    def _run_init(self, handle: Handle) -> None:
        meta = handle.metadata
        try:
            result = self.adapter.lookup(handle.native, meta.init)()
        except SLError as exc:
            raise SLError(SLStatus.INIT_FAILED, f"init entry point of '{meta.name}' missing",
                          failed_name=meta.name) from exc
        if result != 0:
            raise SLError(SLStatus.INIT_FAILED, f"init of '{meta.name}' returned {result}",
                          failed_name=meta.name, native_error=result)

    def _release(self, handle: Handle) -> None:
        handle.refcount -= 1
        if handle.refcount > 0:
            return
        handle.closed = True
        del self._loaded[handle.path]
        if handle.metadata.fini:
            try:
                self.adapter.lookup(handle.native, handle.metadata.fini)()
            except SLError:
                pass  # fehlendes fini verhindert das Entladen nicht
        self.adapter.unmap(handle.native)
        for dep_handle in handle.deps:
            self._release(dep_handle)
