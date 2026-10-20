"""Python API frontend for the CCPP compiler.

Users write a Python file that imports this module, declares arguments, schemes,
DDTs, and suites using decorators, then calls :func:`export_suite` to produce the
same MLIR as the XML/meta frontend.

There are two ways to define scheme argument metadata:

**Inline** — define arguments directly in Python (no ``.meta`` file needed)::

    from xdsl_ccpp.frontend.py_api import Arg, ccpp_scheme, ccpp_suite, export_suite

    @ccpp_scheme
    class my_scheme:
        run = [Arg("ncol", standard_name="horizontal_dimension",
                   type="integer", units="count", intent="in"), ...]

    @ccpp_suite("my_suite", version="1.0")
    class my_suite:
        physics = [my_scheme]

    if __name__ == "__main__":
        export_suite(my_suite)

**From .meta files** — load existing ``.meta`` files and write only the suite
orchestration in Python (backwards-compatible path)::

    from xdsl_ccpp.frontend.py_api import ccpp_scheme_from_meta, ccpp_suite, export_suite

    kessler        = ccpp_scheme_from_meta("examples/kessler/scheme/kessler.meta")
    kessler_update = ccpp_scheme_from_meta("examples/kessler/scheme/kessler_update.meta")

    @ccpp_suite("kessler_suite", version="1.0")
    class kessler_suite:
        def run():
            kessler()
            kessler_update()

    if __name__ == "__main__":
        export_suite(kessler_suite)

**Composing schemes with ordinary Python functions** — a scheme descriptor
may be called from any helper function (e.g. a physics package or a host
adapter) that is itself called, directly or indirectly, from ``run()`` or a
group function; the call records exactly as if made inline.  Groups may be
written as functions, ``with forLoop("std_name"):`` blocks may appear in any
of these bodies, and plain keyword defaults give swappable components
("slots") -- all resolved at IR-generation time, so generated Fortran is
identical to the equivalent flat suite (see ``composite_scheme_plan.md``).
Schemes may be referenced by name only, ``ccpp_scheme_ref("name")``, leaving
file paths to the command line (``--scheme-files=``/``--host-files=``) or the
driver, as for an XML suite::

    def shortwave(*, diagnostics, overlap=sw_mcica):   # overlap is a slot
        overlap()
        with forLoop("number_of_diagnostic_subcycles"):
            sw_gas_optics()
            sw_rte()
            diagnostics()                              # host-supplied hook

    @ccpp_suite("rrtmgp", version="1.0")
    class rrtmgp:
        def physics_after_coupler():
            shortwave(diagnostics=rrtmgp_sw_diagnostics)

The output can be piped directly into ``ccpp_opt``::

    python3 my_suite.py | python3 -m xdsl_ccpp.tools.ccpp_opt -p ... -t ftn
"""

from __future__ import annotations

import functools
import inspect
import sys
import types as _types
from contextlib import contextmanager
from dataclasses import dataclass, field

from xdsl.dialects.builtin import ArrayAttr, ModuleOp, StringAttr

from xdsl_ccpp.dialects.ccpp import (
    ArgumentOp,
    ArgumentTableOp,
    CompositeOp,
    GroupOp,
    SchemeOp,
    SubcycleOp,
    SuiteOp,
    TablePropertiesOp,
)
from xdsl_ccpp.util.ccpp_conventions import (
    set_legacy_mode,
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
                 *, language: str | None = None,
                 kind_specs: list[tuple[str, str, str]] | None = None,
                 dependencies: list[str] | None = None,
                 dependencies_path: str | None = None,
                 source_path: str | None = None,
                 is_reference: bool = False):
        self.name = name
        # Maps entry-point attribute name (e.g. "run") → list of Arg objects.
        self.entry_points = entry_points
        # True for a name-only reference (ccpp_scheme_ref): no metadata of its
        # own; build_ir resolves it by name from scheme_files, or leaves the
        # metadata to the driver (ccpp_dsl --py --scheme-files ...).
        self.is_reference = is_reference
        # Implementation language: None / "fortran" (default) or "c++".
        self.language = language
        # (kind_name, module, spec) tuples from this table's own kind_spec
        # declaration(s) -- see ccpp_conventions.parse_kind_spec_value.
        self.kind_specs = kind_specs or []
        # Raw dependency filenames / dependencies_path / source_path from this
        # table's own declarations -- see ccpp_xml.py's CCPPTableProperties;
        # not resolved to filesystem paths, no current consumer.
        self.dependencies = dependencies or []
        self.dependencies_path = dependencies_path
        self.source_path = source_path

    def __call__(self, **overrides) -> None:
        """Record this scheme into the group currently being recorded.

        Lets ordinary Python functions compose schemes: a helper (e.g. a
        physics package or host adapter) that calls ``some_scheme()`` and is
        itself called from a suite's ``run()`` records ``some_scheme`` exactly
        as if it had been called directly inside ``run()``.  Keyword
        arguments become compile-time literal overrides, same as the
        by-name callers ``_run_groups`` installs.

        Raises:
            RuntimeError: when called outside a recording (i.e. not, directly
                or indirectly, from a ``@ccpp_suite`` ``run()``).
        """
        if _active_recorder is None:
            raise RuntimeError(
                f"Scheme '{self.name}' was called outside a suite recording. "
                f"Schemes can only be called (directly or through helper "
                f"functions) from a @ccpp_suite class's run() method or "
                f"group functions."
            )
        _active_recorder((self, {k: str(v) for k, v in overrides.items()}))


