"""Das .sl-Containerformat: Metadaten plus ein Payload je Plattform/Architektur (Fat-Binary)."""
from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass

from .errors import SLError, SLStatus
from .metadata import Metadata, Target

MAGIC = b"\x89SLIB\r\n\x1a"  # genau 8 Byte
CONTAINER_VERSION = 1
_HEADER = struct.Struct("<8sHII")       # magic, version, meta_len, entry_count
_ENTRY = struct.Struct("<16s16sQQ32s")  # platform, arch, offset, length, sha256


def _bad(message: str) -> SLError:
    return SLError(SLStatus.INVALID_CONTAINER, message)


@dataclass(frozen=True)
class PayloadEntry:
    target: Target
    offset: int
    length: int
    sha256: bytes


class Container:
    def __init__(self, metadata: Metadata, entries: dict, blob: bytes):
        self.metadata = metadata
        self.entries = entries
        self._blob = blob

    @property
    def targets(self) -> list:
        return sorted(self.entries)

    def payload_for(self, platform: str, arch: str) -> bytes:
        entry = self.entries.get(Target(platform, arch))
        if entry is None:
            available = ", ".join(str(t) for t in self.targets)
            raise SLError(
                SLStatus.ARCH_MISMATCH,
                f"no payload for {platform}:{arch} (available: {available})",
                failed_name=self.metadata.name)
        data = self._blob[entry.offset:entry.offset + entry.length]
        if hashlib.sha256(data).digest() != entry.sha256:
            raise _bad(f"payload hash mismatch for {entry.target}")
        return data


def pack(metadata: Metadata, payloads: dict) -> bytes:
    if set(payloads) != set(metadata.targets):
        raise _bad("payload targets differ from metadata targets")
    meta_bytes = json.dumps(metadata.to_dict(), sort_keys=True).encode("utf-8")
    table, blob = [], bytearray()
    for target in sorted(payloads):
        data = bytes(payloads[target])
        table.append(_ENTRY.pack(target.platform.encode("ascii"), target.arch.encode("ascii"),
                                 len(blob), len(data), hashlib.sha256(data).digest()))
        blob += data
    head = _HEADER.pack(MAGIC, CONTAINER_VERSION, len(meta_bytes), len(table))
    return head + meta_bytes + b"".join(table) + bytes(blob)


def unpack(data: bytes) -> Container:
    if len(data) < _HEADER.size:
        raise _bad("file too short")
    magic, version, meta_len, count = _HEADER.unpack_from(data)
    if magic != MAGIC:
        raise _bad("bad magic number")
    if version != CONTAINER_VERSION:
        raise _bad(f"unsupported container version {version}")
    meta_end = _HEADER.size + meta_len
    table_end = meta_end + count * _ENTRY.size
    if table_end > len(data):
        raise _bad("truncated container")
    try:
        metadata = Metadata.from_dict(json.loads(data[_HEADER.size:meta_end]))
    except ValueError as exc:  # JSONDecodeError und UnicodeDecodeError
        raise _bad(f"unreadable metadata: {exc}") from exc
    blob = data[table_end:]
    entries = {}
    for index in range(count):
        plat, arch, offset, length, digest = _ENTRY.unpack_from(
            data, meta_end + index * _ENTRY.size)
        try:
            target = Target(plat.rstrip(b"\0").decode("ascii"), arch.rstrip(b"\0").decode("ascii"))
        except UnicodeDecodeError as exc:
            raise _bad("non-ascii target name") from exc
        if offset + length > len(blob):
            raise _bad("payload outside of container")
        entries[target] = PayloadEntry(target, offset, length, digest)
    if set(entries) != set(metadata.targets):
        raise _bad("payload table differs from metadata targets")
    return Container(metadata, entries, blob)
