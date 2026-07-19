"""Python API frontend for the CCPP compiler.

Users write a Python file that imports this module, declares arguments, schemes,
DDTs, and suites using decorators, then calls :func:`emit_ir` to produce the
same MLIR as the XML/meta frontend.

There are two ways to define scheme argument metadata:

**Inline** — define arguments directly in Python (no ``.meta`` file needed)::

    from xdsl_ccpp.frontend.py_api import Arg, ccpp_scheme, ccpp_suite, emit_ir

    @ccpp_scheme
    class my_scheme:
        run = [Arg("ncol", standard_name="horizontal_loop_extent",
                   type="integer", units="count", intent="in"), ...]

    @ccpp_suite("my_suite", version="1.0")
    class my_suite:
        physics = [my_scheme]

    if __name__ == "__main__":
        emit_ir(my_suite)

**From .meta files** — load existing ``.meta`` files and write only the suite
orchestration in Python (backwards-compatible path)::

    from xdsl_ccpp.frontend.py_api import ccpp_scheme_from_meta, ccpp_suite, emit_ir

    kessler        = ccpp_scheme_from_meta("examples/kessler/scheme/kessler.meta")
    kessler_update = ccpp_scheme_from_meta("examples/kessler/scheme/kessler_update.meta")

    @ccpp_suite("kessler_suite", version="1.0")
    class kessler_suite:
        def run():
            kessler()
            kessler_update()

    if __name__ == "__main__":
        emit_ir(kessler_suite)

The output can be piped directly into ``ccpp_opt``::

    python3 my_suite.py | python3 -m xdsl_ccpp.tools.ccpp_opt -p ... -t ftn
"""

from __future__ import annotations

import sys
import types as _types
from dataclasses import dataclass, field

from xdsl.dialects.builtin import ModuleOp, StringAttr

from xdsl_ccpp.util.ccpp_conventions import CCPP_ERROR_MESSAGE, CCPP_ERROR_CODE, CCPP_ERRMSG_LEN
from xdsl_ccpp.dialects.ccpp import (
    ArgumentOp,
    ArgumentTableOp,
    GroupOp,
    SchemeOp,
    SubcycleOp,
    SuiteOp,
    TablePropertiesOp,
)

# ---------------------------------------------------------------------------
# Compile-time parameter helper
# ---------------------------------------------------------------------------


def ccpp_param(name: str, default, type=int):
    """Return a compile-time parameter, optionally overridden from the command line.

    Scans ``sys.argv`` for a token of the form ``name=value``.  If found,
    returns the value cast to *type*; otherwise returns *default*.  The value
    is resolved when the Python script is executed (i.e. at IR-generation time)
    and is baked into the generated Fortran as a fixed repetition count or
    constant.

    Typical use — define a default in the script and let callers override it::

        top = ccpp_param("top", default=19)

        @ccpp_suite("my_suite")
        class my_suite:
            physics = [hello_scheme]
            def run():
                for i in range(0, top):
                    hello_scheme()

    Default run::

        python3 my_suite.py            # top=19

    CLI override (any value the user provides)::

        python3 my_suite.py top=53     # top=53

    Args:
        name:    Parameter name, matched against ``key=value`` tokens in argv.
        default: Value returned when the parameter is absent from argv.
        type:    Callable used to coerce the string value (default: ``int``).
    """
    prefix = f"{name}="
    for token in sys.argv[1:]:
        if token.startswith(prefix):
            return type(token[len(prefix) :])
    return default


# Class attribute names recognised as scheme entry points.
# Each name maps to the suffix appended to the scheme name in Fortran,
# e.g. attribute ``run`` → Fortran subroutine ``{scheme}_run``.
_ENTRY_POINTS = [
    "run",
    "init",
    "finalize",
    "timestep_init",
    "timestep_final",
    "register",
]


# ---------------------------------------------------------------------------
# Public data class
# ---------------------------------------------------------------------------


