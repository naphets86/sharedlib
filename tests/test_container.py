import struct

import pytest

from sl.container import CONTAINER_VERSION, MAGIC, pack, unpack
from sl.errors import SLError, SLStatus
from sl.metadata import Target

LIN = Target("linux", "x86_64")
MAC = Target("macos", "aarch64")


def _entry_offset(data):
    meta_len = struct.unpack_from("<8sHII", data)[2]
    return 18 + meta_len


def test_magic_is_eight_bytes():
    assert len(MAGIC) == 8


def test_fat_roundtrip(make_meta):
    meta = make_meta(targets=(LIN, MAC))
    container = unpack(pack(meta, {MAC: b"mac-bytes", LIN: b"lin-bytes"}))
    assert container.metadata == meta
    assert container.targets == [LIN, MAC]
    assert container.payload_for("linux", "x86_64") == b"lin-bytes"
    assert container.payload_for("macos", "aarch64") == b"mac-bytes"


def test_missing_target_is_arch_mismatch(make_meta):
    container = unpack(pack(make_meta(), {LIN: b"x"}))
    with pytest.raises(SLError) as info:
        container.payload_for("windows", "x86_64")
    assert info.value.status is SLStatus.ARCH_MISMATCH
    assert "linux:x86_64" in str(info.value)


def test_pack_requires_matching_payloads(make_meta):
    with pytest.raises(SLError, match="differ"):
        pack(make_meta(), {MAC: b"x"})


def test_hash_mismatch(make_meta):
    data = bytearray(pack(make_meta(), {LIN: b"payload"}))
    data[-1] ^= 0xFF
    with pytest.raises(SLError, match="hash"):
        unpack(bytes(data)).payload_for("linux", "x86_64")


def test_short_magic_version_and_truncation(make_meta):
    good = pack(make_meta(), {LIN: b"x"})
    with pytest.raises(SLError, match="too short"):
        unpack(b"SL")
    with pytest.raises(SLError, match="magic"):
        unpack(b"\x00" * 8 + good[8:])
    bad_version = MAGIC + struct.pack("<HII", CONTAINER_VERSION + 1, 0, 0)
    with pytest.raises(SLError, match="version"):
        unpack(bad_version)
    with pytest.raises(SLError, match="truncated"):
        unpack(good[:20])


def test_unreadable_metadata():
    meta = b"{not json"
    data = struct.pack("<8sHII", MAGIC, CONTAINER_VERSION, len(meta), 0) + meta
    with pytest.raises(SLError, match="unreadable"):
        unpack(data)


def test_table_errors(make_meta):
    good = pack(make_meta(), {LIN: b"payload"})
    start = _entry_offset(good)
    ascii_bad = bytearray(good)
    ascii_bad[start] = 0xFF
    with pytest.raises(SLError, match="non-ascii"):
        unpack(bytes(ascii_bad))
    outside = bytearray(good)
    struct.pack_into("<Q", outside, start + 40, 10_000)
    with pytest.raises(SLError, match="outside"):
        unpack(bytes(outside))
    renamed = bytearray(good)
    renamed[start:start + 5] = b"macos"
    with pytest.raises(SLError, match="differs"):
        unpack(bytes(renamed))