# The function that records one item into the suite currently being built,
# or None when no recording is in progress.  An item is either a scheme call,
# ``(descriptor, overrides)``, or a completed ``with forLoop(...)`` block, a
# `SubcycleDescriptor`.  Installed (via `_recording`) by `_run_groups`, by
# `_record_group_function`, and by an open ``with forLoop(...)`` block.
_active_recorder = None


@contextmanager
def _recording(recorder):
    """Install *recorder* as the active recorder for the duration of the block,
    restoring the previous one afterwards (also when the block raises)."""
    global _active_recorder
    previous = _active_recorder
    _active_recorder = recorder
    try:
        yield
    finally:
        _active_recorder = previous


class TableDescriptor:
    """Descriptor produced by :func:`ccpp_ddt`, :func:`ccpp_module`, or :func:`ccpp_host`."""

    def __init__(
        self,
        name: str,
        type_str: str,
        arg_tables: dict[str, list[Arg]],
        *,
        array_layout: str | None = None,
        kind_specs: list[tuple[str, str, str]] | None = None,
        dependencies: list[str] | None = None,
        dependencies_path: str | None = None,
        source_path: str | None = None,
    ):
        self.name = name
        self.type_str = type_str  # "ddt", "module", or "host"
        # Maps arg-table name → list of Arg objects.
        self.arg_tables = arg_tables
        # Array memory layout: "row_major" | None (= column_major, the default).
        self.array_layout = array_layout
        # (kind_name, module, spec) tuples from this table's own kind_spec
        # declaration(s) -- see ccpp_conventions.parse_kind_spec_value.
        self.kind_specs = kind_specs or []
        # Raw dependency filenames / dependencies_path / source_path from this
        # table's own declarations -- see ccpp_xml.py's CCPPTableProperties;
        # not resolved to filesystem paths, no current consumer.
        self.dependencies = dependencies or []
        self.dependencies_path = dependencies_path
        self.source_path = source_path


