"""Lower packages to package caps (composite-scheme 2f, step 2f-2).

Runs after ``scope-packages`` and before ``flatten-composites``, while the
package boundaries are still in the IR.  For every segment found by
`package_segments` (one routine of the package cap: consecutive calls of one
entry-point call in one phase):

- a **synthetic scheme** named after the segment is added: one arg table for
  the segment's phase, holding the segment's *interface* -- the arguments of
  its schemes in that phase, minus package-private names (``<pkg>__*``),
  merged by standard name;
- the segment's calls in the suite are replaced by **one call** of that
  scheme, placed where the segment's first call was; hook calls stay;
- the calls themselves move into a ``ccpp.package_cap`` op (one per package),
  as one ``ccpp.segment`` each, from which the package cap is generated.

Each package also gets two **state schemes**, ``<pkg>_state_create`` (an
``_init`` phase only) before the package's first call and
``<pkg>_state_delete`` (a ``_finalize`` phase only) after its last: the
package cap generates them to allocate its private arrays (creating
device-resident ones on the device) and to delete them from the device, as
the suite cap's own _initialize/_finalize do for suite-owned arrays.

Downstream passes therefore see the synthetic schemes as ordinary schemes.
The package's own schemes are no longer called from any suite, so host
matching leaves them alone: their data arrives through the segment interface.
"""

from __future__ import annotations

from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects.builtin import ArrayAttr, ModuleOp, StringAttr
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp import TableTypeKind
from xdsl_ccpp.transforms.package_scope import private_name
from xdsl_ccpp.transforms.package_segments import Loop, Segment, package_segments
from xdsl_ccpp.transforms.util.cap_shared import iter_arg_tables
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_ERROR_STD_NAMES,
    CCPP_LOOP_BEGIN_STD_NAME,
    CCPP_LOOP_END_STD_NAME,
    CCPP_LOOP_EXTENT_STD_NAME,
)

# Attribute of a synthetic scheme's table: the package schemes it calls, so
# the host's list of active schemes names them (CAM-SIMA reads a scheme's
# namelist only when the scheme is listed).
SEGMENT_SCHEMES_ATTR = "segment_schemes"

# Properties every use of an interface name must agree on.
_MUST_AGREE = ("type", "kind", "units", "dim_names")


def package_cap_module_name(package: str) -> str:
    """Fortran module of a package's cap."""
    return f"{package}_package_cap"


def state_create_scheme(package: str) -> str:
    """Synthetic scheme whose _init allocates the package's private state."""
    return f"{package}_state_create"


def state_delete_scheme(package: str) -> str:
    """Synthetic scheme whose _finalize deletes the package's private device
    state."""
    return f"{package}_state_delete"


def _segments(nodes):
    for node in nodes:
        if isinstance(node, Segment):
            yield node
        elif isinstance(node, Loop):
            yield from _segments(node.body)


def _scheme_calls(ops):
    """The scheme ops of a segment, in call order, looking into loops."""
    for op in ops:
        if isa(op, ccpp.SchemeOp):
            yield op
        else:
            for inner in op.walk():
                if isa(inner, ccpp.SchemeOp):
                    yield inner


def _prop(arg, name):
    value = arg.properties.get(name)
    return value.data if value is not None else None


def _merged_intent(intents: list[str]) -> str:
    """``in`` if never written, ``out`` if first touched by a pure write,
    ``inout`` otherwise."""
    if not any(i in ("out", "inout") for i in intents):
        return "in"
    return "out" if intents[0] == "out" else "inout"


