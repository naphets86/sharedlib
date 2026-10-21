"""Python-Referenzbinding: sl.open(name) ist auf allen Plattformen identisch."""
from __future__ import annotations

from .capi import default_loader


class Library:
    def __init__(self, handle):
        self._handle = handle

    @property
    def info(self) -> dict:
        return self._handle.loader.info(self._handle)

    def symbol(self, name, argtypes=None, restype=None):
        func = self._handle.loader.symbol(self._handle, name)
        if argtypes is not None:
            func.argtypes = list(argtypes)
        if restype is not None:
            func.restype = restype
        return func

    def close(self) -> None:
        if self._handle is not None:
            handle, self._handle = self._handle, None
            handle.loader.close(handle)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def open(name_or_path, *, loader=None, flags=0) -> Library:  # noqa: A001
    return Library((loader or default_loader()).open(name_or_path, flags))
