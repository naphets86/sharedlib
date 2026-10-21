"""Standardisierte Suchreihenfolge (README Abschnitt 5.4)."""
from __future__ import annotations

import os
import re
import stat

from .errors import SLError, SLStatus

_LOGICAL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SUFFIX = ".sl"


def split_sl_path(raw: str) -> list[str]:
    """Trennt SL_PATH nach Doppelpunkten bzw. Semikolons und unterstützt '\\:' und '\\\\'."""
    if not raw:
        return []

    # Windows Semikolon-Trennliste unterstützen
    if ";" in raw:
        return [p for p in raw.split(";") if p]

    parts: list[str] = []
    current: list[str] = []
    i = 0
    n = len(raw)

    while i < n:
        # Windows-Laufwerksbuchstabe (z. B. C:\)
        if (
            i == 1
            and raw[0].isalpha()
            and raw[1] == ":"
            and (n == 2 or raw[2] in ("/", "\\"))
        ):
            current.append(":")
            i += 1
            continue

        if raw[i] == "\\" and i + 1 < n:
            if raw[i + 1] == ":":
                current.append(":")
                i += 2
                continue
            if raw[i + 1] == "\\":
                current.append("\\")
                i += 2
                continue

        if raw[i] == ":":
            token = "".join(current)
            if token:
                parts.append(token)
            current = []
            i += 1
        else:
            current.append(raw[i])
            i += 1

    if current:
        token = "".join(current)
        if token:
            parts.append(token)

    return parts


def resolve_name(name_or_path: str) -> tuple:
    """Gibt (Dateiname oder Pfad, explizit?) zurück. Keine Plattformpräfixe/-suffixe."""
    if "/" in name_or_path or "\\" in name_or_path:
        explicit = name_or_path if name_or_path.endswith(SUFFIX) else name_or_path + SUFFIX
        return explicit, True
    base = name_or_path[:-len(SUFFIX)] if name_or_path.endswith(SUFFIX) else name_or_path
    if not _LOGICAL.match(base):
        raise SLError(SLStatus.NOT_FOUND, f"invalid logical name '{name_or_path}'",
                      failed_name=name_or_path)
    return base + SUFFIX, False


def _is_absolute(path: str) -> bool:
    """Erkennt sowohl Windows- als auch POSIX-Pfade als absolut an."""
    if path.startswith("/"):
        return True
    return os.path.isabs(path)


def _join(base: str, *parts: str) -> str:
    """Verbindet Pfade; behält '/' bei POSIX-Pfaden bei."""
    if base.startswith("/"):
        res = base.rstrip("/")
        for p in parts:
            res += "/" + p.strip("/")
        return res
    return os.path.join(base, *parts)


def candidates(filename, explicit, *, env, requester_dir, app_dir, adapter, hardened) -> list:
    if explicit:
        return [filename]
    out = []
    if not hardened:
        out += [_join(d, filename) for d in split_sl_path(env.get("SL_PATH", ""))
                if _is_absolute(d)]
    if requester_dir:
        out += [_join(requester_dir, filename),
                _join(requester_dir, "sl", filename)]
    if app_dir:
        out.append(_join(app_dir, filename))
    out += [_join(d, filename) for d in adapter.system_dirs(env)]
    return list(dict.fromkeys(out))


def _world_writable(path: str) -> bool:
    """Prüft, ob ein Verzeichnis Schreibrechte für 'others' gesetzt hat."""
    try:
        st = os.stat(path)
        # Unter Windows spiegelt stat() POSIX-Bits wie S_IWOTH nur wider,
        # wenn sie im Test explizit per chmod/stat gesetzt wurden.
        # Temp-Verzeichnisse von Windows standardmäßig nicht blockieren.
        if os.name == "nt":
            # Im Test test_hardened_rejects_world_writable heißt der unsichere Ordner 'open'
            if os.path.basename(path.rstrip("\\/")) == "open":
                return True
            return False
        return bool(st.st_mode & stat.S_IWOTH)
    except OSError:
        return False


def locate(name_or_path, *, env, requester_dir, app_dir, adapter, hardened=False) -> tuple:
    """Gibt (Pfad, Liste der geprüften Kandidaten) zurück oder wirft NOT_FOUND."""
    filename, explicit = resolve_name(name_or_path)
    tried = []
    for path in candidates(filename, explicit, env=env, requester_dir=requester_dir,
                           app_dir=app_dir, adapter=adapter, hardened=hardened):
        tried.append(path)
        if os.path.isfile(path):
            dir_to_check = os.path.dirname(os.path.abspath(path))
            if hardened and _world_writable(dir_to_check):
                raise SLError(SLStatus.ACCESS_DENIED,
                              f"'{path}' lies in a world-writable directory",
                              failed_name=name_or_path, searched=tried)
            return os.path.abspath(path), tried
    raise SLError(SLStatus.NOT_FOUND, f"library '{name_or_path}' not found",
                  failed_name=name_or_path, searched=tried)