def interface_args(segment_name: str, phase: str, package: str,
                   calls: list[tuple[str, list]]) -> list:
    """The synthetic scheme's arguments for one segment.

    *calls* is ``[(scheme_name, [ArgumentOp, ...]), ...]`` in call order:
    each scheme's arguments in *phase*.  Package-private names are dropped;
    the others are merged by standard name, keeping the first use's
    declaration and local name (qualified with its scheme if that local name
    is already taken).

    Raises:
        ValueError: when uses of one standard name disagree on type, kind,
            units or dimensions, or an interface argument is dimensioned by
            a package-private name.
    """
    private_prefix = private_name(package, "")
    uses: dict[str, list[tuple[str, object]]] = {}
    for scheme, args in calls:
        for arg in args:
            if arg.standard_name is None:
                continue
            std = arg.standard_name.data.lower()
            if std.startswith(private_prefix):
                continue
            uses.setdefault(std, []).append((scheme, arg))

    out = []
    local_names: set[str] = set()
    for std, std_uses in uses.items():
        scheme, first = std_uses[0]
        for other_scheme, other in std_uses[1:]:
            for prop in _MUST_AGREE:
                if _prop(first, prop) != _prop(other, prop):
                    raise ValueError(
                        f"Segment '{segment_name}' ({phase}): '{std}' has {prop} "
                        f"'{_prop(first, prop)}' in {scheme} but '{_prop(other, prop)}' "
                        f"in {other_scheme}; a package interface needs one.")
        dims = (_prop(first, "dim_names") or "").split(",")
        private_dims = [d for d in dims if d.strip().lower().startswith(private_prefix)]
        if private_dims:
            raise ValueError(
                f"Segment '{segment_name}' ({phase}): interface argument '{std}' is "
                f"dimensioned by package-private {', '.join(private_dims)}.")
        arg = first.clone()
        local = first.arg_name.data
        if local.lower() in local_names:
            local = f"{scheme}_{local}"
        local_names.add(local.lower())
        arg.properties["name"] = StringAttr(local)
        arg.properties["intent"] = StringAttr(
            _merged_intent([_prop(a, "intent") or "in" for _, a in std_uses]))
        out.append(arg)
    return out


def _column_range_args(args: list, phase: str) -> list:
    """Segments are generated like group functions (physics mode, all phases
    but register): the loop extent becomes the column range col_start /
    col_end, the names the generator gives those dummy arguments."""
    if phase == "register":
        return args
    out = []
    for arg in args:
        std = arg.standard_name.data.lower() if arg.standard_name is not None else ""
        if std == CCPP_LOOP_EXTENT_STD_NAME and not (_prop(arg, "dim_names") or ""):
            for local, bound in (("col_start", CCPP_LOOP_BEGIN_STD_NAME),
                                 ("col_end", CCPP_LOOP_END_STD_NAME)):
                out.append(ccpp.ArgumentOp(local, arg.arg_type.data, {
                    "type": arg.arg_type.data, "standard_name": bound, "units": "count",
                    "dimensions": "()", "intent": "in"}))
        else:
            out.append(arg)
    return out


def _check_loops(segment_name: str, ops) -> None:
    """Package-only loops with a non-literal count would need the count in
    the interface under the host's local name: not supported yet."""
    for op in ops:
        for inner in op.walk():
            if isa(inner, ccpp.SubcycleOp) and not inner.is_literal.value.data:
                raise ValueError(
                    f"Segment '{segment_name}': package-only loop over "
                    f"'{inner.loop_count.data}' (a non-literal count) is not "
                    f"supported in package caps yet.")


