"""validate_source — Cross-validate CCPP .meta metadata against Fortran source.

Provides a pure comparison function that takes two CCPP metadata ModuleOps —
one loaded from ``.meta`` files, one extracted from Fortran source by
``fparser2_to_meta`` — and returns a list of :class:`Mismatch` objects
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


@dataclass
class ResidencyFinding:
    """One disagreement (or, at level "note", one detail) between a scheme's
    `.meta` memory_space and what its entry point's own OpenACC says
    (acc-derive-memory-space). Notes are printed at --verbose 2 only."""

    level: str  # "warning" or "note"
    table_name: str
    message: str

    def __str__(self) -> str:
        return f"{self.table_name}: {self.message}"


def compare_memory_space(
    meta_module: builtin.ModuleOp,
    acc_residency: dict,
    source_path: str = "",
) -> list[ResidencyFinding]:
    """Compare each scheme argument's `.meta` memory_space with the
    classification of its entry point's OpenACC (*acc_residency*: proc name
    -> fparser2_to_meta.AccResidency).

    Warnings (notes where --directive acc derives the value anyway):
    - the entry point has no OpenACC of its own but calls a routine in the
      same file that has some (e.g. a dispatcher calling the real kernel
      routine): only the entry point is read, so its residency is unclear;
    - the source requires the argument on the device (present, deviceptr,
      update, use_device, default(present)) but `.meta` says memory_space =
      host (a silent `.meta` is a note: derive_memory_space sets device);
    - `.meta` says device, but the entry point has OpenACC directives and
      none of them uses the argument on the device.
    Notes (--verbose 2): arguments the scheme copies itself ("either": a
    copy clause, or an array in a compute construct with no clause) whose
    `.meta` is silent; derived-type arguments left to the scheme; entry
    points with no OpenACC, whose memory_space comes from `.meta` only.
    `unified` in `.meta` is not compared.
    """
    from xdsl_ccpp.transforms.fparser2_to_meta import ACC_DEVICE

    def where(line_no: int) -> str:
        return f"{source_path}:{line_no}" if source_path else f"line {line_no}"

    findings: list[ResidencyFinding] = []
    for name, table in sorted(_collect_arg_tables(meta_module).items()):
        if table.table_type.data != TableTypeKind.Scheme or name not in acc_residency:
            continue
        residency = acc_residency[name]
        meta_args = {
            op.arg_name.data.lower(): op
            for op in table.body.block.ops
            if isinstance(op, ArgumentOp)
        }
        declared_device = sorted(
            arg for arg, op in meta_args.items()
            if op.memory_space is not None and op.memory_space.data == "device"
        )
        if not residency.has_acc:
            callees = sorted(
                callee for callee in residency.calls
                if callee in acc_residency and acc_residency[callee].has_acc
            )
            if callees:
                findings.append(ResidencyFinding(
                    "warning", name,
                    f"has no OpenACC of its own but calls {', '.join(callees)}, "
                    "which does; only the entry point is read, so its arguments' "
                    "device residency is unclear -- put the data directives "
                    "(present/copy clauses) in the entry point",
                ))
            elif declared_device:
                findings.append(ResidencyFinding(
                    "note", name,
                    "no OpenACC in the entry point; memory_space = device for "
                    f"{', '.join(declared_device)} comes from .meta only",
                ))
            continue
        for arg, op in sorted(meta_args.items()):
            declared = op.memory_space.data if op.memory_space is not None else None
            if declared == "unified":
                continue
            use = residency.args.get(arg)
            if arg in residency.derived_types:
                findings.append(ResidencyFinding(
                    "note", name,
                    f"'{arg}' is a derived type its OpenACC moves itself "
                    f"({where(residency.derived_types[arg])}); xdsl-ccpp leaves it on the host",
                ))
            elif use is not None and use.category == ACC_DEVICE and declared is None:
                findings.append(ResidencyFinding(
                    "note", name,
                    f"'{arg}' is used on the device ({use.how}, {where(use.line_no)}): "
                    "memory_space = device is derived with --directive acc",
                ))
            elif use is not None and use.category == ACC_DEVICE and declared != "device":
                findings.append(ResidencyFinding(
                    "warning", name,
                    f"'{arg}' is used on the device ({use.how}, {where(use.line_no)}) "
                    f"but .meta says memory_space = {declared}",
                ))
            elif use is not None and use.category != ACC_DEVICE and declared is None:
                findings.append(ResidencyFinding(
                    "note", name,
                    f"'{arg}' is copied by the scheme itself ({use.how}, "
                    f"{where(use.line_no)}): on the device only where the cap "
                    "already keeps it there",
                ))
            elif use is None and declared == "device":
                findings.append(ResidencyFinding(
                    "warning", name,
                    f"'{arg}' has memory_space = device in .meta, but the entry "
                    "point's OpenACC never uses it on the device",
                ))
    return findings