@dataclass
class Arg:
    """A CCPP argument — one entry in a scheme, DDT, module, or host arg table.

    Args:
        name:          Fortran variable name (e.g. ``"temp_layer"``).
        standard_name: CCPP standard variable identifier used for matching.
        type:          ``"integer"``, ``"real"``, ``"character"``, or a DDT name.
        intent:        ``"in"``, ``"out"``, or ``"inout"``; omit for DDT fields.
        units:         Physical units string (e.g. ``"K"``, ``"none"``).
        dimensions:    Tuple of dimension standard names; empty tuple = scalar.
        kind:          Optional kind specifier (e.g. ``"kind_phys"``, ``"len=512"``).
        long_name:     Optional human-readable description.
        optional:      Whether the argument is optional.
        extra:         Pass-through attributes not explicitly modeled above
                       (e.g. ``memory_space``, ``state_variable``, ``active``).
                       Values are forwarded as-is to
                       :class:`~xdsl_ccpp.dialects.ccpp.ArgumentOp`.
    """

    name: str
    standard_name: str
    type: str
    intent: str = ""
    units: str = ""
    dimensions: tuple[str, ...] = field(default_factory=tuple)
    kind: str | None = None
    long_name: str | None = None
    optional: bool = False
    extra: dict = field(default_factory=dict)

    def to_ccpp_attrs(self) -> dict:
        """Return the attribute dict expected by :class:`~xdsl_ccpp.dialects.ccpp.ArgumentOp`."""
        attrs: dict = {"type": self.type}
        if self.standard_name:
            attrs["standard_name"] = self.standard_name
        if self.long_name:
            attrs["long_name"] = self.long_name
        if self.kind:
            attrs["kind"] = self.kind
        if self.intent:
            attrs["intent"] = self.intent
        if self.units:
            attrs["units"] = self.units
        attrs["dimensions"] = "(" + ", ".join(self.dimensions) + ")"
        if self.optional:
            attrs["optional"] = True
        attrs.update(self.extra)
        return attrs


# ---------------------------------------------------------------------------
# Internal descriptor classes
# ---------------------------------------------------------------------------


class SchemeDescriptor:
    """Descriptor produced by :func:`ccpp_scheme`."""

    def __init__(self, name: str, entry_points: dict[str, list[Arg]],
                 *, language: "str | None" = None):
        self.name = name
        # Maps entry-point attribute name (e.g. "run") → list of Arg objects.
        self.entry_points = entry_points
        # Implementation language: None / "fortran" (default) or "c++".
        self.language = language


class TableDescriptor:
    """Descriptor produced by :func:`ccpp_ddt`, :func:`ccpp_module`, or :func:`ccpp_host`."""

    def __init__(
        self,
        name: str,
        type_str: str,
        arg_tables: "dict[str, list[Arg]]",
        *,
        array_layout: "str | None" = None,
    ):
        self.name = name
        self.type_str = type_str  # "ddt", "module", or "host"
        # Maps arg-table name → list of Arg objects.
        self.arg_tables = arg_tables
        # Array memory layout: "row_major" | None (= column_major, the default).
        self.array_layout = array_layout


class SuiteDescriptor:
    """Descriptor produced by :func:`ccpp_suite`."""

    def __init__(
        self,
        name: str,
        version: str,
        groups: "dict[str, list[tuple[SchemeDescriptor, dict[str, str]] | SubcycleDescriptor]]",
    ):
        self.name = name
        self.version = version
        # Maps group name → list of (SchemeDescriptor, overrides) pairs or
        # SubcycleDescriptor objects.  overrides is a {arg_name: literal_str}
        # dict, empty when there are no overrides.
        self.groups = groups


