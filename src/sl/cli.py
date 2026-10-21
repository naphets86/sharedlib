"""Kommandozeile: sl info | pack | gen | build | matrix."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .build import build_matrix, build_sl, pack_files
from .codegen import generate_all
from .container import unpack
from .errors import SLError
from .metadata import Metadata, Target


def _target_file(text: str) -> tuple:
    spec, sep, path = text.partition("=")
    plat, colon, arch = spec.partition(":")
    if not (sep and colon):
        raise argparse.ArgumentTypeError(f"expected PLATFORM:ARCH=PATH, got '{text}'")
    try:
        return Target(plat, arch), path
    except SLError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _load_meta(path: str) -> Metadata:
    return Metadata.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sl")
    sub = parser.add_subparsers(dest="command", required=True)
    info = sub.add_parser("info", help="show metadata of a .sl file")
    info.add_argument("file")
    pack = sub.add_parser("pack", help="pack native payloads into a fat .sl")
    pack.add_argument("--meta", required=True)
    pack.add_argument("--payload", action="append", type=_target_file, required=True)
    pack.add_argument("-o", "--output", required=True)
    gen = sub.add_parser("gen", help="generate header, C source, CMake, binding")
    gen.add_argument("--meta", required=True)
    gen.add_argument("-o", "--outdir", required=True)
    build = sub.add_parser("build", help="compile sources and pack for the host target")
    build.add_argument("--meta", required=True)
    build.add_argument("--source", action="append", required=True)
    build.add_argument("--extra", action="append", type=_target_file, default=[])
    build.add_argument("-I", "--include", action="append", default=[])
    build.add_argument("-D", "--define", action="append", default=[])
    build.add_argument("-o", "--output", required=True)
    matrix = sub.add_parser("matrix", help="print the build matrix as JSON")
    matrix.add_argument("--meta", required=True)
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "info":
            container = unpack(Path(args.file).read_bytes())
            data = container.metadata.to_dict()
            data["payloads"] = [str(t) for t in container.targets]
            print(json.dumps(data, indent=2, sort_keys=True))
        elif args.command == "pack":
            print(pack_files(_load_meta(args.meta), dict(args.payload), args.output))
        elif args.command == "gen":
            for path in generate_all(_load_meta(args.meta), args.outdir):
                print(path)
        elif args.command == "build":
            print(build_sl(_load_meta(args.meta), args.source, args.output,
                           extra_files=dict(args.extra), include_dirs=args.include,
                           defines=args.define))
        else:
            print(json.dumps(build_matrix(_load_meta(args.meta)), indent=2))
    except (SLError, ValueError, OSError) as exc:
        print(f"sl: error: {exc}", file=sys.stderr)
        return 2
    return 0
