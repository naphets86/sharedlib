"""Metadatenkopf eines .sl-Containers (README Abschnitt 6.2)."""
from __future__ import annotations

import operator
import re
from dataclasses import dataclass, field, replace

from .errors import SLError, SLStatus
from .platform_info import ARCHES, PLATFORMS

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_CONSTRAINT = re.compile(r"^(>=|<=|==|>|<)\s*(\d+\.\d+\.\d+)$")
_OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq,
        ">": operator.gt, "<": operator.lt}
_RUNTIMES = ("embedded", "external")
_KEYS = {"name", "version", "abi_version", "targets", "dependencies",
         "exports", "signatures", "runtime", "init", "fini"}


def _bad(message: str) -> SLError:
    return SLError(SLStatus.INVALID_CONTAINER, message)


def is_identifier(text) -> bool:
    return isinstance(text, str) and _IDENT.match(text) is not None


def parse_version(text) -> tuple:
    match = _VERSION.match(text) if isinstance(text, str) else None
    if match is None:
        raise _bad(f"invalid version '{text}'")
    return tuple(int(part) for part in match.groups())


def _parse_range(spec) -> list:
    if not isinstance(spec, str):
        raise _bad(f"invalid version range '{spec}'")
    if spec.strip() in ("", "*"):
        return []
    out = []
    for part in spec.split(","):
        match = _CONSTRAINT.match(part.strip())
        if match is None:
            raise _bad(f"invalid version range '{spec}'")
        out.append((_OPS[match.group(1)], parse_version(match.group(2))))
    return out


def satisfies(version: str, spec: str) -> bool:
    current = parse_version(version)
    return all(op(current, bound) for op, bound in _parse_range(spec))


@dataclass(frozen=True, order=True)
class Target:
    platform: str
    arch: str

    def __post_init__(self):
        if self.platform not in PLATFORMS:
            raise _bad(f"unknown platform '{self.platform}'")
        if self.arch not in ARCHES:
            raise _bad(f"unknown architecture '{self.arch}'")

    def __str__(self) -> str:
        return f"{self.platform}:{self.arch}"


@dataclass(frozen=True)
class Metadata:
    name: str
    version: str
    abi_version: int
    targets: tuple
    dependencies: dict = field(default_factory=dict)
    exports: tuple = ()
    signatures: dict = field(default_factory=dict)
    runtime: str = "external"
    init: str | None = None
    fini: str | None = None

    def __post_init__(self):
        if not is_identifier(self.name):
            raise _bad(f"invalid library name '{self.name}'")
        parse_version(self.version)
        if isinstance(self.abi_version, bool) or not isinstance(self.abi_version, int) \
                or self.abi_version < 1:
            raise _bad("abi_version must be an integer >= 1")
        if not self.targets or len(set(self.targets)) != len(self.targets):
            raise _bad("targets must be non-empty and unique")
        for dep, spec in self.dependencies.items():
            if not is_identifier(dep):
                raise _bad(f"invalid dependency name '{dep}'")
            _parse_range(spec)
        if len(set(self.exports)) != len(self.exports) \
                or not all(is_identifier(e) for e in self.exports):
            raise _bad("exports must be unique identifiers")
        if not set(self.signatures) <= set(self.exports):
            raise _bad("signature given for a symbol that is not exported")
        if self.runtime not in _RUNTIMES:
            raise _bad(f"invalid runtime '{self.runtime}'")
        for hook in (self.init, self.fini):
            if hook is not None and not is_identifier(hook):
                raise _bad(f"invalid lifecycle entry point '{hook}'")

    def with_targets(self, targets) -> "Metadata":
        return replace(self, targets=tuple(sorted(targets)))

    def to_dict(self) -> dict:
        return {
            "name": self.name, "version": self.version,
            "abi_version": self.abi_version,
            "targets": [{"platform": t.platform, "arch": t.arch} for t in self.targets],
            "dependencies": dict(sorted(self.dependencies.items())),
            "exports": list(self.exports),
            "signatures": dict(sorted(self.signatures.items())),
            "runtime": self.runtime, "init": self.init, "fini": self.fini,
        }

    @classmethod
    def from_dict(cls, data) -> "Metadata":
        if not isinstance(data, dict):
            raise _bad("metadata must be an object")
        unknown = set(data) - _KEYS
        if unknown:
            raise _bad(f"unknown metadata keys: {sorted(unknown)}")
        missing = {"name", "version", "abi_version", "targets"} - set(data)
        if missing:
            raise _bad(f"missing metadata keys: {sorted(missing)}")
        try:
            targets = tuple(Target(t["platform"], t["arch"]) for t in data["targets"])
            return cls(
                name=data["name"], version=data["version"],
                abi_version=data["abi_version"], targets=targets,
                dependencies=dict(data.get("dependencies", {})),
                exports=tuple(data.get("exports", ())),
                signatures=dict(data.get("signatures", {})),
                runtime=data.get("runtime", "external"),
                init=data.get("init"), fini=data.get("fini"),
            )
        except (TypeError, KeyError, ValueError) as exc:
            raise _bad(f"malformed metadata: {exc}") from exc