class SubcycleDescriptor:
    """A block of schemes that execute inside a loop.

    Produced by :func:`forLoop`.  Corresponds to
    ``<subcycle loop="N">`` in a suite XML file.
    """

    def __init__(self, count: "int | str", schemes: "list[SchemeDescriptor]"):
        # Integer → literal loop count baked in at IR-generation time.
        # String → CCPP standard name resolved at runtime (is_literal=False).
        self.count = count
        self.schemes = schemes


def forLoop(
    count: "int | str",
    schemes: "list[SchemeDescriptor]",
) -> SubcycleDescriptor:
    """Declare a loop block: *schemes* repeated *count* times.

    Corresponds to ``<subcycle loop="N">`` in a suite XML file.  May appear
    anywhere in a group's scheme list.

    Use this function when the loop count is a **CCPP standard name** resolved
    at runtime by the host model.  For a fixed integer count known at
    IR-generation time, a plain Python ``for`` loop inside ``def run():`` is
    simpler and equally correct::

        # Literal count — use a for loop in def run():
        repeats = ccpp_param("repeats", default=3)

        @ccpp_suite("my_suite", version="1.0")
        class my_suite:
            physics = [scheme_a, scheme_b, teardown]
            def run():
                for i in range(repeats):
                    scheme_a()
                    scheme_b()
                teardown()

        # Runtime CCPP standard name — must use forLoop():
        @ccpp_suite("rrtmgp", version="1.0")
        class rrtmgp:
            physics_after_coupler = [
                rrtmgp_pre,
                forLoop("number_of_diagnostic_subcycles", [
                    rrtmgp_constituents,
                    rrtmgp_sw_gas_optics,
                    rrtmgp_sw_rte,
                ]),
                rrtmgp_post,
            ]

    Args:
        count:   Loop iteration count.  Pass an ``int`` (or a value from
                 :func:`ccpp_param`) for a literal baked in at IR-generation
                 time, or a ``str`` CCPP standard name resolved at runtime.
        schemes: Ordered list of :class:`SchemeDescriptor` objects forming the
                 loop body.
    """
    return SubcycleDescriptor(count=count, schemes=schemes)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def ccpp_scheme(cls) -> SchemeDescriptor:
    """Decorator: declare a CCPP physics scheme.

    The decorated class may define any subset of the following attributes,
    each holding a ``list[Arg]``:

    - ``run``            → ``{scheme}_run``
    - ``init``           → ``{scheme}_init``
    - ``finalize``       → ``{scheme}_finalize``
    - ``timestep_init``  → ``{scheme}_timestep_init``
    - ``timestep_final`` → ``{scheme}_timestep_final``
    - ``register``       → ``{scheme}_register``

    Returns a :class:`SchemeDescriptor` whose ``.name`` is the class name.
    """
    entry_points: dict[str, list[Arg]] = {}
    for ep in _ENTRY_POINTS:
        if hasattr(cls, ep):
            entry_points[ep] = getattr(cls, ep)
    return SchemeDescriptor(cls.__name__, entry_points)


def ccpp_ddt(cls) -> TableDescriptor:
    """Decorator: declare a CCPP derived data type (DDT).

    The class should have a single attribute named after the DDT containing
    a ``list[Arg]`` describing the DDT's fields (no ``intent`` required).

    Example::

        @ccpp_ddt
        class vmr_type:
            vmr_type = [
                Arg("nvmr", standard_name="number_of_chemical_species",
                    type="integer", units="count"),
            ]
    """
    arg_tables: dict[str, list[Arg]] = {}
    for attr_name, val in cls.__dict__.items():
        if not attr_name.startswith("_") and isinstance(val, list):
            arg_tables[attr_name] = val
    return TableDescriptor(cls.__name__, "ddt", arg_tables)


def ccpp_module(cls) -> TableDescriptor:
    """Decorator: declare a CCPP host-model data module.

    Each non-private list attribute on the class becomes one arg table.
    """
    arg_tables: dict[str, list[Arg]] = {}
    for attr_name, val in cls.__dict__.items():
        if not attr_name.startswith("_") and isinstance(val, list):
            arg_tables[attr_name] = val
    return TableDescriptor(cls.__name__, "module", arg_tables)


