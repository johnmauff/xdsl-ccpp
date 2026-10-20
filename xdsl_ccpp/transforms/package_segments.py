"""Package segmentation (composite-scheme 2f, step 2f-1).

How a per-package cap would cut each package's code into routines
(composite_scheme_plan.md §11, 2f design).  Analysis only: nothing here
changes the IR or the generated code.

For every suite, group and phase, the calls the suite cap makes are walked in
order.  A *segment* is a maximal run of consecutive calls made by one
entry-point call (``ccpp.composite`` tagged ``package``) as package code,
that is, not through one of its hooks.  Host code -- the adapter, the
suite, hook bodies -- separates segments and stays in the suite cap.

Phases follow the suite cap:
- a scheme is called only in the phases it has, so a host scheme without,
  say, an init phase does not split the package's init calls;
- loops (``ccpp.subcycle``) repeat only the run phase; in every other phase
  their calls run once each, in place, so loops are flattened there.

In the run phase a loop whose body is all from one entry-point call stays
inside that call's segment; a loop that also contains host code stays in
the suite cap, with segments inside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from xdsl.dialects.builtin import ModuleOp
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp import TableTypeKind
from xdsl_ccpp.transforms.util.cap_shared import iter_arg_tables
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_INSTANCE_NUMBER_STD_NAME,
    CCPP_NUMBER_OF_INSTANCES_STD_NAME,
)

PHASES = ("register", "init", "timestep_init", "run", "timestep_final", "final")


@dataclass(frozen=True)
class EntryCall:
    """One call of a package entry point (the same entry point may be called
    several times; ``call`` numbers its calls in suite order, from 1)."""

    package: str
    entry_point: str
    call: int


@dataclass
class Loop:
    """A run-phase loop kept as a loop: its body is a list of nodes."""

    count: str
    body: list = field(default_factory=list)


@dataclass
class Segment:
    """Package code that one package-cap routine would hold: scheme names and
    (run phase only) loops of scheme names, in call order."""

    entry: EntryCall
    index: int
    body: list = field(default_factory=list)

    def name(self, phase: str) -> str:
        """Name of the package-cap routine, e.g. ``rrtmgp_shortwave_2`` (run)
        or ``rrtmgp_shortwave_init_1``; a second call of the same entry point
        gets ``_c2`` after the entry-point name."""
        base = self.entry.entry_point
        if self.entry.call > 1:
            base += f"_c{self.entry.call}"
        if phase != "run":
            base += f"_{phase}"
        return f"{base}_{self.index}"


@dataclass(frozen=True)
class HostCall:
    """A scheme call that stays in the suite cap.  ``hook`` is
    ``(entry_point, hook_name)`` for a call made through a hook."""

    scheme: str
    hook: tuple[str, str] | None = None


@dataclass(frozen=True)
class _Call:
    scheme: str
    entry: EntryCall | None
    hook: tuple[str, str] | None


def _scheme_phases(module: ModuleOp) -> dict[str, set[str]]:
    """Scheme name -> the phases it has (from its arg-table names)."""
    phases: dict[str, set[str]] = {}
    for props, table in iter_arg_tables(module, table_type=TableTypeKind.Scheme):
        scheme = props.table_name.data
        phases.setdefault(scheme, set()).add(table.table_name.data[len(scheme) + 1:])
    return phases


class _Walker:
    """Turns one group's ops into a nested list of `_Call`s and `Loop`s for one
    phase.  ``call_numbers`` maps each entry-point composite op (by id) to its
    call number."""

    def __init__(self, phases: dict[str, set[str]], call_numbers: dict[int, int]):
        self.phases = phases
        self.call_numbers = call_numbers

    def items(self, ops, phase, entry=None, hook=None, entry_name=None) -> list:
        out: list = []
        for op in ops:
            if isa(op, ccpp.SchemeOp):
                name = op.scheme_name.data
                if phase in self.phases.get(name, set()):
                    out.append(_Call(name, None if hook else entry, hook))
            elif isa(op, ccpp.SubcycleOp):
                body = self.items(op.body.block.ops, phase, entry, hook, entry_name)
                if phase == "run":
                    if body:
                        out.append(Loop(op.loop_count.data, body))
                else:
                    out.extend(body)
            elif isa(op, ccpp.CompositeOp):
                if op.hook is not None:
                    out.extend(self.items(op.body.block.ops, phase, entry,
                                          (entry_name, op.composite_name.data), entry_name))
                elif op.package is not None:
                    new_entry = EntryCall(op.package.data, op.composite_name.data,
                                          self.call_numbers[id(op)])
                    out.extend(self.items(op.body.block.ops, phase, new_entry, None,
                                          op.composite_name.data))
                else:
                    out.extend(self.items(op.body.block.ops, phase, entry, hook, entry_name))
        return out


def _owners(items) -> set:
    """Entry calls (or None for host code) owning the calls in *items*."""
    owners: set = set()
    for item in items:
        if isinstance(item, Loop):
            owners |= _owners(item.body)
        else:
            owners.add(item.entry)
    return owners


def _strip(items) -> list:
    """Scheme names and loops of scheme names, for a segment body."""
    return [Loop(i.count, _strip(i.body)) if isinstance(i, Loop) else i.scheme
            for i in items]


def _segment(items, counters: dict) -> list:
    """Group *items* into Segments, HostCalls and Loops (see module doc)."""
    out: list = []
    current: Segment | None = None
    for item in items:
        if isinstance(item, Loop):
            owners = _owners(item.body)
            if len(owners) == 1 and None not in owners:
                (entry,) = owners
                if current is None or current.entry != entry:
                    counters[entry] = counters.get(entry, 0) + 1
                    current = Segment(entry, counters[entry])
                    out.append(current)
                current.body.append(Loop(item.count, _strip(item.body)))
            else:
                current = None
                out.append(Loop(item.count, _segment(item.body, counters)))
        elif item.entry is None:
            current = None
            out.append(HostCall(item.scheme, item.hook))
        else:
            if current is None or current.entry != item.entry:
                counters[item.entry] = counters.get(item.entry, 0) + 1
                current = Segment(item.entry, counters[item.entry])
                out.append(current)
            current.body.append(item.scheme)
    return out


def _has_segment(nodes) -> bool:
    return any(isinstance(n, Segment) or (isinstance(n, Loop) and _has_segment(n.body))
               for n in nodes)


def package_segments(module: ModuleOp) -> dict[str, dict[str, dict[str, list]]]:
    """``{suite: {group: {phase: nodes}}}`` for every suite with packages,
    keeping only groups and phases that contain a segment.  *nodes* is a
    list of `Segment`, `HostCall` and (run phase) `Loop`."""
    phases = _scheme_phases(module)
    result: dict = {}
    for suite in module.walk():
        if not isa(suite, ccpp.SuiteOp):
            continue
        # Number each entry point's calls in suite order (walk is pre-order).
        call_numbers: dict[int, int] = {}
        seen: dict[tuple[str, str], int] = {}
        for op in suite.walk():
            if isa(op, ccpp.CompositeOp) and op.package is not None:
                key = (op.package.data, op.composite_name.data)
                seen[key] = seen.get(key, 0) + 1
                call_numbers[id(op)] = seen[key]
        walker = _Walker(phases, call_numbers)
        groups = [op for op in suite.body.block.ops if isa(op, ccpp.GroupOp)]
        per_group: dict = {}
        for group in groups:
            for phase in PHASES:
                nodes = _segment(walker.items(group.body.block.ops, phase), {})
                if _has_segment(nodes):
                    per_group.setdefault(group.group_name.data, {})[phase] = nodes
        if per_group:
            result[suite.suite_name.data] = per_group
    return result


def multi_instance_problems(module: ModuleOp) -> list[str]:
    """Errors when packages are used with a multi-instance host: package state
    is not per instance (composite_scheme_plan.md, 2f decision 4)."""
    packages = sorted({op.package.data for op in module.walk()
                       if isa(op, ccpp.CompositeOp) and op.package is not None})
    if not packages:
        return []
    declared: set[str] = set()
    for _, table in iter_arg_tables(module, table_type=(TableTypeKind.Host,
                                                        TableTypeKind.Module,
                                                        TableTypeKind.Control)):
        for arg in table.body.ops:
            if isa(arg, ccpp.ArgumentOp) and arg.standard_name is not None:
                declared.add(arg.standard_name.data.lower())
    if {CCPP_INSTANCE_NUMBER_STD_NAME, CCPP_NUMBER_OF_INSTANCES_STD_NAME} <= declared:
        return [f"Package(s) {', '.join(packages)} used with a multi-instance host "
                f"({CCPP_INSTANCE_NUMBER_STD_NAME} and {CCPP_NUMBER_OF_INSTANCES_STD_NAME} "
                f"declared); package state is not yet kept per instance."]
    return []


def _format_nodes(nodes, phase, indent) -> list[str]:
    lines = []
    pad = "  " * indent
    for node in nodes:
        if isinstance(node, Segment):
            lines.append(f"{pad}segment {node.name(phase)}: "
                         + ", ".join(_format_body(node.body)))
        elif isinstance(node, HostCall):
            where = f" [hook {node.hook[0]}.{node.hook[1]}]" if node.hook else ""
            lines.append(f"{pad}host    {node.scheme}{where}")
        else:
            lines.append(f"{pad}loop {node.count}:")
            lines.extend(_format_nodes(node.body, phase, indent + 1))
    return lines


def _format_body(body) -> list[str]:
    return [f"loop {b.count}({', '.join(_format_body(b.body))})" if isinstance(b, Loop) else b
            for b in body]


def format_package_segments(segments: dict) -> str:
    """Human-readable report of `package_segments`' result."""
    lines = []
    for suite, groups in segments.items():
        for group, phases in groups.items():
            for phase, nodes in phases.items():
                lines.append(f"segments: suite {suite}, group {group}, phase {phase}")
                lines.extend(_format_nodes(nodes, phase, 1))
    return "\n".join(lines) + ("\n" if lines else "")
