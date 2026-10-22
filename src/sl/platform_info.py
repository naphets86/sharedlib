"""Normalisierung von Plattform- und Architekturnamen."""
from __future__ import annotations

import platform as _platform
import sys

from .errors import SLError, SLStatus

PLATFORMS = ("linux", "macos", "windows")
ARCHES = ("x86_64", "aarch64", "x86", "arm")
NATIVE_SUFFIX = {"linux": ".so", "macos": ".dylib", "windows": ".dll"}

_ARCH_ALIASES = {
    "x86_64": "x86_64", "amd64": "x86_64", "x64": "x86_64",
    "arm64": "aarch64", "aarch64": "aarch64",
    "i386": "x86", "i686": "x86", "x86": "x86",
    "armv7l": "arm", "arm": "arm",
}


def current_platform(sys_platform=None) -> str:
    raw = sys_platform or sys.platform
    if raw.startswith(("linux", "android")):
        return "linux"
    mapping = {"darwin": "macos", "win32": "windows", "cygwin": "windows"}
    if raw not in mapping:
        raise SLError(SLStatus.INTERNAL, f"unsupported platform '{raw}'")
    return mapping[raw]


def current_arch(machine=None) -> str:
    raw = (machine or _platform.machine()).lower()
    if raw not in _ARCH_ALIASES:
        raise SLError(SLStatus.INTERNAL, f"unsupported architecture '{raw}'")
    return _ARCH_ALIASES[raw]
