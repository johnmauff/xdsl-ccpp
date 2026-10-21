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

Downstream passes therefore see the synthetic schemes as ordinary schemes.
The package's own schemes are no longer called from any suite, so host
matching leaves them alone: their data arrives through the segment interface.
"""

from __future__ import annotations

from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects.builtin import ModuleOp, StringAttr
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp import TableTypeKind
from xdsl_ccpp.transforms.package_scope import private_name
from xdsl_ccpp.transforms.package_segments import Loop, Segment, package_segments
from xdsl_ccpp.transforms.util.cap_shared import iter_arg_tables

# Properties every use of an interface name must agree on.
_MUST_AGREE = ("type", "kind", "units", "dim_names")


def package_cap_module_name(package: str) -> str:
    """Fortran module of a package's cap."""
    return f"{package}_package_cap"


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
            args = interface_args(name, phase, seg.entry.package, calls)
            new_tables.append(ccpp.TablePropertiesOp(
                name, "scheme", [ccpp.ArgumentTableOp(f"{name}_{phase}", "scheme", args)],
                attributes={"source_module": StringAttr(
                    package_cap_module_name(seg.entry.package))}))
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
        for phase, seg in found:
            anchor = outermost_moved(seg.ops[0])
            rewriter.insert_op(ccpp.SchemeOp(seg.name(phase)), InsertPoint.before(anchor))
        for o in moved.values():
            if outermost_moved(o) is o:
                rewriter.erase_op(o)

        first_suite = next(o for o in op.body.block.ops if isa(o, ccpp.SuiteOp))
        for table in new_tables:
            rewriter.insert_op(table, InsertPoint.before(first_suite))
        for package, segment_ops in package_segment_ops.items():
            rewriter.insert_op(ccpp.PackageCapOp(package, segment_ops),
                               InsertPoint.before(first_suite))