class SuiteDescriptor:
    """Descriptor produced by :func:`ccpp_suite`."""

    def __init__(
        self,
        name: str,
        version: str,
        groups: dict[str, list[tuple[SchemeDescriptor, dict[str, str]] | SubcycleDescriptor]],
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
    ``<subcycle loop="N">`` in a suite XML file.  ``schemes`` may itself
    contain another `SubcycleDescriptor` (a nested ``forLoop()``), to
    arbitrary depth -- corresponding to a nested ``<subcycle>``.

    Also usable as a context manager (``with forLoop("std_name"):``) inside
    a ``run()``/group function or a helper called from one: scheme calls in
    the block body are collected as ``(descriptor, overrides)`` pairs, and on
    exit the whole block is recorded into the enclosing recording as one item.
    """

    def __init__(
        self, count: int | str,
        schemes: list[SchemeDescriptor | tuple[SchemeDescriptor, dict[str, str]]
                      | SubcycleDescriptor],
    ):
        # Integer → literal loop count baked in at IR-generation time.
        # String → CCPP standard name resolved at runtime (is_literal=False).
        self.count = count
        self.schemes = schemes
        self._outer_recorder = None

    def __enter__(self) -> SubcycleDescriptor:
        global _active_recorder
        if _active_recorder is None:
            raise RuntimeError(
                f"'with forLoop({self.count!r}):' was used outside a suite "
                f"recording; it is only valid (directly or through helper "
                f"functions) inside a @ccpp_suite class's run() method or "
                f"group functions."
            )
        if self.schemes:
            raise ValueError(
                f"forLoop({self.count!r}, [...]) was given a scheme list and "
                f"also used as a with-block; use one form or the other."
            )
        self._outer_recorder = _active_recorder
        _active_recorder = self.schemes.append
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        global _active_recorder
        outer, self._outer_recorder = self._outer_recorder, None
        _active_recorder = outer
        if exc_type is None:
            if not self.schemes:
                raise ValueError(
                    f"'with forLoop({self.count!r}):' block recorded no "
                    f"scheme calls."
                )
            outer(self)
        return False


def forLoop(
    count: int | str,
    schemes: list[SchemeDescriptor | SubcycleDescriptor] | None = None,
) -> SubcycleDescriptor:
    """Declare a loop block: *schemes* repeated *count* times.

    Corresponds to ``<subcycle loop="N">`` in a suite XML file.  Two forms:

    - **List form** ``forLoop(count, [scheme, ...])``: may appear anywhere in
      a group's scheme list.  *schemes* may itself contain another
      ``forLoop()`` result, nested to arbitrary depth, corresponding to a
      nested ``<subcycle>``.
    - **Block form** ``with forLoop(count):`` (no *schemes*): usable inside
      ``run()``, a group function, or any helper function called from one.
      Every scheme call in the block body -- including through further
      helpers, keyword overrides included -- forms the loop body; blocks may
      nest.  The block is recorded into the enclosing group as one subcycle::

          def rrtmgp_shortwave():
              with forLoop("number_of_diagnostic_subcycles"):
                  rrtmgp_sw_gas_optics()
                  rrtmgp_sw_rte()

      Inside ``run()`` the block lands in the parent group of the schemes it
      contains; all of them must belong to the same group.

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
                 loop body -- may itself contain a nested :func:`forLoop`
                 result for a nested ``<subcycle>``.  Omit for the block form.
    """
    return SubcycleDescriptor(count=count, schemes=[] if schemes is None else schemes)


class CompositeDescriptor:
    """One call of a ``@ccpp_composite`` function or package entry point: its
    name and the items its body recorded, in order -- ``(descriptor,
    overrides)`` scheme calls, `SubcycleDescriptor` blocks and nested
    `CompositeDescriptor` calls.  ``package`` is set for a package entry
    point; ``hook`` marks the host code an entry point ran through one of its
    hooks.  Lowered to a ``ccpp.composite`` op.
    """

    def __init__(self, name: str, *, package: str | None = None, hook: bool = False):
        self.name = name
        self.package = package
        self.hook = hook
        self.items: list = []


def _hook_parameters(fn) -> set[str]:
    """Names of *fn*'s hook parameters: those that can be passed by keyword
    and have no default."""
    return {p.name for p in inspect.signature(fn).parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                           inspect.Parameter.KEYWORD_ONLY)}


def _hook_call(hook_name: str, target):
    """Wrap the callable bound to hook *hook_name* so that each call records
    what it runs as one hook composite.  A call that records nothing (a host
    that leaves the hook empty) records no composite."""

    @functools.wraps(target)
    def record_hook(*args, **kwargs):
        hook = CompositeDescriptor(hook_name, hook=True)
        with _recording(hook.items.append):
            target(*args, **kwargs)
        if hook.items:
            _active_recorder(hook)

    return record_hook


def _composite_recorder(fn, package: str | None = None):
    """Wrap *fn* so each call records one `CompositeDescriptor`.  For a
    package entry point, callables bound to hook parameters are wrapped with
    `_hook_call` first."""
    hooks = _hook_parameters(fn) if package is not None else set()

    @functools.wraps(fn)
    def record_composite(*args, **kwargs):
        if _active_recorder is None:
            raise RuntimeError(
                f"Composite '{fn.__name__}' was called outside a suite recording. "
                f"Composites can only be called (directly or through helper "
                f"functions) from a @ccpp_suite class's run() method or group "
                f"functions."
            )
        if hooks:
            bound = inspect.signature(fn).bind(*args, **kwargs)
            for name in hooks & bound.arguments.keys():
                if callable(bound.arguments[name]):
                    bound.arguments[name] = _hook_call(name, bound.arguments[name])
            args, kwargs = bound.args, bound.kwargs
        composite = CompositeDescriptor(fn.__name__, package=package)
        with _recording(composite.items.append):
            fn(*args, **kwargs)
        if not composite.items:
            raise ValueError(f"Composite '{fn.__name__}' recorded no scheme calls.")
        _active_recorder(composite)

    return record_composite


def ccpp_composite(fn):
    """Decorator: record calls of *fn* as a composite scheme -- a named block
    of schemes that belongs to no package (see `ccpp_package` for one that
    does).

    Without the decorator, schemes called by a helper function are recorded
    straight into the caller's group (composition is flattened while the
    suite is recorded).  With it, each call of *fn* records one
    ``ccpp.composite`` op named after *fn*, whose body holds the scheme calls,
    ``with forLoop(...)`` blocks and nested composites the call made.  The
    ``flatten-composites`` pass inlines composites again before code
    generation, so generated code is unchanged.

    Slots and hooks remain ordinary Python parameters, resolved while the
    suite is recorded::

        @ccpp_composite
        def rrtmgp_longwave(*, diagnostics, overlap=lw_mcica):
            overlap()
            ...

    Raises:
        RuntimeError: when called outside a suite recording.
        ValueError: when a call records no scheme calls.
    """
    return _composite_recorder(fn)


class PackageDescriptor:
    """A physics package: the exchangeable unit whose entry points share one
    scope (composite_scheme_plan.md §11).  Produced by `ccpp_package`."""

    def __init__(self, name: str):
        self.name = name
        # Entry-point name -> the undecorated function.
        self.entry_points: dict[str, object] = {}

    def entry_point(self, fn):
        """Decorator: make *fn* an entry point of this package.

        Each call records one ``ccpp.composite`` op named after *fn* and
        tagged with the package.  *fn*'s parameters follow the slot/hook
        convention: a parameter with a default is a SLOT (a swappable science
        component; whatever is bound to it is package code), one without a
        default is a HOOK (host code the caller must supply).  Each call of a
        callable bound to a hook records a nested ``ccpp.composite`` marked
        ``hook``, so later passes can tell host code from package code.
        Non-callable hook values (e.g. a loop count's standard name) are
        passed through unchanged.

        Raises:
            ValueError: when the package already has an entry point named
                like *fn*.
        """
        if fn.__name__ in self.entry_points:
            raise ValueError(
                f"Package '{self.name}' already has an entry point named "
                f"'{fn.__name__}'.")
        self.entry_points[fn.__name__] = fn
        return _composite_recorder(fn, package=self.name)


def ccpp_package(name: str) -> PackageDescriptor:
    """Declare a physics package; decorate its entry points with
    ``@<package>.entry_point``::

        rrtmgp = ccpp_package("rrtmgp")

        @rrtmgp.entry_point
        def rrtmgp_longwave(*, diagnostics, overlap=lw_mcica):
            overlap()
            ...
            diagnostics()
    """
    return PackageDescriptor(name)


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


def ccpp_scheme_ref(name: str) -> SchemeDescriptor:
    """Reference a scheme by name only, without loading its metadata.

    The Python counterpart of an XML ``<scheme>name</scheme>`` entry: a suite
    or package written with references contains no file paths.  The
    metadata is supplied where it is for an XML suite -- by whoever runs the
    generator: ``build_ir``/``export_suite``'s *scheme_files* (on a script's
    command line, ``--scheme-files=a.meta,b.F90``), or ``ccpp_dsl --py ...
    --scheme-files ...``, which merges ``.meta`` metadata itself::

        hello_scheme = ccpp_scheme_ref("hello_scheme")
    """
    return SchemeDescriptor(name, {}, is_reference=True)


def _table_descriptor_from_class(cls, table_type: str) -> TableDescriptor:
    """Shared body for ccpp_ddt/ccpp_module/ccpp_host: every non-private
    list attribute on the decorated class becomes one arg table.

    Extracted after confirming
    the three decorators below were byte-identical apart from the literal
    table-type string passed to TableDescriptor.
    """
    arg_tables: dict[str, list[Arg]] = {}
    for attr_name, val in cls.__dict__.items():
        if not attr_name.startswith("_") and isinstance(val, list):
            arg_tables[attr_name] = val
    return TableDescriptor(cls.__name__, table_type, arg_tables)


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
    return _table_descriptor_from_class(cls, "ddt")


def ccpp_module(cls) -> TableDescriptor:
    """Decorator: declare a CCPP host-model data module.

    Each non-private list attribute on the class becomes one arg table.
    """
    return _table_descriptor_from_class(cls, "module")


def ccpp_host(cls) -> TableDescriptor:
    """Decorator: declare a CCPP host-model subroutine entry point.

    Each non-private list attribute on the class becomes one arg table.
    """
    return _table_descriptor_from_class(cls, "host")


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
                # Through the active recorder (not _add directly) so a call
                # inside a ``with forLoop(...)`` block lands in that block.
                _active_recorder((ssd, {k: str(v) for k, v in kwargs.items()}))

            return _caller

        namespace[scheme_name] = _make_scheme_caller(scheme_name, sd)

    # Override range() to catch the common mistake of passing a CCPP standard
    # name string where an integer is required.
    def _checked_range(*args):
        for a in args:
            if isinstance(a, str):
                raise TypeError(
                    f"range() does not accept a CCPP standard name '{a}'. "
                    f"Use 'with forLoop(\"{a}\"):' (or forLoop('{a}', [...]) "
                    f"in the group list) instead of a for loop in def run():"
                )
        return range(*args)

    namespace["range"] = _checked_range

    # Every scheme call -- by-name callers above, or SchemeDescriptor.__call__
    # for schemes reached through helper functions (whose globals are their
    # own module's, not the overlay below) -- routes here and goes to its
    # parent group.  A completed ``with forLoop(...)`` block or composite call
    # goes to the parent group shared by every scheme inside it.
    def _record_item(item) -> None:
        if isinstance(item, (SubcycleDescriptor, CompositeDescriptor)):
            targets = {scheme_to_group.get(sd.name, default_group)
                       for sd in _block_schemes(item)}
            if len(targets) > 1:
                what = (f"'with forLoop({item.count!r}):'"
                        if isinstance(item, SubcycleDescriptor)
                        else f"composite '{item.name}'")
                raise ValueError(
                    f"{what} in run() contains schemes from several groups "
                    f"{sorted(targets)}; it must stay within one group."
                )
            output.setdefault(targets.pop(), []).append(item)
        else:
            sd, overrides = item
            _add(scheme_to_group.get(sd.name, default_group), sd, overrides)

    # Execute run_fn with recording callables overlaid on its original
    # globals.  Its closure is passed through so run() may also refer to
    # locals of an enclosing function (those resolve via the closure, not the
    # overlay, and record through SchemeDescriptor.__call__).
    with _recording(_record_item):
        _types.FunctionType(run_fn.__code__, {**run_fn.__globals__, **namespace},
                            run_fn.__name__, run_fn.__defaults__,
                            run_fn.__closure__)()

    return output


def _block_schemes(block: SubcycleDescriptor | CompositeDescriptor):
    """Yield every SchemeDescriptor inside a loop block or composite call, at
    any nesting depth."""
    items = block.schemes if isinstance(block, SubcycleDescriptor) else block.items
    for item in items:
        if isinstance(item, (SubcycleDescriptor, CompositeDescriptor)):
            yield from _block_schemes(item)
        elif isinstance(item, tuple):
            yield item[0]
        else:
            yield item


def _record_group_function(group_fn) -> list:
    """Execute a group function, returning the items it recorded, in order.

    Every scheme call made by *group_fn* -- directly or through helper
    functions -- records into this one group, regardless of any group list
    the scheme may also appear in; ``with forLoop(...)`` blocks record as
    `SubcycleDescriptor` items.
    """
    items: list = []
    with _recording(items.append):
        group_fn()
    return items


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

    **Group functions**: any other non-private function defined on the class
    becomes a group named after the function.  Its body is executed at
    IR-generation time, and every scheme it calls -- directly or through
    ordinary helper functions (physics packages, host adapters) -- is
    recorded into that group, in call order.  Group functions and list
    groups may be mixed; groups keep class-definition order.  A class with
    group functions may not also define ``run``.

    Examples::

        # Group functions composing schemes through helper functions
        def my_package():
            hello_scheme()
            temp_adjust()

        @ccpp_suite("hello_world_suite", version="1.0")
        class hello_world:
            def physics():
                my_package()

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
        group_fns: dict = {}
        for attr_name, val in cls.__dict__.items():
            if attr_name.startswith("_"):
                continue
            if isinstance(val, list):
                raw_groups[attr_name] = val
            elif attr_name != "run" and inspect.isfunction(val):
                group_fns[attr_name] = val
        run_fn = cls.__dict__.get("run")
        if run_fn is not None and group_fns:
            raise ValueError(
                f"Suite '{name}' defines both run() and group function(s) "
                f"{sorted(group_fns)}; use one or the other."
            )
        if run_fn is not None:
            groups = _run_groups(run_fn, raw_groups)
        else:
            groups = {}
            for attr_name in cls.__dict__:
                if attr_name in raw_groups:
                    groups[attr_name] = [
                        item if isinstance(item, SubcycleDescriptor) else (item, {})
                        for item in raw_groups[attr_name]
                    ]
                elif attr_name in group_fns:
                    groups[attr_name] = _record_group_function(group_fns[attr_name])
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


def _ccpp_arg_to_arg(ccpp_arg) -> Arg:
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


def _dependencies_kwargs(table_properties) -> dict:
    """Return the dependencies/dependencies_path/source_path constructor
    kwargs shared by SchemeDescriptor and TableDescriptor, read off a parsed
    CCPPTableProperties -- one place for the three from_meta loaders below to
    stay in sync rather than repeating the same hasAttr ternaries three times.
    """
    return dict(
        dependencies=table_properties.dependencies,
        dependencies_path=(
            table_properties.getAttr("dependencies_path")
            if table_properties.hasAttr("dependencies_path") else None
        ),
        source_path=(
            table_properties.getAttr("source_path")
            if table_properties.hasAttr("source_path") else None
        ),
    )


def ccpp_scheme_from_meta(filename: str, name: str | None = None) -> SchemeDescriptor:
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
            export_suite(kessler_suite)

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
        :func:`export_suite`.
    """
    from xdsl_ccpp.frontend.ccpp_xml import (
        parse_meta_file,  # lazy to avoid circular import
    )

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
    return SchemeDescriptor(
        scheme_name, entry_points, language=language,
        kind_specs=meta.table_properties.kind_specs,
        **_dependencies_kwargs(meta.table_properties),
    )


