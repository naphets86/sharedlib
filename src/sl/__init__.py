"""sl - Referenzimplementierung des einheitlichen Shared-Library-Formats (.sl)."""
from .adapters import DarwinAdapter, LinuxAdapter, PlatformAdapter, WindowsAdapter, get_adapter
from .binding import Library, open
from .capi import ErrorInfo, default_loader, set_default_loader, sl_close, sl_info, sl_open, sl_symbol
from .container import Container, pack, unpack
from .errors import SLError, SLStatus
from .loader import Handle, Loader
from .metadata import Metadata, Target, satisfies

__version__ = "0.1.0"
__all__ = [
    "Container", "DarwinAdapter", "ErrorInfo", "Handle", "Library", "LinuxAdapter", "Loader",
    "Metadata", "PlatformAdapter", "SLError", "SLStatus", "Target", "WindowsAdapter",
    "default_loader", "get_adapter", "open", "pack", "satisfies", "set_default_loader",
    "sl_close", "sl_info", "sl_open", "sl_symbol", "unpack",
]
