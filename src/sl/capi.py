"""C-artige Statusschnittstelle (sl_open, sl_symbol, sl_info, sl_close)."""
from __future__ import annotations

from dataclasses import dataclass

from .errors import SLError, SLStatus
from .loader import Loader


@dataclass
class ErrorInfo:
    code: SLStatus = SLStatus.OK
    message: str = ""
    failed_name: str = ""
    searched: str = ""
    native_error: int = 0


_default_loader = None


def default_loader() -> Loader:
    global _default_loader
    if _default_loader is None:
        _default_loader = Loader()
    return _default_loader


def set_default_loader(loader) -> None:
    global _default_loader
    _default_loader = loader


def _error(exc: SLError) -> ErrorInfo:
    return ErrorInfo(exc.status, exc.message, exc.failed_name,
                     "\n".join(exc.searched), exc.native_error)


def sl_open(name_or_path, flags=0, loader=None):
    try:
        return SLStatus.OK, (loader or default_loader()).open(name_or_path, flags), ErrorInfo()
    except SLError as exc:
        return exc.status, None, _error(exc)


def sl_symbol(handle, symbol):
    try:
        return SLStatus.OK, handle.loader.symbol(handle, symbol), ErrorInfo()
    except SLError as exc:
        return exc.status, None, _error(exc)


def sl_info(handle):
    try:
        return SLStatus.OK, handle.loader.info(handle), ErrorInfo()
    except SLError as exc:
        return exc.status, None, _error(exc)


def sl_close(handle):
    try:
        handle.loader.close(handle)
        return SLStatus.OK, ErrorInfo()
    except SLError as exc:
        return exc.status, _error(exc)
