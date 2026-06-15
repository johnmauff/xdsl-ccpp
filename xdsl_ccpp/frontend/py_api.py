"""Python API frontend for the CCPP compiler.

Users write a Python file that imports this module, declares arguments, schemes,
DDTs, and suites using decorators, then calls :func:`emit_ir` to produce the
same MLIR as the XML/meta frontend.

Minimal example::

    from xdsl_ccpp.frontend.py_api import Arg, ccpp_scheme, ccpp_suite, emit_ir

    errmsg = Arg("errmsg", standard_name=CCPP_ERROR_MESSAGE,
                 type="character", kind="len=512", intent="out", units="none")
    errflg = Arg("errflg", standard_name=CCPP_ERROR_CODE,
                 type="integer", intent="out", units="1")

    @ccpp_scheme
    class my_scheme:
        run      = [Arg("ncol", ...), errmsg, errflg]
        init     = [errmsg, errflg]
        finalize = [errmsg, errflg]

    @ccpp_suite("my_suite", version="1.0")
    class my_suite:
        physics = [my_scheme]

    if __name__ == "__main__":
        emit_ir(my_suite)

The output can be piped directly into ``ccpp_opt``::

    python3 my_suite.py | python3 -m xdsl_ccpp.tools.ccpp_opt -p ... -t ftn
"""

from __future__ import annotations

import sys
import types as _types
from dataclasses import dataclass, field

from xdsl.dialects.builtin import ModuleOp

from xdsl_ccpp.util.ccpp_conventions import CCPP_ERROR_MESSAGE, CCPP_ERROR_CODE
from xdsl_ccpp.dialects.ccpp import (
    ArgumentOp,
    ArgumentTableOp,
    GroupOp,
    SchemeOp,
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
        return attrs


# ---------------------------------------------------------------------------
# Internal descriptor classes
# ---------------------------------------------------------------------------


class SchemeDescriptor:
    """Descriptor produced by :func:`ccpp_scheme`."""

    def __init__(self, name: str, entry_points: dict[str, list[Arg]]):
        self.name = name
        # Maps entry-point attribute name (e.g. "run") → list of Arg objects.
        self.entry_points = entry_points


class TableDescriptor:
    """Descriptor produced by :func:`ccpp_ddt`, :func:`ccpp_module`, or :func:`ccpp_host`."""

    def __init__(self, name: str, type_str: str, arg_tables: dict[str, list[Arg]]):
        self.name = name
        self.type_str = type_str  # "ddt", "module", or "host"
        # Maps arg-table name → list of Arg objects.
        self.arg_tables = arg_tables


class SuiteDescriptor:
    """Descriptor produced by :func:`ccpp_suite`."""

    def __init__(
        self,
        name: str,
        version: str,
        groups: dict[str, list[tuple[SchemeDescriptor, dict[str, str]]]],
    ):
        self.name = name
        self.version = version
        # Maps group name → list of (SchemeDescriptor, overrides) pairs.
        # overrides is a {arg_name: literal_str} dict, empty when no overrides.
        self.groups = groups


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

    All standard Python control flow (``for``, ``while``, ``if``) works as
    normal because the function body is executed directly.  Module-level
    variables (including those produced by :func:`ccpp_param`) are accessible
    inside ``run`` because the original ``__globals__`` dict is preserved.
    """
    # Map each scheme name to its parent group name and descriptor.
    scheme_to_group: dict[str, str] = {}
    all_schemes: dict[str, SchemeDescriptor] = {}
    for group_name, schemes in groups.items():
        for sd in schemes:
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
            groups = {k: [(sd, {}) for sd in v] for k, v in raw_groups.items()}
        return SuiteDescriptor(name, version, groups)

    return decorator


# ---------------------------------------------------------------------------
# IR construction
# ---------------------------------------------------------------------------


def _arg_op(arg: Arg) -> ArgumentOp:
    return ArgumentOp(arg.name, arg.type, arg.to_ccpp_attrs())


def _table_properties_op(
    table_name: str,
    type_str: str,
    arg_tables: dict[str, list[Arg]],
) -> TablePropertiesOp:
    table_ops = []
    for entry_name, args in arg_tables.items():
        arg_ops = [_arg_op(a) for a in args]
        table_ops.append(ArgumentTableOp(entry_name, type_str, arg_ops))
    return TablePropertiesOp(table_name, type_str, table_ops)


def _scheme_table_properties(sd: SchemeDescriptor) -> TablePropertiesOp:
    entry_tables = {f"{sd.name}_{ep}": args for ep, args in sd.entry_points.items()}
    return _table_properties_op(sd.name, "scheme", entry_tables)


def build_ir(
    suite: SuiteDescriptor,
    additional: list[TableDescriptor | SchemeDescriptor] | None = None,
) -> ModuleOp:
    """Build a :class:`~xdsl.dialects.builtin.ModuleOp` from a suite descriptor.

    Produces the same MLIR as the XML/meta frontend (:mod:`xdsl_ccpp.frontend.ccpp_xml`).

    Args:
        suite:      The suite descriptor returned by ``@ccpp_suite``.
        additional: Extra DDT/module/host (or scheme) descriptors not already
                    referenced inside the suite's groups.

    Returns:
        A top-level ``ModuleOp`` ready to be passed to ``ccpp_opt``.
    """
    ir_ops = []

    # Build the SuiteOp, collecting unique SchemeDescriptors along the way.
    group_ops = []
    seen_schemes: dict[str, SchemeDescriptor] = {}
    for group_name, scheme_list in suite.groups.items():
        scheme_ops = [
            SchemeOp(sd.name, overrides or None) for sd, overrides in scheme_list
        ]
        group_ops.append(GroupOp(group_name, scheme_ops))
        for sd, _ in scheme_list:
            seen_schemes.setdefault(sd.name, sd)
    ir_ops.append(SuiteOp(suite.name, group_ops, suite.version))

    # One TablePropertiesOp per unique scheme.
    for sd in seen_schemes.values():
        ir_ops.append(_scheme_table_properties(sd))

    # Additional descriptors (DDTs, host modules, hosts, extra schemes).
    for desc in additional or []:
        if isinstance(desc, SchemeDescriptor):
            ir_ops.append(_scheme_table_properties(desc))
        else:
            ir_ops.append(
                _table_properties_op(desc.name, desc.type_str, desc.arg_tables)
            )

    return ModuleOp(ir_ops)


def emit_ir(
    suite: SuiteDescriptor,
    additional: list[TableDescriptor | SchemeDescriptor] | None = None,
) -> None:
    """Build IR from *suite* and print it to stdout.

    Intended to be called inside ``if __name__ == "__main__":`` in user scripts.
    The output is identical to the XML/meta frontend and can be piped directly
    into ``ccpp_opt``.
    """
    print(build_ir(suite, additional))