@dataclass(frozen=True)
class LowerPackages(ModulePass):
    """Lower every package to synthetic segment schemes plus a
    ``ccpp.package_cap`` op (see module docstring).  A module without
    packages is left unchanged."""

    name = "lower-packages"

    def apply(self, ctx: Context, op: ModuleOp) -> None:
        segments = package_segments(op)
        if not segments:
            return
        tables: dict[str, dict] = {}
        for props, table in iter_arg_tables(op, table_type=TableTypeKind.Scheme):
            tables.setdefault(props.table_name.data, {})[table.table_name.data] = table

        found: list[tuple[str, Segment]] = []
        for groups in segments.values():
            for phases in groups.values():
                for phase, nodes in phases.items():
                    found.extend((phase, s) for s in _segments(nodes))

        names: set[str] = set()
        new_tables = []
        package_segment_ops: dict[str, list] = {}
        error_args: dict[str, list] = {}
        for phase, seg in found:
            name = seg.name(phase)
            if name in names or name in tables:
                raise ValueError(
                    f"Package '{seg.entry.package}': segment name '{name}' is not "
                    f"unique (a package used in several suites, or a scheme of that "
                    f"name) -- not supported yet.")
            names.add(name)
            calls = []
            for s in _scheme_calls(seg.ops):
                scheme = s.scheme_name.data
                table = tables.get(scheme, {}).get(f"{scheme}_{phase}")
                if table is None:
                    raise ValueError(f"Scheme '{scheme}' has no {phase} arg table.")
                calls.append((scheme, [a for a in table.body.ops if isa(a, ccpp.ArgumentOp)]))
            _check_loops(name, seg.ops)
            args = _column_range_args(
                interface_args(name, phase, seg.entry.package, calls), phase)
            error_args.setdefault(seg.entry.package, [
                a.clone() for a in args
                if a.standard_name is not None
                and a.standard_name.data.lower() in CCPP_ERROR_STD_NAMES])
            new_tables.append(ccpp.TablePropertiesOp(
                name, "scheme", [ccpp.ArgumentTableOp(f"{name}_{phase}", "scheme", args)],
                attributes={
                    "source_module": StringAttr(package_cap_module_name(seg.entry.package)),
                    SEGMENT_SCHEMES_ATTR: ArrayAttr(
                        [StringAttr(s) for s in dict.fromkeys(s for s, _ in calls)]),
                }))
            package_segment_ops.setdefault(seg.entry.package, []).append(
                ccpp.SegmentOp(name, phase, seg.entry.entry_point,
                               [o.clone() for o in seg.ops]))

        # Rewrite the suites: one synthetic call per segment where its first
        # call was, then remove the moved calls.
        moved = {id(o): o for _, seg in found for o in seg.ops}

        def outermost_moved(o):
            top = o
            parent = o.parent_op()
            while parent is not None:
                if id(parent) in moved:
                    top = parent
                parent = parent.parent_op()
            return top

        rewriter = Rewriter()
        segment_calls: dict[str, set] = {}
        for phase, seg in found:
            anchor = outermost_moved(seg.ops[0])
            rewriter.insert_op(ccpp.SchemeOp(seg.name(phase)), InsertPoint.before(anchor))
            segment_calls.setdefault(seg.entry.package, set())
        for o in moved.values():
            if outermost_moved(o) is o:
                rewriter.erase_op(o)

        # State schemes: create before the package's first entry-point call,
        # delete after its last (hooks included), outside any loop.
        def outside_loops(o):
            while isa(o.parent_op(), ccpp.SubcycleOp):
                o = o.parent_op()
            return o

        for package in segment_calls:
            calls = [o for o in op.walk()
                     if isa(o, ccpp.CompositeOp) and o.hook is None
                     and o.package is not None and o.package.data == package]
            for scheme, phase, where in (
                    (state_create_scheme(package), "init", InsertPoint.before(outside_loops(calls[0]))),
                    (state_delete_scheme(package), "finalize", InsertPoint.after(outside_loops(calls[-1])))):
                if scheme in names or scheme in tables:
                    raise ValueError(f"Package '{package}': state scheme name '{scheme}' "
                                     f"is already used.")
                new_tables.append(ccpp.TablePropertiesOp(
                    scheme, "scheme",
                    [ccpp.ArgumentTableOp(f"{scheme}_{phase}", "scheme",
                                          [a.clone() for a in error_args[package]])],
                    attributes={
                        "source_module": StringAttr(package_cap_module_name(package)),
                        SEGMENT_SCHEMES_ATTR: ArrayAttr([]),
                    }))
                rewriter.insert_op(ccpp.SchemeOp(scheme), where)

        first_suite = next(o for o in op.body.block.ops if isa(o, ccpp.SuiteOp))
        for table in new_tables:
            rewriter.insert_op(table, InsertPoint.before(first_suite))
        for package, segment_ops in package_segment_ops.items():
            rewriter.insert_op(ccpp.PackageCapOp(package, segment_ops),
                               InsertPoint.before(first_suite))
