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
            [device_enter=<r> device_exit=<r>]
    source <path>
    driver_source <path>

`type` is the argument's metadata type; `module` holds the handler routines
and `type_module` declares the type. `source` lines name the Fortran files
the handlers need, relative to the registry file; they are compiled into
the captured model and into every test driver that uses a handled type.
`driver_source` files are compiled into those test drivers only, never
into the model: a stand-in for something the model gets from the host
(e.g. a plain-NetCDF implementation of an I/O interface the host
implements with PIO), which would clash with the host's in the model.

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

Optional, both or neither, for GPU builds of the test drivers:

    device_enter(obj)
        put obj's data on the device (OpenACC/OpenMP enter data);
    device_exit(obj, copy_out)
        end that: copy the data back to the host when copy_out (an out or
        inout argument), else delete it.

A test driver calls them around the call of a scheme whose own directives
name the argument (or a component of it), so the scheme finds its data
present, as in a production run where the data stays on the device
between schemes; the comparison then checks what the scheme left on the
device.
"""

import functools
import os
from dataclasses import dataclass

from xdsl_ccpp.util.errors import CcppInputError

_HANDLER_KEYS = ("module", "type_module", "write", "read", "compare")
_OPTIONAL_KEYS = ("dims", "device_enter", "device_exit")


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
    device_enter: "str | None" = None
    device_exit: "str | None" = None


@dataclass(frozen=True)
class DdtHandlerRegistry:
    """A parsed registry file: handlers by lower-case type name, the
    sources (absolute paths) they need, and the sources only the test
    drivers compile."""

    path: str
    handlers: dict
    sources: tuple
    driver_sources: tuple = ()


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
    if ("device_enter" in settings) != ("device_exit" in settings):
        raise _error(path, line_no,
                     f"handler {type_name}: device_enter and device_exit go together")
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
    driver_sources: list = []
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
            elif keyword in ("source", "driver_source"):
                if len(rest) != 1:
                    raise _error(path, line_no, f"{keyword}: expected one path")
                source = os.path.normpath(os.path.join(base, rest[0]))
                if not os.path.isfile(source):
                    raise _error(path, line_no, f"{keyword}: no file {source}")
                if source in sources or source in driver_sources:
                    raise _error(path, line_no, f"{keyword}: {rest[0]} listed twice")
                (sources if keyword == "source" else driver_sources).append(source)
            else:
                raise _error(path, line_no, f"unknown keyword '{keyword}' "
                                            f"(expected 'handler', 'source' or 'driver_source')")
    return DdtHandlerRegistry(path, handlers, tuple(sources), tuple(driver_sources))