def ccpp_host(cls) -> TableDescriptor:
    """Decorator: declare a CCPP host-model subroutine entry point.

    Each non-private list attribute on the class becomes one arg table.
    """
    arg_tables: dict[str, list[Arg]] = {}
    for attr_name, val in cls.__dict__.items():
        if not attr_name.startswith("_") and isinstance(val, list):
            arg_tables[attr_name] = val
    return TableDescriptor(cls.__name__, "host", arg_tables)


def _run_groups(
    run_fn,
    groups: dict[str, list[SchemeDescriptor]],
) -> dict[str, list[tuple[SchemeDescriptor, dict[str, str]]]]:
    """Execute *run_fn* in a recording namespace to determine group contents.

    Callable names available inside ``run``:

    - **Group name** (e.g. ``physics()``) — adds all schemes from that group to
      the output, preserving the group name.
    - **Scheme name** (e.g. ``hello_scheme()``) — adds that scheme to its parent
      group (the group whose list it appeared in).  Keyword arguments become
      compile-time literal overrides (e.g. ``hello_scheme(var_a=92)``).
    - **``range(n)``** — works normally for integer counts, giving a natural
      ``for i in range(n): scheme()`` loop syntax.  Passing a string raises a
      clear error directing the user to :func:`forLoop` instead.

    All standard Python control flow (``for``, ``while``, ``if``) works as
    normal because the function body is executed directly.  Module-level
    variables (including those produced by :func:`ccpp_param`) are accessible
    inside ``run`` because the original ``__globals__`` dict is preserved.
    """
    # Map each scheme name to its parent group name and descriptor.
    # SubcycleDescriptor items in group lists are skipped — forLoop() in a
    # group list has no effect when def run(): is also present.
    scheme_to_group: dict[str, str] = {}
    all_schemes: dict[str, SchemeDescriptor] = {}
    for group_name, schemes in groups.items():
        for sd in schemes:
            if isinstance(sd, SubcycleDescriptor):
                continue
            scheme_to_group[sd.name] = group_name
            all_schemes[sd.name] = sd

    default_group = next(iter(groups)) if groups else "physics"

    # Recording state: ordered dict of group_name → (descriptor, overrides) list.
    output: dict[str, list[tuple[SchemeDescriptor, dict[str, str]]]] = {}

    def _add(group_name: str, sd: SchemeDescriptor, overrides: dict[str, str]) -> None:
        if group_name not in output:
            output[group_name] = []
        output[group_name].append((sd, overrides))

    # Build the recording namespace.
    namespace: dict = {}

    for group_name, schemes in groups.items():

        def _make_group_caller(gname, gschemes):
            def _caller():
                for sd in gschemes:
                    _add(gname, sd, {})

            return _caller

        namespace[group_name] = _make_group_caller(group_name, schemes)

    for scheme_name, sd in all_schemes.items():

        def _make_scheme_caller(sname, ssd):
            def _caller(**kwargs):
                overrides = {k: str(v) for k, v in kwargs.items()}
                _add(scheme_to_group.get(sname, default_group), ssd, overrides)

            return _caller

        namespace[scheme_name] = _make_scheme_caller(scheme_name, sd)

    # Override range() to catch the common mistake of passing a CCPP standard
    # name string where an integer is required.
    def _checked_range(*args):
        for a in args:
            if isinstance(a, str):
                raise TypeError(
                    f"range() does not accept a CCPP standard name '{a}'. "
                    f"Use forLoop('{a}', [...]) in the group list instead of "
                    f"a for loop in def run():"
                )
        return range(*args)

    namespace["range"] = _checked_range

    # Execute run_fn with recording callables overlaid on its original globals.
    _types.FunctionType(run_fn.__code__, {**run_fn.__globals__, **namespace})()

    return output