def ccpp_scheme_from_source(
    filename: str, name: str | None = None, root_dir: str | None = None,
) -> SchemeDescriptor:
    """Load a CCPP scheme descriptor from ``!$ccpp``-tagged Fortran source.

    The ``.meta``-free counterpart of :func:`ccpp_scheme_from_meta`: argument
    names, types, kinds, intents and ranks come from the Fortran declarations,
    and ``standard_name``/``units``/``long_name``/``dim_names``/etc. from
    ``!$ccpp [name] key = value`` comment tags beside them -- the convention
    of ``examples/advection_nometa`` (see that directory's README)::

        hello_scheme = ccpp_scheme_from_source("examples/helloworld_composite/hello_scheme.F90")

    Uses the same extractor as the ``ccpp_generate_meta`` tool, then the same
    loading path as :func:`ccpp_scheme_from_meta`, so a fully tagged source
    yields the same descriptor as an equivalent hand-written ``.meta``.

    Args:
        filename: Path to a tagged scheme ``.F90`` file.
        name:     As for :func:`ccpp_scheme_from_meta`.
        root_dir: When given, derive the scheme's ``dependencies`` from its
                  ``USE`` statements, resolved within this directory (see
                  ``ccpp_generate_meta``'s ``--root-dir``).  Omitted: no
                  ``dependencies`` are recorded.

    Raises:
        ValueError: if metadata could not be extracted from *filename*.
    """
    with _meta_from_source(filename, root_dir) as meta_path:
        return ccpp_scheme_from_meta(meta_path, name)


