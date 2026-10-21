"""Standardisiertes Fehlermodell (README Abschnitt 5.6)."""
from __future__ import annotations

from enum import IntEnum


class SLStatus(IntEnum):
    OK = 0
    NOT_FOUND = 1
    DEPENDENCY_MISSING = 2
    ARCH_MISMATCH = 3
    ABI_MISMATCH = 4
    INVALID_CONTAINER = 5
    SYMBOL_NOT_FOUND = 6
    INIT_FAILED = 7
    CYCLE = 8
    ACCESS_DENIED = 9
    INTERNAL = 10

    @property
    def c_name(self) -> str:
        return "SL_OK" if self is SLStatus.OK else "SL_ERR_" + self.name


class SLError(Exception):
    """Fehler mit Status, stabilem Text und Diagnosedaten."""

    def __init__(self, status, message, *, failed_name="", searched=(), native_error=0):
        super().__init__(message)
        self.status = SLStatus(status)
        self.message = message
        self.failed_name = failed_name
        self.searched = tuple(searched)
        self.native_error = native_error

    def __str__(self) -> str:
        return f"{self.status.c_name}: {self.message}"