def ccpp_suite(name: str, version: str = "1.0"):
    """Decorator factory: declare a CCPP suite.

    Each non-private class attribute that is a ``list[SchemeDescriptor]``
    becomes a named group, in definition order.

    An optional ``run`` method can be defined on the class to explicitly
    control which schemes are included and in what order.  Inside ``run``:

    - Calling a **group name** (e.g. ``physics()``) adds all schemes from
      that group to the output, preserving the group name.
    - Calling a **scheme name directly** (e.g. ``hello_scheme()``) adds just
      that scheme to its parent group.

    When ``run`` is absent the default behaviour (include every scheme from
    every group) is preserved.

    Examples::

        # Default — include all schemes
        @ccpp_suite("hello_world_suite", version="1.0")
        class hello_world:
            physics = [hello_scheme, temp_adjust]

        # Equivalent explicit run
        @ccpp_suite("hello_world_suite", version="1.0")
        class hello_world:
            physics = [hello_scheme, temp_adjust]
            def run():
                physics()

        # Select a subset / custom order
        @ccpp_suite("hello_world_suite", version="1.0")
        class hello_world:
            physics = [hello_scheme, temp_adjust]
            def run():
                hello_scheme()   # temp_adjust is skipped

        # Repeat a scheme N times using a loop.
        # N can be a module-level constant or a ccpp_param() value.
        top = ccpp_param("top", default=10)   # override: python3 suite.py top=53

        @ccpp_suite("loop_suite", version="1.0")
        class loop_suite:
            physics = [hello_scheme]
            def run():
                for i in range(0, top):
                    hello_scheme()
    """

    def decorator(cls) -> SuiteDescriptor:
        raw_groups: dict[str, list[SchemeDescriptor]] = {}
        for attr_name, val in cls.__dict__.items():
            if not attr_name.startswith("_") and isinstance(val, list):
                raw_groups[attr_name] = val
        run_fn = cls.__dict__.get("run")
        if run_fn is not None:
            groups = _run_groups(run_fn, raw_groups)
        else:
            groups = {
                k: [item if isinstance(item, SubcycleDescriptor) else (item, {}) for item in v]
                for k, v in raw_groups.items()
            }
        return SuiteDescriptor(name, version, groups)

    return decorator


# ---------------------------------------------------------------------------
# .meta file loaders
# ---------------------------------------------------------------------------


def _parse_dims(dim_str: str) -> tuple[str, ...]:
    """Convert a ``.meta`` dimension string to a tuple of standard names.

    Examples::

        _parse_dims("(horizontal_loop_extent, vertical_layer_dimension)")
            → ("horizontal_loop_extent", "vertical_layer_dimension")
        _parse_dims("()")  → ()
    """
    s = dim_str.strip().strip("()")
    if not s.strip():
        return ()
    return tuple(d.strip() for d in s.split(",") if d.strip())


def _ccpp_arg_to_arg(ccpp_arg) -> "Arg":
    """Convert a parsed ``CCPPArgument`` object to an :class:`Arg` dataclass.

    Attributes explicitly modeled in :class:`Arg` are mapped directly.
    Everything else (e.g. ``memory_space``, ``state_variable``, ``active``)
    goes into :attr:`Arg.extra` and is forwarded verbatim to the IR.
    """
    attrs = ccpp_arg.getAttrs()
    modeled = {"standard_name", "type", "intent", "units", "dimensions",
               "kind", "long_name", "optional"}
    extra = {k: v for k, v in attrs.items() if k not in modeled}
    return Arg(
        name=ccpp_arg.name,
        standard_name=attrs.get("standard_name", ""),
        type=attrs.get("type", ""),
        intent=attrs.get("intent", ""),
        units=attrs.get("units", ""),
        dimensions=_parse_dims(attrs.get("dimensions", "()")),
        kind=attrs.get("kind"),
        long_name=attrs.get("long_name"),
        optional=str(attrs.get("optional", "")).strip().lower() in ("true", ".true."),
        extra=extra,
    )


