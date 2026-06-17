"""validate_fir — Cross-validate CCPP .meta metadata against Fortran source (via FIR).

Provides a pure comparison function that takes two CCPP metadata ModuleOps —
one loaded from ``.meta`` files, one extracted from Fortran source via the
``fir-to-meta`` pass — and returns a list of :class:`Mismatch` objects
describing every discrepancy.

Fields compared per argument:
- type  (``real``, ``integer``, ``character``)
- rank  (number of array dimensions)
- intent (``in``, ``out``, ``inout``)
- optional flag
- kind name (fparser2 backend only — FIR lowers ``kind_phys`` to ``f32``/``f64``)

Fields NOT compared (not present in Fortran source):
- ``standard_name``, ``long_name``, ``units``
- dimension names (checked separately via ``check_dimension_names`` with host files)
"""

from __future__ import annotations

from dataclasses import dataclass

from xdsl.dialects import builtin
from xdsl.ir import Operation

from xdsl_ccpp.dialects.ccpp import ArgumentOp, ArgumentTableOp, TableTypeKind


@dataclass
class Mismatch:
    table_name: str  # procedure name, e.g. "temp_adjust_run"
    arg_name: str    # Fortran arg name, e.g. "qv"
    field: str       # "type", "rank", "intent", "optional", "extra_in_meta", "extra_in_fir"
    meta_value: str  # what the .meta file says (empty when field is extra_in_*)
    fir_value: str   # what the FIR source says (empty when field is extra_in_*)

    def __str__(self) -> str:
        if self.field == "extra_in_meta":
            return (
                f"  {self.table_name}: '{self.arg_name}' is in .meta "
                f"but missing from Fortran source"
            )
        if self.field == "extra_in_fir":
            return (
                f"  {self.table_name}: '{self.arg_name}' is in Fortran source "
                f"but missing from .meta"
            )
        if self.field == "unregistered_dim":
            return (
                f"  {self.table_name}.{self.arg_name}: "
                f"dimension '{self.meta_value}' is not registered in the host model"
            )
        return (
            f"  {self.table_name}.{self.arg_name}: {self.field} mismatch "
            f"(meta='{self.meta_value}', source='{self.fir_value}')"
        )


def _collect_arg_tables(module: builtin.ModuleOp) -> dict[str, ArgumentTableOp]:
    """Recursively collect all ArgumentTableOps, keyed by table_name."""
    result: dict[str, ArgumentTableOp] = {}
    _walk(module, result)
    return result


def _walk(op: Operation, result: dict[str, ArgumentTableOp]) -> None:
    if isinstance(op, ArgumentTableOp):
        result[op.table_name.data] = op
        return
    for region in op.regions:
        for block in region.blocks:
            for child in block.ops:
                _walk(child, result)