@contextmanager
def _meta_from_source(filename: str, root_dir: str | None = None):
    """Yield the path of a temporary ``.meta`` generated from tagged *filename*."""
    import os
    import tempfile

    from xdsl_ccpp.tools.ccpp_generate_meta import generate_meta_for_file

    meta_text = generate_meta_for_file(filename, root_dir)
    if meta_text is None:
        raise ValueError(
            f"Could not extract CCPP metadata from {filename!r} "
            f"(see the error printed above)."
        )
    stem = os.path.splitext(os.path.basename(filename))[0]
    with tempfile.TemporaryDirectory() as tmpdir:
        meta_path = os.path.join(tmpdir, f"{stem}.meta")
        with open(meta_path, "w") as f:
            f.write(meta_text)
        yield meta_path


def _schemes_from_meta_file(meta_path: str) -> list[SchemeDescriptor]:
    """Every scheme defined in *meta_path*, in file order."""
    from xdsl_ccpp.frontend.ccpp_xml import parse_meta_file

    names = [str(m.table_properties.getAttr("name"))
             for m in parse_meta_file(meta_path, is_scheme=True)
             if str(m.table_properties.getAttr("type")) == "scheme"]
    return [ccpp_scheme_from_meta(meta_path, n) for n in names]


def _load_scheme_file(filename: str) -> list[SchemeDescriptor]:
    """Every scheme in a ``.meta`` file or a ``!$ccpp``-tagged Fortran file."""
    if filename.lower().endswith((".f90", ".f")):
        with _meta_from_source(filename) as meta_path:
            return _schemes_from_meta_file(meta_path)
    return _schemes_from_meta_file(filename)