def ccpp_scheme_from_meta(filename: str, name: str | None = None) -> "SchemeDescriptor":
    """Load a CCPP scheme descriptor from a ``.meta`` file.

    Parses *filename* and returns a :class:`SchemeDescriptor` equivalent to
    one produced by the ``@ccpp_scheme`` decorator.  The scheme name and all
    argument metadata (standard names, types, intents, dimensions, and
    pass-through attributes such as ``memory_space``) are taken directly from
    the file — no duplication in Python is required.

    This is the primary bridge between the existing ``.meta`` file ecosystem
    and the Python suite API.  Use it when you want to express suite
    orchestration logic in Python while keeping ``.meta`` files as the source
    of truth for scheme argument metadata::

        kessler        = ccpp_scheme_from_meta("examples/kessler/scheme/kessler.meta")
        kessler_update = ccpp_scheme_from_meta("examples/kessler/scheme/kessler_update.meta")

        @ccpp_suite("kessler_suite", version="1.0")
        class kessler_suite:
            def run():
                kessler()
                kessler_update()

        if __name__ == "__main__":
            emit_ir(kessler_suite)

    When a ``.meta`` file contains multiple scheme definitions (e.g.
    ``physics_tendency_updaters.meta`` defines ``apply_heating_rate``,
    ``apply_constituent_tendencies``, etc.) pass the *name* keyword to select
    the desired one::

        apply_heating_rate = ccpp_scheme_from_meta(
            "schemes/utilities/physics_tendency_updaters.meta",
            name="apply_heating_rate",
        )

    Args:
        filename: Path to a scheme ``.meta`` file.
        name:     If given, return the scheme with this name instead of the
                  first scheme block in the file.

    Returns:
        A :class:`SchemeDescriptor` ready for use in ``@ccpp_suite`` and
        :func:`emit_ir`.
    """
    from xdsl_ccpp.frontend.ccpp_xml import parse_meta_file  # lazy to avoid circular import

    meta_list = parse_meta_file(filename, is_scheme=True)
    if name is not None:
        meta = next(
            (m for m in meta_list
             if str(m.table_properties.getAttr("type")) == "scheme"
             and str(m.table_properties.getAttr("name")) == name),
            None,
        )
        if meta is None:
            raise ValueError(f"No scheme named {name!r} in {filename!r}")
    else:
        # A .meta file may contain multiple [ccpp-table-properties] blocks (e.g. a
        # DDT definition followed by the scheme that uses it).  Find the first
        # block whose type is "scheme"; fall back to the first block if none match.
        meta = next(
            (m for m in meta_list
             if str(m.table_properties.getAttr("type")) == "scheme"),
            meta_list[0],
        )
    scheme_name = meta.table_properties.getAttr("name")
    prefix = scheme_name + "_"

    entry_points: dict[str, list[Arg]] = {}
    for table in meta.arg_tables:
        table_name = table.getAttr("name")
        ep = table_name[len(prefix):] if table_name.startswith(prefix) else table_name
        if ep in _ENTRY_POINTS:
            entry_points[ep] = [_ccpp_arg_to_arg(a) for a in table.getFunctionArguments()]

    language = (
        meta.table_properties.getAttr("language")
        if meta.table_properties.hasAttr("language")
        else None
    )
    return SchemeDescriptor(scheme_name, entry_points, language=language)


