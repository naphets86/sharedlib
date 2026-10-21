"""Build-Orchestrierung: Toolchain-Plan, Kompilierung, Packen zum Fat-Container."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .container import pack
from .errors import SLError, SLStatus
from .metadata import Metadata, Target
from .platform_info import NATIVE_SUFFIX, current_arch, current_platform

_FLAGS = {
    "linux": ["-shared", "-fPIC", "-fvisibility=hidden"],
    "macos": ["-dynamiclib", "-fvisibility=hidden"],
    "windows": ["-shared"],
}
_DARWIN_ARCH = {"x86_64": "x86_64", "aarch64": "arm64"}


def toolchain_flags(platform: str, arch: str) -> list:
    flags = list(_FLAGS[platform])
    if platform == "macos":
        if arch not in _DARWIN_ARCH:
            raise ValueError(f"architecture '{arch}' is not supported on macos")
        flags += ["-arch", _DARWIN_ARCH[arch]]
    return flags


def build_matrix(metadata: Metadata, compiler: str = "cc") -> list:
    return [{"platform": t.platform, "arch": t.arch,
             "output": metadata.name + NATIVE_SUFFIX[t.platform],
             "compiler": compiler, "flags": toolchain_flags(t.platform, t.arch)}
            for t in metadata.targets]


def compile_command(compiler, sources, output, platform, arch,
                    include_dirs=(), defines=()) -> list:
    return ([compiler, *toolchain_flags(platform, arch)]
            + [f"-I{d}" for d in include_dirs] + [f"-D{d}" for d in defines]
            + ["-o", str(output), *map(str, sources)])


def find_compiler(env=None, which=shutil.which) -> str:
    env = os.environ if env is None else env
    if env.get("CC"):
        return env["CC"]
    for candidate in ("cc", "gcc", "clang", "cl", "gcc.exe", "clang.exe"):
        found = which(candidate)
        if found:
            return found
    raise SLError(SLStatus.INTERNAL, "no C compiler found (set CC)")


def build_native(sources, output, *, compiler=None, platform=None, arch=None,
                 include_dirs=(), defines=()) -> Path:
    command = compile_command(compiler or find_compiler(), sources, output,
                              platform or current_platform(), arch or current_arch(),
                              include_dirs, defines)
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except OSError as exc:
        raise SLError(SLStatus.INTERNAL, f"cannot run compiler: {exc}",
                      native_error=exc.errno or 0) from exc
    if result.returncode != 0:
        raise SLError(SLStatus.INTERNAL, f"compilation failed:\n{result.stderr}",
                      native_error=result.returncode)
    return Path(output)


def pack_files(metadata: Metadata, files: dict, output) -> Path:
    """Packt vorhandene Plattform-Binaries {Target: Pfad} zu einem Fat-.sl."""
    payloads = {target: Path(path).read_bytes() for target, path in files.items()}
    data = pack(metadata.with_targets(payloads), payloads)
    out = Path(output)
    out.write_bytes(data)
    return out


def build_sl(metadata: Metadata, sources, output, *, compiler=None, platform=None,
             arch=None, extra_files=None, include_dirs=(), defines=()) -> Path:
    """Kompiliert fuer das Host-Target und ergaenzt vorgebaute Payloads anderer Targets."""
    host = Target(platform or current_platform(), arch or current_arch())
    with tempfile.TemporaryDirectory() as tmp:
        lib = Path(tmp) / (metadata.name + NATIVE_SUFFIX[host.platform])
        build_native(sources, lib, compiler=compiler, platform=host.platform,
                     arch=host.arch, include_dirs=include_dirs, defines=defines)
        files = {**(extra_files or {}), host: lib}
        return pack_files(metadata, files, output)