def ccpp_host_from_meta(filename: str) -> list[TableDescriptor]:
    """Load CCPP host metadata from a ``.meta`` file.

    Parses *filename* and returns one :class:`TableDescriptor` per
    ``[ccpp-table-properties]`` block.  A single file may contain multiple
    blocks (e.g. a DDT definition followed by a module), so the return value
    is always a list.

    Pass the results in the *additional* argument of :func:`export_suite` or
    :func:`build_ir`::

        host_mod = ccpp_host_from_meta("kessler_host_mod.meta")
        host_sub = ccpp_host_from_meta("kessler_host_sub.meta")

        if __name__ == "__main__":
            export_suite(kessler_suite, additional=[*host_mod, *host_sub])

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
                            array_layout=array_layout,
                            kind_specs=meta.table_properties.kind_specs,
                            **_dependencies_kwargs(meta.table_properties))
        )
    return result


def ccpp_ddt_from_meta(filename: str) -> TableDescriptor:
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
            export_suite(ddt_suite, additional=[vmr_type])

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
    return TableDescriptor(meta.table_properties.getAttr("name"), type_str, arg_tables,
                            kind_specs=meta.table_properties.kind_specs,
                            **_dependencies_kwargs(meta.table_properties))


# ---------------------------------------------------------------------------
# IR construction
# ---------------------------------------------------------------------------


def _arg_op(arg: Arg) -> ArgumentOp:
    return ArgumentOp(arg.name, arg.type, arg.to_ccpp_attrs())


def _table_properties_op(
    table_name: str,
    type_str: str,
    arg_tables: dict[str, list[Arg]],
    array_layout: str | None = None,
    language: str | None = None,
    kind_specs: list[tuple[str, str, str]] | None = None,
    dependencies: list[str] | None = None,
    dependencies_path: str | None = None,
    source_path: str | None = None,
) -> TablePropertiesOp:
    table_ops = []
    for entry_name, args in arg_tables.items():
        arg_ops = [_arg_op(a) for a in args]
        table_ops.append(ArgumentTableOp(entry_name, type_str, arg_ops))
    attrs: dict | None = None
    if (array_layout is not None or (language is not None and language != "fortran")
            or kind_specs or dependencies or dependencies_path is not None
            or source_path is not None):
        attrs = {}
        if array_layout is not None:
            attrs["array_layout"] = StringAttr(array_layout)
        if language is not None and language != "fortran":
            attrs["language"] = StringAttr(language)
        if kind_specs:
            # Same "<module>:<kind_name>=>spec" canonical encoding as
            # ccpp_xml.py's build_meta_ir -- one source of truth for the
            # syntax, decoded by suite_kinds.py's MetaKind pass.
            attrs["kind_specs"] = ArrayAttr([
                StringAttr(f"{module}:{kind_name}=>{spec}")
                for kind_name, module, spec in kind_specs
            ])
        if source_path is not None:
            attrs["source_path"] = StringAttr(source_path)
        if dependencies_path is not None:
            attrs["dependencies_path"] = StringAttr(dependencies_path)
        if dependencies:
            attrs["dependencies"] = ArrayAttr([StringAttr(dep) for dep in dependencies])
    return TablePropertiesOp(table_name, type_str, table_ops, attributes=attrs)


def _scheme_table_properties(sd: SchemeDescriptor) -> TablePropertiesOp:
    entry_tables = {f"{sd.name}_{ep}": args for ep, args in sd.entry_points.items()}
    return _table_properties_op(sd.name, "scheme", entry_tables, language=sd.language,
                                 kind_specs=sd.kind_specs, dependencies=sd.dependencies,
                                 dependencies_path=sd.dependencies_path,
                                 source_path=sd.source_path)


def _register_scheme(seen_schemes: dict[str, SchemeDescriptor], sd: SchemeDescriptor) -> None:
    """Record *sd* under its name; a full descriptor replaces a reference."""
    existing = seen_schemes.get(sd.name)
    if existing is None or (existing.is_reference and not sd.is_reference):
        seen_schemes[sd.name] = sd


def _group_item_to_op(
    item: tuple[SchemeDescriptor, dict[str, str]] | SchemeDescriptor
          | SubcycleDescriptor | CompositeDescriptor,
    seen_schemes: dict[str, SchemeDescriptor],
) -> SchemeOp | SubcycleOp | CompositeOp:
    """Convert one recorded item to its MLIR op, registering schemes seen.

    Loop blocks (`SubcycleDescriptor`) and composite calls
    (`CompositeDescriptor`) recurse through this same function, so they may
    nest in each other to arbitrary depth -- loops mirroring the XML
    frontend's nested `<subcycle>` support (see
    examples/var_compat/var_compatibility_suite.xml, ported from NCAR
    ccpp-framework's feature/capgen-v1, which nests three levels deep).

    Loop-body entries from the list form are bare `SchemeDescriptor`s; those
    from the ``with forLoop(...)`` block form and from composites are
    ``(descriptor, overrides)`` pairs, whose overrides are kept.
    """
    if isinstance(item, SubcycleDescriptor):
        inner_ops = [_group_item_to_op(sub, seen_schemes) for sub in item.schemes]
        return SubcycleOp(item.count, inner_ops, is_literal=isinstance(item.count, int))
    if isinstance(item, CompositeDescriptor):
        inner_ops = [_group_item_to_op(sub, seen_schemes) for sub in item.items]
        return CompositeOp(item.name, inner_ops, package=item.package, hook=item.hook)
    if isinstance(item, SchemeDescriptor):
        item = (item, {})
    sd, overrides = item
    _register_scheme(seen_schemes, sd)
    return SchemeOp(sd.name, overrides or None)


def build_ir(
    suites: SuiteDescriptor | list[SuiteDescriptor],
    additional: list[TableDescriptor | SchemeDescriptor] | None = None,
    *,
    scheme_files: list[str] | None = None,
    host_files: list[str] | None = None,
) -> ModuleOp:
    """Build a :class:`~xdsl.dialects.builtin.ModuleOp` from one or more suite descriptors.

    Produces the same MLIR as the XML/meta frontend (:mod:`xdsl_ccpp.frontend.ccpp_xml`).

    Args:
        suites:       One :class:`SuiteDescriptor` or a list of them.  When a
                      list is given all suites are included in the same
                      ``ModuleOp``, matching the behaviour of the XML frontend
                      when ``--suites`` receives a comma-separated list.
        additional:   Extra DDT/module/host (or scheme) descriptors not already
                      referenced inside any suite's groups.
        scheme_files: ``.meta`` or ``!$ccpp``-tagged Fortran files supplying
                      metadata for :func:`ccpp_scheme_ref` references, matched
                      by scheme name.  When given, every reference must be
                      found in them; when omitted, references emit no
                      metadata (``ccpp_dsl --py --scheme-files`` merges it).
        host_files:   Host/module/DDT ``.meta`` files, appended after
                      *additional*.

    Returns:
        A top-level ``ModuleOp`` ready to be passed to ``ccpp_opt``.

    Raises:
        ValueError: a scheme is defined twice across *scheme_files*, or a
            reference has no metadata in them.
    """
    if isinstance(suites, SuiteDescriptor):
        suites = [suites]

    loaded: dict[str, SchemeDescriptor] = {}
    for path in scheme_files or []:
        for sd in _load_scheme_file(path):
            if sd.name in loaded:
                raise ValueError(f"Scheme '{sd.name}' is defined more than once in scheme_files")
            loaded[sd.name] = sd
    additional = list(additional or [])
    for path in host_files or []:
        additional.extend(ccpp_host_from_meta(path))

    ir_ops = []
    seen_schemes: dict[str, SchemeDescriptor] = {}

    # Build one SuiteOp per suite, collecting unique SchemeDescriptors across all.
    for suite in suites:
        group_ops = []
        for group_name, scheme_list in suite.groups.items():
            ops = [_group_item_to_op(item, seen_schemes) for item in scheme_list]
            group_ops.append(GroupOp(group_name, ops))
        ir_ops.append(SuiteOp(suite.name, group_ops, suite.version))

    # One TablePropertiesOp per unique scheme across all suites; references
    # take their metadata from scheme_files (or are left to the driver).
    for name, sd in seen_schemes.items():
        if sd.is_reference:
            if name in loaded:
                sd = loaded[name]
            elif scheme_files:
                raise ValueError(
                    f"No metadata for scheme '{name}' in scheme_files {scheme_files}"
                )
            else:
                continue
        ir_ops.append(_scheme_table_properties(sd))

    # Additional descriptors (DDTs, host modules, hosts, extra schemes).
    for desc in additional:
        if isinstance(desc, SchemeDescriptor):
            ir_ops.append(_scheme_table_properties(desc))
        else:
            ir_ops.append(
                _table_properties_op(desc.name, desc.type_str, desc.arg_tables,
                                     array_layout=desc.array_layout,
                                     kind_specs=desc.kind_specs,
                                     dependencies=desc.dependencies,
                                     dependencies_path=desc.dependencies_path,
                                     source_path=desc.source_path)
            )

    return ModuleOp(ir_ops)


def export_suite(
    suites: SuiteDescriptor | list[SuiteDescriptor],
    additional: list[TableDescriptor | SchemeDescriptor] | None = None,
) -> None:
    """Hand the suite(s) defined in this script to the CCPP generator.

    Call it at the end of a suite script, inside
    ``if __name__ == "__main__":``.  It writes the suite description (MLIR,
    identical to what the XML/meta frontend produces) to stdout, where the
    generator -- ``ccpp_dsl --py`` or a ``| ccpp_opt`` pipeline -- reads it.

    Pass a list of :class:`SuiteDescriptor` objects to include multiple suites
    in one IR output, matching ``ccpp_xdsl --suites a.xml,b.xml ...``.

    Metadata for :func:`ccpp_scheme_ref` references and for the host comes
    from the script's command line, as the build system would pass it for
    an XML suite (see :func:`build_ir`)::

        python3 suite.py --scheme-files=a.meta,b.F90 --host-files=host.meta
    """
    # This script has no argparse of its own; ccpp_dsl.py's --py mode
    # forwards --legacy-mode as a bare token on this process's own argv
    # (mirroring ccpp_param()'s existing sys.argv-scanning convention).
    # Must run before build_ir() constructs any ArgumentOp below.
    set_legacy_mode("--legacy-mode" in sys.argv)
    print(build_ir(suites, additional,
                   scheme_files=_argv_file_list("--scheme-files"),
                   host_files=_argv_file_list("--host-files")))


def _argv_file_list(option: str) -> list[str] | None:
    """Comma-separated paths from a ``option=a,b`` token on argv, if present."""
    prefix = f"{option}="
    for token in sys.argv[1:]:
        if token.startswith(prefix):
            return [p for p in token[len(prefix):].split(",") if p]
    return None


def emit_ir(
    suites: SuiteDescriptor | list[SuiteDescriptor],
    additional: list[TableDescriptor | SchemeDescriptor] | None = None,
) -> None:
    """Older name for :func:`export_suite`, kept for existing scripts."""
    export_suite(suites, additional)