def ccpp_host_from_meta(filename: str) -> "list[TableDescriptor]":
    """Load CCPP host metadata from a ``.meta`` file.

    Parses *filename* and returns one :class:`TableDescriptor` per
    ``[ccpp-table-properties]`` block.  A single file may contain multiple
    blocks (e.g. a DDT definition followed by a module), so the return value
    is always a list.

    Pass the results in the *additional* argument of :func:`emit_ir` or
    :func:`build_ir`::

        host_mod = ccpp_host_from_meta("kessler_host_mod.meta")
        host_sub = ccpp_host_from_meta("kessler_host_sub.meta")

        if __name__ == "__main__":
            emit_ir(kessler_suite, additional=[*host_mod, *host_sub])

    Args:
        filename: Path to a host ``.meta`` file.

    Returns:
        A list of :class:`TableDescriptor` objects (one per table-properties block).
    """
    from xdsl_ccpp.frontend.ccpp_xml import parse_meta_file

    meta_list = parse_meta_file(filename, is_scheme=False)
    result = []
    for meta in meta_list:
        type_str = str(meta.table_properties.getAttr("type"))
        arg_tables: dict[str, list[Arg]] = {
            table.getAttr("name"): [_ccpp_arg_to_arg(a) for a in table.getFunctionArguments()]
            for table in meta.arg_tables
        }
        array_layout = (
            meta.table_properties.getAttr("array_layout")
            if meta.table_properties.hasAttr("array_layout")
            else None
        )
        result.append(
            TableDescriptor(meta.table_properties.getAttr("name"), type_str, arg_tables,
                            array_layout=array_layout)
        )
    return result


def ccpp_ddt_from_meta(filename: str) -> "TableDescriptor":
    """Load a CCPP DDT definition from a ``.meta`` file.

    Parses *filename* and returns the first DDT-typed
    ``[ccpp-table-properties]`` block as a :class:`TableDescriptor`.  Useful
    when a ``.meta`` file contains both a DDT definition and a scheme
    definition (e.g. ``make_ddt.meta``)::

        vmr_type = ccpp_ddt_from_meta("examples/capgen/scheme/make_ddt.meta")
        make_ddt = ccpp_scheme_from_meta("examples/capgen/scheme/make_ddt.meta")

        @ccpp_suite("ddt_suite", version="1.0")
        class ddt_suite:
            data_prep = [make_ddt, environ_conditions]

        if __name__ == "__main__":
            emit_ir(ddt_suite, additional=[vmr_type])

    Args:
        filename: Path to a ``.meta`` file containing a DDT definition.

    Returns:
        A :class:`TableDescriptor` with ``type_str="ddt"``.
    """
    from xdsl_ccpp.frontend.ccpp_xml import parse_meta_file

    meta_list = parse_meta_file(filename, is_scheme=False)
    meta = next(
        (m for m in meta_list
         if str(m.table_properties.getAttr("type")) == "ddt"),
        meta_list[0],
    )
    type_str = str(meta.table_properties.getAttr("type"))
    arg_tables: dict[str, list[Arg]] = {
        table.getAttr("name"): [_ccpp_arg_to_arg(a) for a in table.getFunctionArguments()]
        for table in meta.arg_tables
    }
    return TableDescriptor(meta.table_properties.getAttr("name"), type_str, arg_tables)


# ---------------------------------------------------------------------------
# IR construction
# ---------------------------------------------------------------------------


def _arg_op(arg: Arg) -> ArgumentOp:
    return ArgumentOp(arg.name, arg.type, arg.to_ccpp_attrs())


def _table_properties_op(
    table_name: str,
    type_str: str,
    arg_tables: "dict[str, list[Arg]]",
    array_layout: "str | None" = None,
    language: "str | None" = None,
) -> TablePropertiesOp:
    table_ops = []
    for entry_name, args in arg_tables.items():
        arg_ops = [_arg_op(a) for a in args]
        table_ops.append(ArgumentTableOp(entry_name, type_str, arg_ops))
    attrs: "dict | None" = None
    if array_layout is not None or (language is not None and language != "fortran"):
        attrs = {}
        if array_layout is not None:
            attrs["array_layout"] = StringAttr(array_layout)
        if language is not None and language != "fortran":
            attrs["language"] = StringAttr(language)
    return TablePropertiesOp(table_name, type_str, table_ops, attributes=attrs)


