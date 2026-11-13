"""Derived-type capture handlers supplied by the physics side
(scheme-io-capture-rte-objects).

The scheme I/O capture records intrinsic arguments and flat derived types
itself. A derived type it cannot read (private or pointer components, type
extension, ...) can be captured through handler routines its owner writes,
using the type's public procedures. xdsl_ccpp knows nothing about such a
type: a registry file names it, the handler routines and their sources, and
the host passes the file (--capture-ddt-handlers).

Registry format, one entry per line, `#` starts a comment:

    handler <type> module=<m> type_module=<m> write=<r> read=<r> compare=<r> [dims=<std>,...]
    source <path>

`type` is the argument's metadata type; `module` holds the handler routines
and `type_module` declares the type. `source` lines name the Fortran files
the handlers need, relative to the registry file; they are compiled into
the captured model and into every test driver that uses a handled type.

The routines (`dims` are extra integer arguments, the values of the scheme
call's arguments with those standard names, in order):

    write(name, obj, dims...)
        record obj as sub-group <name> of the capture group being written
        (ccpp_capture_begin_ddt / ccpp_capture_end_ddt);
    read(group, name, obj, dims...)
        rebuild obj from sub-group <name> of <group> ("in" or "out");
    compare(group, name, obj, tolerance, call_count, n_failed, dims...)
        compare obj with sub-group <name> of <group>, reporting each part
        through ccpp_capture_report (which counts failures in n_failed).
"""

import functools
import os
from dataclasses import dataclass

from xdsl_ccpp.util.errors import CcppInputError

_HANDLER_KEYS = ("module", "type_module", "write", "read", "compare")
_OPTIONAL_KEYS = ("dims",)


@dataclass(frozen=True)
class DdtHandler:
    """One registry `handler` line."""

    type_name: str
    module: str
    type_module: str
    write: str
    read: str
    compare: str
    dims: tuple = ()


@dataclass(frozen=True)
class DdtHandlerRegistry:
    """A parsed registry file: handlers by lower-case type name, and the
    sources (absolute paths) they need."""

    path: str
    handlers: dict
    sources: tuple


def _error(path: str, line_no: int, message: str) -> CcppInputError:
    return CcppInputError(f"{path}:{line_no}: {message}")


def _parse_handler(path: str, line_no: int, words: list) -> DdtHandler:
    if not words:
        raise _error(path, line_no, "handler: missing the type name")
    type_name, settings = words[0], {}
    for word in words[1:]:
        key, sep, value = word.partition("=")
        if not sep or not value:
            raise _error(path, line_no, f"handler {type_name}: expected key=value, got '{word}'")
        if key not in _HANDLER_KEYS + _OPTIONAL_KEYS:
            raise _error(path, line_no, f"handler {type_name}: unknown key '{key}'")
        if key in settings:
            raise _error(path, line_no, f"handler {type_name}: '{key}' given twice")
        settings[key] = value
    missing = [key for key in _HANDLER_KEYS if key not in settings]
    if missing:
        raise _error(path, line_no, f"handler {type_name}: missing {', '.join(missing)}")
    dims = tuple(d for d in settings.pop("dims", "").split(",") if d)
    return DdtHandler(type_name.lower(), dims=dims, **settings)


@functools.lru_cache(maxsize=None)
def parse_ddt_handlers(path: "str | None") -> "DdtHandlerRegistry | None":
    """The registry in *path* (None without one); a malformed line or a
    missing source is a CcppInputError naming the file and line."""
    if not path:
        return None
    path = os.path.abspath(path)
    base = os.path.dirname(path)
    handlers: dict = {}
    sources: list = []
    with open(path) as f:
        for line_no, raw in enumerate(f, start=1):
            words = raw.split("#", 1)[0].split()
            if not words:
                continue
            keyword, rest = words[0], words[1:]
            if keyword == "handler":
                handler = _parse_handler(path, line_no, rest)
                if handler.type_name in handlers:
                    raise _error(path, line_no, f"handler {handler.type_name}: listed twice")
                handlers[handler.type_name] = handler
            elif keyword == "source":
                if len(rest) != 1:
                    raise _error(path, line_no, "source: expected one path")
                source = os.path.normpath(os.path.join(base, rest[0]))
                if not os.path.isfile(source):
                    raise _error(path, line_no, f"source: no file {source}")
                if source not in sources:
                    sources.append(source)
            else:
                raise _error(path, line_no, f"unknown keyword '{keyword}' "
                                            f"(expected 'handler' or 'source')")
    return DdtHandlerRegistry(path, handlers, tuple(sources))