def compare_arg_tables(
    meta_table: ArgumentTableOp,
    fir_table: ArgumentTableOp,
) -> list[Mismatch]:
    """Compare one .meta arg table against its FIR-extracted counterpart.

    Returns a (possibly empty) list of Mismatch objects.
    """
    table_name = meta_table.table_name.data

    # Fortran is case-insensitive; normalise both sides to lowercase
    meta_args: dict[str, ArgumentOp] = {
        op.arg_name.data.lower(): op
        for op in meta_table.body.block.ops
        if isinstance(op, ArgumentOp)
    }
    fir_args: dict[str, ArgumentOp] = {
        op.arg_name.data.lower(): op
        for op in fir_table.body.block.ops
        if isinstance(op, ArgumentOp)
    }

    mismatches: list[Mismatch] = []

    for name in sorted(meta_args):
        if name not in fir_args:
            mismatches.append(Mismatch(table_name, name, "extra_in_meta", "", ""))

    for name in sorted(fir_args):
        if name not in meta_args:
            mismatches.append(Mismatch(table_name, name, "extra_in_fir", "", ""))

    for name in sorted(set(meta_args) & set(fir_args)):
        m = meta_args[name]
        f = fir_args[name]

        # type — skip when source reports 'unknown' (e.g. CLASS(*) or types the
        # parser cannot classify; fparser2 resolves TYPE(name) directly so
        # 'unknown' should only appear for genuinely unresolvable cases)
        if m.arg_type.data != f.arg_type.data and f.arg_type.data != "unknown":
            mismatches.append(
                Mismatch(table_name, name, "type", m.arg_type.data, f.arg_type.data)
            )

        # rank (dimension count)
        meta_rank = m.dimensions.data if m.dimensions is not None else 0
        fir_rank = f.dimensions.data if f.dimensions is not None else 0
        if meta_rank != fir_rank:
            mismatches.append(
                Mismatch(table_name, name, "rank", str(meta_rank), str(fir_rank))
            )

        # intent — only flag when both sides declare it; FIR omits intent for
        # some internal arguments (e.g. procedure pointers).
        meta_intent = m.intent.data if m.intent is not None else None
        fir_intent = f.intent.data if f.intent is not None else None
        if meta_intent is not None and fir_intent is not None and meta_intent != fir_intent:
            mismatches.append(
                Mismatch(table_name, name, "intent", meta_intent, fir_intent)
            )

        # optional flag
        meta_opt = m.optional is not None
        fir_opt = f.optional is not None
        if meta_opt != fir_opt:
            mismatches.append(
                Mismatch(
                    table_name, name, "optional",
                    str(meta_opt), str(fir_opt),
                )
            )

        # kind — only compare when both sides supply it; FIR backend does not
        # preserve symbolic kind names (it lowers them to f32/f64/i32 etc.).
        # Normalise by stripping spaces before comparing so that 'len=512' and
        # 'len = 512' (fparser2 preserves source whitespace) are treated equal.
        meta_kind_raw = m.kind.data if m.kind is not None else None
        fir_kind_raw = f.kind.data if f.kind is not None else None
        if meta_kind_raw is not None and fir_kind_raw is not None:
            if (meta_kind_raw.replace(" ", "").lower()
                    != fir_kind_raw.replace(" ", "").lower()):
                mismatches.append(
                    Mismatch(table_name, name, "kind", meta_kind_raw, fir_kind_raw)
                )

    return mismatches


def _collect_names_walk(op: Operation, names: set[str]) -> None:
    if isinstance(op, ArgumentOp):
        if op.standard_name is not None:
            names.add(op.standard_name.data.lower())
        return
    for region in op.regions:
        for block in region.blocks:
            for child in block.ops:
                _collect_names_walk(child, names)


def collect_standard_names(module: builtin.ModuleOp) -> set[str]:
    """Return all standard_name values from every ArgumentOp in *module*."""
    names: set[str] = set()
    _collect_names_walk(module, names)
    return names


def check_dimension_names(
    meta_module: builtin.ModuleOp,
    known_standard_names: set[str],
) -> list[Mismatch]:
    """Check that every dimension name used in scheme args is a known standard name.

    Numeric literals (e.g. the ``6`` in ``(horizontal_dimension, 6)``) are skipped.
    Only scheme-type arg tables are checked; host/module/DDT tables are ignored.
    Returns a list of Mismatch objects with field='unregistered_dim'.
    """
    mismatches: list[Mismatch] = []
    for table in _collect_arg_tables(meta_module).values():
        if table.table_type.data != TableTypeKind.Scheme:
            continue
        for op in table.body.block.ops:
            if not isinstance(op, ArgumentOp):
                continue
            if op.dim_names is None:
                continue
            for raw in op.dim_names.data.split(","):
                dim_name = raw.strip().lower()
                if not dim_name:
                    continue
                if dim_name.lstrip("-").isdigit():
                    continue
                if dim_name not in known_standard_names:
                    mismatches.append(Mismatch(
                        table.table_name.data,
                        op.arg_name.data.lower(),
                        "unregistered_dim",
                        dim_name,
                        "",
                    ))
    return mismatches


def compare_modules(
    meta_module: builtin.ModuleOp,
    fir_module: builtin.ModuleOp,
) -> list[Mismatch]:
    """Compare all scheme arg tables present in both modules.

    Tables that exist only in the .meta module (host-only variables, utility
    tables) are skipped — the FIR module only contains scheme subroutines.
    Tables that exist only in the FIR module (subroutines not listed in any
    .meta file) are also skipped; use compare_modules_strict() for that.
    """
    meta_tables = _collect_arg_tables(meta_module)
    fir_tables = _collect_arg_tables(fir_module)

    mismatches: list[Mismatch] = []
    for name in sorted(meta_tables):
        if name in fir_tables:
            mismatches.extend(compare_arg_tables(meta_tables[name], fir_tables[name]))
    return mismatches