def _scheme_table_properties(sd: SchemeDescriptor) -> TablePropertiesOp:
    entry_tables = {f"{sd.name}_{ep}": args for ep, args in sd.entry_points.items()}
    return _table_properties_op(sd.name, "scheme", entry_tables, language=sd.language)


def _group_item_to_op(
    item: "tuple[SchemeDescriptor, dict[str, str]] | SubcycleDescriptor",
    seen_schemes: "dict[str, SchemeDescriptor]",
) -> "SchemeOp | SubcycleOp":
    """Convert one group-list item to its MLIR op, registering schemes seen."""
    if isinstance(item, SubcycleDescriptor):
        inner_ops = []
        for sd in item.schemes:
            if isinstance(sd, SubcycleDescriptor):
                raise ValueError(
                    "Nested forLoop() blocks are not supported -- forLoop's "
                    "schemes list must contain only schemes, not another "
                    "forLoop(). Use multiple sibling forLoop() blocks instead."
                )
            inner_ops.append(SchemeOp(sd.name, None))
            seen_schemes.setdefault(sd.name, sd)
        return SubcycleOp(item.count, inner_ops, is_literal=isinstance(item.count, int))
    sd, overrides = item
    seen_schemes.setdefault(sd.name, sd)
    return SchemeOp(sd.name, overrides or None)


def build_ir(
    suites: "SuiteDescriptor | list[SuiteDescriptor]",
    additional: list[TableDescriptor | SchemeDescriptor] | None = None,
) -> ModuleOp:
    """Build a :class:`~xdsl.dialects.builtin.ModuleOp` from one or more suite descriptors.

    Produces the same MLIR as the XML/meta frontend (:mod:`xdsl_ccpp.frontend.ccpp_xml`).

    Args:
        suites:     One :class:`SuiteDescriptor` or a list of them.  When a
                    list is given all suites are included in the same
                    ``ModuleOp``, matching the behaviour of the XML frontend
                    when ``--suites`` receives a comma-separated list.
        additional: Extra DDT/module/host (or scheme) descriptors not already
                    referenced inside any suite's groups.

    Returns:
        A top-level ``ModuleOp`` ready to be passed to ``ccpp_opt``.
    """
    if isinstance(suites, SuiteDescriptor):
        suites = [suites]

    ir_ops = []
    seen_schemes: dict[str, SchemeDescriptor] = {}

    # Build one SuiteOp per suite, collecting unique SchemeDescriptors across all.
    for suite in suites:
        group_ops = []
        for group_name, scheme_list in suite.groups.items():
            ops = [_group_item_to_op(item, seen_schemes) for item in scheme_list]
            group_ops.append(GroupOp(group_name, ops))
        ir_ops.append(SuiteOp(suite.name, group_ops, suite.version))

    # One TablePropertiesOp per unique scheme across all suites.
    for sd in seen_schemes.values():
        ir_ops.append(_scheme_table_properties(sd))

    # Additional descriptors (DDTs, host modules, hosts, extra schemes).
    for desc in additional or []:
        if isinstance(desc, SchemeDescriptor):
            ir_ops.append(_scheme_table_properties(desc))
        else:
            ir_ops.append(
                _table_properties_op(desc.name, desc.type_str, desc.arg_tables,
                                     array_layout=desc.array_layout)
            )

    return ModuleOp(ir_ops)


def emit_ir(
    suites: "SuiteDescriptor | list[SuiteDescriptor]",
    additional: list[TableDescriptor | SchemeDescriptor] | None = None,
) -> None:
    """Build IR from one or more suites and print it to stdout.

    Intended to be called inside ``if __name__ == "__main__":`` in user scripts.
    The output is identical to the XML/meta frontend and can be piped directly
    into ``ccpp_opt``.

    Pass a list of :class:`SuiteDescriptor` objects to include multiple suites
    in one IR output, matching ``ccpp_xdsl --suites a.xml,b.xml ...``.
    """
    print(build_ir(suites, additional))
