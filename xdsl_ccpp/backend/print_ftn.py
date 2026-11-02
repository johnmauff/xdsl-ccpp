from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import IO, cast

from xdsl.dialects import arith, builtin, func, llvm, math, memref, scf
from xdsl.dialects.builtin import (
    DYNAMIC_INDEX,
    Float32Type,
    Float64Type,
    FloatAttr,
    FunctionType,
    IntAttr,
    IntegerAttr,
    IntegerType,
    MemRefType,
    ModuleOp,
    StringAttr,
)
from xdsl.ir import Attribute, Block, BlockArgument, Operation, OpResult, Region, SSAValue
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp_utils import AccDataBeginOp as CCPPAccDataBeginOp
from xdsl_ccpp.dialects.ccpp_utils import AccDataEndOp as CCPPAccDataEndOp
from xdsl_ccpp.dialects.ccpp_utils import AccEnterDataOp as CCPPAccEnterDataOp
from xdsl_ccpp.dialects.ccpp_utils import AccExitDataOp as CCPPAccExitDataOp
from xdsl_ccpp.dialects.ccpp_utils import AccParallelOp as CCPPAccParallelOp
from xdsl_ccpp.dialects.ccpp_utils import AccUpdateDeviceOp as CCPPAccUpdateDeviceOp
from xdsl_ccpp.dialects.ccpp_utils import AccUpdateSelfOp as CCPPAccUpdateSelfOp
from xdsl_ccpp.dialects.ccpp_utils import ActiveCheckOp as CCPPActiveCheckOp
from xdsl_ccpp.dialects.ccpp_utils import ClearErrStateOp as CCPPClearErrStateOp
from xdsl_ccpp.dialects.ccpp_utils import ErrorExitOp as CCPPErrorExitOp
from xdsl_ccpp.dialects.ccpp_utils import ReturnStmtOp as CCPPReturnStmtOp
from xdsl_ccpp.dialects.ccpp_utils import CamDirectCallOp as CCPPCamDirectCallOp
from xdsl_ccpp.dialects.ccpp_utils import CallStatementOp as CCPPCallStatementOp
from xdsl_ccpp.dialects.ccpp_utils import CamSuiteDispatchOp as CCPPCamSuiteDispatchOp
from xdsl_ccpp.dialects.ccpp_utils import CapVarRefOp as CCPPCapVarRefOp
from xdsl_ccpp.dialects.ccpp_utils import CHostCapOp as CCPPCHostCapOp
from xdsl_ccpp.dialects.ccpp_utils import ClearStringOp as CCPPClearStringOp
from xdsl_ccpp.dialects.ccpp_utils import DerivedType as CCPPDerivedType
from xdsl_ccpp.dialects.ccpp_utils import ErrorPropagateOp as CCPPErrorPropagateOp
from xdsl_ccpp.dialects.ccpp_utils import ExprTextLiteralOp as CCPPExprTextLiteralOp
from xdsl_ccpp.dialects.ccpp_utils import HostVarRefOp as CCPPHostVarRefOp
from xdsl_ccpp.dialects.ccpp_utils import KeywordCallOp as CCPPKeywordCallOp
from xdsl_ccpp.dialects.ccpp_utils import KindCastOp as CCPPKindCastOp
from xdsl_ccpp.dialects.ccpp_utils import KindDefOp as CCPPKindDefOp
from xdsl_ccpp.dialects.ccpp_utils import KindWriteBackOp as CCPPKindWriteBackOp
from xdsl_ccpp.dialects.ccpp_utils import LazyAllocOp as CCPPLazyAllocOp
from xdsl_ccpp.dialects.ccpp_utils import ModuleVarOp as CCPPModuleVarOp
from xdsl_ccpp.dialects.ccpp_utils import (
    OmpTargetDataBeginOp as CCPPOmpTargetDataBeginOp,
)
from xdsl_ccpp.dialects.ccpp_utils import OmpTargetDataEndOp as CCPPOmpTargetDataEndOp
from xdsl_ccpp.dialects.ccpp_utils import (
    OmpTargetEnterDataOp as CCPPOmpTargetEnterDataOp,
)
from xdsl_ccpp.dialects.ccpp_utils import OmpTargetExitDataOp as CCPPOmpTargetExitDataOp
from xdsl_ccpp.dialects.ccpp_utils import (
    OmpTargetUpdateFromOp as CCPPOmpTargetUpdateFromOp,
)
from xdsl_ccpp.dialects.ccpp_utils import OmpTargetUpdateToOp as CCPPOmpTargetUpdateToOp
from xdsl_ccpp.dialects.ccpp_utils import PresentCheckOp as CCPPPresentCheckOp
from xdsl_ccpp.dialects.ccpp_utils import PromotionLoopOp as CCPPPromotionLoopOp
from xdsl_ccpp.dialects.ccpp_utils import RankReducingSliceOp as CCPPRankReducingSliceOp
from xdsl_ccpp.dialects.ccpp_utils import RealKindType as CCPPRealKindType
from xdsl_ccpp.dialects.ccpp_utils import RowMajorConvertOp as CCPPRowMajorConvertOp
from xdsl_ccpp.dialects.ccpp_utils import RowMajorWriteBackOp as CCPPRowMajorWriteBackOp
from xdsl_ccpp.dialects.ccpp_utils import ArrayConstructorExprOp as CCPPArrayConstructorExprOp
from xdsl_ccpp.dialects.ccpp_utils import CallExprOp as CCPPCallExprOp
from xdsl_ccpp.dialects.ccpp_utils import IndexExprOp as CCPPIndexExprOp
from xdsl_ccpp.dialects.ccpp_utils import KeywordArgExprOp as CCPPKeywordArgExprOp
from xdsl_ccpp.dialects.ccpp_utils import MemberAccessExprOp as CCPPMemberAccessExprOp
from xdsl_ccpp.dialects.ccpp_utils import SliceExprOp as CCPPSliceExprOp
from xdsl_ccpp.dialects.ccpp_utils import StringConcatExprOp as CCPPStringConcatExprOp
from xdsl_ccpp.dialects.ccpp_utils import StringLiteralExprOp as CCPPStringLiteralExprOp
from xdsl_ccpp.dialects.ccpp_utils import ValueExprOp as CCPPValueExprOp
from xdsl_ccpp.dialects.ccpp_utils import VarRefExprOp as CCPPVarRefExprOp
from xdsl_ccpp.dialects.ccpp_utils import AllocateOp as CCPPAllocateOp
from xdsl_ccpp.dialects.ccpp_utils import DdtMethodCallOp as CCPPDdtMethodCallOp
from xdsl_ccpp.dialects.ccpp_utils import ErrorGuardOp as CCPPErrorGuardOp
from xdsl_ccpp.dialects.ccpp_utils import NullifyPointerOp as CCPPNullifyPointerOp
from xdsl_ccpp.dialects.ccpp_utils import AssignOp as CCPPAssignOp
from xdsl_ccpp.dialects.ccpp_utils import PointerAssignOp as CCPPPointerAssignOp
from xdsl_ccpp.dialects.ccpp_utils import SafeDeallocOp as CCPPSafeDeallocOp
from xdsl_ccpp.dialects.ccpp_utils import ScopedBlockOp as CCPPScopedBlockOp
from xdsl_ccpp.dialects.ccpp_utils import DoLoopOp as CCPPDoLoopOp
from xdsl_ccpp.dialects.ccpp_utils import MetadataLiteralExprOp as CCPPMetadataLiteralExprOp
from xdsl_ccpp.dialects.ccpp_utils import NullPointerExprOp as CCPPNullPointerExprOp
from xdsl_ccpp.dialects.ccpp_utils import MethodCallExprOp as CCPPMethodCallExprOp
from xdsl_ccpp.dialects.ccpp_utils import ZeroFillOp as CCPPZeroFillOp
from xdsl_ccpp.dialects.ccpp_utils import ConstituentApiOp as CCPPConstituentApiOp
from xdsl_ccpp.dialects.ccpp_utils import (
    DdtComponentDeclOp as CCPPDdtComponentDeclOp,
)
from xdsl_ccpp.dialects.ccpp_utils import (
    DerivedTypeDefOp as CCPPDerivedTypeDefOp,
)
from xdsl_ccpp.dialects.ccpp_utils import (
    CToFortranStringCopyOp as CCPPCToFortranStringCopyOp,
)
from xdsl_ccpp.dialects.ccpp_utils import (
    FortranToCStringCopyOp as CCPPFortranToCStringCopyOp,
)
from xdsl_ccpp.dialects.ccpp_utils import SetStringOp as CCPPSetStringOp
from xdsl_ccpp.dialects.ccpp_utils import StrCmpOp as CCPPStrCmpOp
from xdsl_ccpp.dialects.ccpp_utils import SubcycleLoopOp as CCPPSubcycleLoopOp
from xdsl_ccpp.dialects.ccpp_utils import TrimOp as CCPPTrimOp
from xdsl_ccpp.dialects.ccpp_utils import UnitConvertOp as CCPPUnitConvertOp
from xdsl_ccpp.dialects.ccpp_utils import UnitWriteBackOp as CCPPUnitWriteBackOp
from xdsl_ccpp.dialects.ccpp_utils import VerticalFlipOp as CCPPVerticalFlipOp
from xdsl_ccpp.dialects.ccpp_utils import (
    VerticalFlipWriteBackOp as CCPPVerticalFlipWriteBackOp,
)
from xdsl_ccpp.dialects.ccpp_utils import WriteErrMsgOp as CCPPWriteErrMsgOp
from xdsl_ccpp.dialects.ccpp_utils import WriteStmtOp as CCPPWriteStmtOp
from xdsl_ccpp.dialects.ccpp_utils import PrintStmtOp as CCPPPrintStmtOp
from xdsl_ccpp.backend import expr_precedence
from xdsl_ccpp.util.ccpp_conventions import (
    FN_FIXED_INTERFACE,
    FN_RESULT,
    FN_USES,
    arg_attr_values,
    arg_decl,
    is_allocatable_local,
    is_pointer_local,
    local_name,
)
# print_op has its own local_name variables, which would shadow this there.
from xdsl_ccpp.util.ccpp_conventions import local_name as recorded_local_name

_MAX_LINE_LEN = 99


def wrap_paren_list(
    prefix: str, items: list, suffix: str, max_col: int, cont_indent: str,
    cont_marker: str = " &",
) -> list:
    """Emit ``{prefix}{items joined by ', '}{suffix}``, continuation-wrapping
    the item list onto ``cont_indent``-indented lines (each ending in
    ``cont_marker``) when the single-line form would exceed ``max_col``.

    ``cont_marker`` defaults to Fortran's ``" &"`` continuation (both
    existing call sites below are Fortran and rely on this default,
    unchanged). Pass ``cont_marker=""`` for C++, which needs no
    continuation marker at all (``CppCallStatementOp`` in
    ``print_cpp_header.py``, which imports this cross-module the same way
    that module already imports ``classify_arg_intent`` from here).

    Used by CallStatementOp's printing (and the C++ printer's
    CppCallStatementOp) -- replacing hand-rolled copies of the same wrap
    loop that cpp_interop.py once had (``_emit_subr_header``/``_emit_call``).
    """
    single = prefix + ", ".join(items) + suffix
    if len(single) <= max_col:
        return [single]
    lines = [prefix + cont_marker]
    cur = cont_indent
    for i, item in enumerate(items):
        sep = ", " if i < len(items) - 1 else ""
        # Never flush an empty line: an item too long for any line (a long
        # string literal) goes on a line of its own.
        if cur.strip() and len(cur) + len(item) + len(sep) + 4 > max_col:
            lines.append(cur + cont_marker)
            cur = cont_indent + item + sep
        else:
            cur += item + sep
    lines.append(cur + suffix)
    return lines


def _extent_text(names: "list[str]") -> str:
    """One explicit-shape extent from a bind_c_extents entry (see
    cap_shared.bind_c_extents_attr): n; hi - lo + 1; or assumed size."""
    if not names:
        return "*"
    if len(names) == 1:
        return names[0]
    lo, hi = names
    return f"{hi} - {lo} + 1"


def _decl_fortran_type(op) -> str:
    """The Fortran type of a ModuleVarOp or DdtComponentDeclOp, from its
    structured attributes (DdtComponentDeclOp has no is_target: TARGET is
    illegal on a derived-type component)."""
    base = op.base_type.data
    kind = op.kind.data if op.kind is not None else None

    if base == "type":
        ftn = f"type({op.ddt_name.data})"
    elif base == "character":
        specs = []
        if kind is not None:
            specs.append(f"kind={kind}")
        if op.char_len is not None:
            specs.append(f"len={op.char_len.value.data}")
        ftn = f"character({', '.join(specs)})" if specs else base
    elif kind is not None:
        ftn = f"{base}(kind={kind})"
    else:
        ftn = base

    is_target = getattr(op, "is_target", None)
    if is_target is not None and is_target.value.data:
        ftn += ", target"
    if op.is_pointer is not None and op.is_pointer.value.data:
        ftn += ", pointer"
    return ftn


# ---------------------------------------------------------------------
# Scheme I/O capture -- generated test-driver rendering (scheme-io-capture
# backlog item, PR 3). Deliberately standalone, not IR-driven like the
# rest of this file: scheme_io_capture_pass.py builds one standalone
# Fortran *program* per captured scheme call site (reads a fixture back,
# calls the real scheme, compares), which is categorically different from
# a generated cap's own module/subroutine structure this file's IR walk
# otherwise renders -- there's no existing dialect for "an arbitrary local
# scalar/array declaration in a standalone program," and building one
# solely for this dev-tooling feature would be disproportionate to its
# scope. What belongs here regardless, per this file's own role as the
# one place that knows Fortran syntax: the actual text-rendering logic.
# TestDriverParam is this function's plain, Fortran-agnostic input
# contract -- scheme_io_capture_pass.py resolves CCPP metadata (intent,
# optionality, dim_names) into these before calling in; nothing here
# reads a CCPPArgument or any other CCPP-metadata type directly.
@dataclass(frozen=True)
class TestDriverParam:
    """One real scheme-call keyword argument, already classified by CCPP
    semantics (scheme_io_capture_pass.py's own _driver_param_category) --
    "in"/"out"/"inout" (a real captured argument, fixture-backed),
    "error_arg" (errmsg/errflg -- declared and passed, never compared), or
    "unverified" (mandatory but outside the capture pass's v1 type scope
    -- declared and passed so the call compiles, never compared). `dims`
    is the resolved list of *other* local parameter names sizing this
    argument (e.g. ["ncol", "nz"]) when rank > 0, else None. `is_device`
    (scheme-io-capture-gpu-residency) mirrors the scheme's own
    memory_space=device attribute for this argument (the same
    cap_shared._device_arg_names lookup the real cap itself uses) --
    drives whether the driver establishes/tears down a device copy of it
    around the call; see _render_driver_enter_data/_render_driver_exit_data.
    A captured array (in/out/inout) has no `dims`: the driver sizes it
    from the capture file (ccpp_capture_extents).

    A captured derived-type argument (scheme-io-capture-ddt-args) has
    `ddt_read`, the procedure (in module `ddt_read_module`) that rebuilds
    it from the capture file, and `type_module`, the module declaring its
    type `arg_type`.
    """

    name: str
    category: str
    arg_type: "str | None"
    kind: "str | None"
    rank: int
    dims: "list[str] | None" = None
    is_device: bool = False
    ddt_read: "str | None" = None
    ddt_read_module: "str | None" = None
    type_module: "str | None" = None


def _test_driver_decl_type(arg_type: "str | None", kind: "str | None") -> str:
    """Fortran declaration-prefix text (everything before ` :: name`) for
    one TestDriverParam."""
    if arg_type == "real":
        return f"real(kind={kind or 'kind_phys'})"
    if arg_type == "integer":
        return "integer"
    if arg_type == "logical":
        return "logical"
    if arg_type == "character":
        length = "512"
        if kind and "len" in kind:
            raw = kind.split("=", 1)[1].strip()
            if raw not in ("", "*"):
                length = raw
        return f"character(len={length})"
    # Any other/DDT type should never actually reach here in practice --
    # anything of a type this framework can't resolve would already have
    # failed host-var matching earlier in the pipeline. Fall back to
    # something that at least compiles; the driver simply won't verify it.
    return "real(kind=kind_phys)"


def format_fortran_real_literal(value: float, kind: str = "kind_phys") -> str:
    """Format a Python float as a safe, portable Fortran real(kind=`kind`)
    literal -- used by scheme_io_capture_pass.py to turn a user-supplied
    --capture-tolerance value into the generated test driver's own
    `tolerance` PARAMETER (scheme-io-capture-tolerance-config). Always
    includes an explicit decimal point: Python's own repr() of a small or
    large float (e.g. repr(1e-10) == '1e-10') omits one, and while a bare
    mantissa + exponent letter is technically unambiguous Fortran, adding
    the decimal point explicitly is cheap and removes any doubt across
    compiler families.
    """
    text = repr(value)
    if "." not in text:
        e_idx = next((i for i, c in enumerate(text) if c in "eE"), None)
        if e_idx is None:
            text += ".0"
        else:
            text = text[:e_idx] + ".0" + text[e_idx:]
    return f"{text}_{kind}"


def _render_driver_enter_data(directive: str, copyin_names: "list[str]", create_names: "list[str]") -> "str | None":
    """One `!$acc enter data`/`!$omp target enter data` line establishing
    device residency for this phase's own memory_space=device arguments,
    for scheme-io-capture-gpu-residency -- a generated test driver is a
    standalone program with no surrounding suite-level device residency
    to rely on (unlike a real cap, which assumes it's already established
    elsewhere and only needs an `update self` sync before reading a value
    back for capture -- see scheme_io_capture_pass.py's own
    _insert_capture docstring), so it must create its own device copies
    around each call. `copyin_names` (intent in/inout -- a real captured
    value worth transferring) and `create_names` (intent out -- nothing
    useful to transfer yet, device allocation only) mirror the same
    needs_in/needs_out distinction the real cap's own AccEnterDataOp
    printer makes (ccpp_utils.py/print_ftn.py's own module-level case).
    Returns None when both lists are empty (no device-resident args this
    phase). No `#ifdef USE_GPU` guard, unlike that real-cap printer: the
    capture pass always asks for directives (OpenACC by default), which
    are comments unless the driver is compiled with OpenACC/OpenMP, so
    one driver serves a CPU and a GPU replay.
    """
    if directive == "acc":
        clauses = []
        if copyin_names:
            clauses.append(f"copyin({', '.join(copyin_names)})")
        if create_names:
            clauses.append(f"create({', '.join(create_names)})")
        if not clauses:
            return None
        return "!$acc enter data " + " ".join(clauses)
    clauses = []
    if copyin_names:
        clauses.append(f"map(to:{', '.join(copyin_names)})")
    if create_names:
        clauses.append(f"map(alloc:{', '.join(create_names)})")
    if not clauses:
        return None
    return "!$omp target enter data " + " ".join(clauses)


def _render_driver_exit_data(directive: str, copyout_names: "list[str]", delete_names: "list[str]") -> "str | None":
    """The exit half of _render_driver_enter_data, above -- emitted after
    the call (and after the errflg check) so that `copyout_names`
    (intent out/inout -- the scheme's own device-side result) are back in
    the driver's host-side variable BEFORE the after/compare steps read
    it; `delete_names` (intent in -- never read again) just releases the
    device copy with no transfer back. Returns None when both lists are
    empty.
    """
    if directive == "acc":
        clauses = []
        if copyout_names:
            clauses.append(f"copyout({', '.join(copyout_names)})")
        if delete_names:
            clauses.append(f"delete({', '.join(delete_names)})")
        if not clauses:
            return None
        return "!$acc exit data " + " ".join(clauses)
    clauses = []
    if copyout_names:
        clauses.append(f"map(from:{', '.join(copyout_names)})")
    if delete_names:
        clauses.append(f"map(release:{', '.join(delete_names)})")
    if not clauses:
        return None
    return "!$omp target exit data " + " ".join(clauses)


def _render_test_driver_phase_block(
    table_name: str,
    params: "list[TestDriverParam]",
    declared: set,
    directive: "str | None" = None,
) -> "tuple[list[str], list[str]]":
    """Render one phase's own declarations and body lines for
    render_scheme_io_capture_test_driver, below. `declared` is the set of
    local variable names already declared by an earlier phase block in
    the same driver (mutated in place) -- a scheme's own phases routinely
    share argument names for CCPP-mandated roles (errmsg/errflg above
    all), and Fortran rejects a duplicate declaration, so a name already
    declared is simply reused rather than redeclared. Returns
    (decls, body_lines) -- decls only for names first introduced by this
    phase, body_lines this phase's own read/call/compare sequence.

    Replays every captured call of this phase, not just the first: a
    shared `call_count`/`found` pair (declared once by the caller, reused
    across every phase's own loop) drives a `do ... exit` loop that opens
    the call's capture file (ccpp_capture_open_call: <table>_<n>.nc,
    scheme-io-capture-netcdf) for call_count=1, 2, 3, ..., reads its `in`
    group, calls the scheme, reads the `out` group, and stops at the
    first call with no file. No file at all for call 1 is a FAIL (the
    driver would otherwise pass without testing anything). A real
    FPHYStest run produces several calls per table (one per
    chunk/timestep). Array
    allocations move inside the loop with an `allocated()` guard (not
    allocated once up front): a real scheme's own column count can
    legitimately differ from one captured call to the next (different
    chunks), so each iteration must be free to reallocate.
    """
    decls: list[str] = []
    allocates: list[str] = []
    # Scalar "before" reads (dimension-bound args like ncol/nz, per CCPP's
    # own dim_names convention) must run before any allocate(...) that
    # depends on their value -- kept separate from array reads so the
    # final emission order below can put every scalar read ahead of every
    # allocate, which must in turn come ahead of every array read.
    scalar_before_reads: list[str] = []
    array_before_reads: list[str] = []
    after_reads: list[str] = []
    compares: list[str] = []
    call_kwargs: list[str] = []
    errmsg_param = None
    errflg_param = None
    # scheme-io-capture-gpu-residency: a memory_space=device argument needs
    # its own device copy established before the call and torn down after
    # -- which transfer direction depends on intent, same needs_in/needs_out
    # split the real cap's own AccEnterDataOp/AccExitDataOp construction
    # uses (see _render_driver_enter_data/_render_driver_exit_data above).
    enter_copyin: list[str] = []
    enter_create: list[str] = []
    exit_copyout: list[str] = []
    exit_delete: list[str] = []

    def _declare(name: str, decl_line: str) -> None:
        if name in declared:
            return
        declared.add(name)
        decls.append(decl_line)

    def _read_lines(group: str, captured_name: str, var_name: str) -> list:
        return [f'call ccpp_capture_read("{group}", "{captured_name}", {var_name})']

    def _allocate_lines(var_name: str, rank: int, extents: "list[str] | None", group: str,
                        captured_name: str) -> list:
        """(Re)allocate an array to `extents`, or, without them, to the
        shape of `captured_name` in `group` of the open capture file."""
        lines = [f"if (allocated({var_name})) deallocate({var_name})"]
        if extents is None:
            lines.append(
                f'call ccpp_capture_extents("{group}", "{captured_name}", '
                f"extents{rank}, extents_found)"
            )
            extents = [f"extents{rank}({i})" for i in range(1, rank + 1)]
        lines.append(f"allocate({var_name}({', '.join(extents)}))")
        return lines

    for p in params:
        call_kwargs.append(f"{p.name}={p.name}")
        decl_type = _test_driver_decl_type(p.arg_type, p.kind)

        if p.ddt_read is not None:
            # A derived type: rebuilt from the capture file (its read
            # allocates it), never compared.
            colons = ", ".join(":" for _ in range(p.rank))
            _declare(p.name, f"type({p.arg_type}), allocatable :: {p.name}({colons})")
            array_before_reads.append(f'call {p.ddt_read}("in", "{p.name}", {p.name})')
            continue

        if p.category == "error_arg":
            _declare(p.name, f"{decl_type} :: {p.name}")
            if p.arg_type == "character":
                errmsg_param = p.name
            elif p.arg_type == "integer":
                errflg_param = p.name
            continue

        if p.rank == 0:
            _declare(p.name, f"{decl_type} :: {p.name}")
        else:
            colons = ", ".join(":" for _ in range(p.rank))
            _declare(p.name, f"{decl_type}, allocatable :: {p.name}({colons})")
            group = "out" if p.category == "out" else "in"
            allocates += _allocate_lines(p.name, p.rank, p.dims, group, p.name)

        if p.category == "unverified":
            continue

        # category in ("in", "out", "inout") -- a real captured argument.
        if directive and p.is_device:
            if p.category in ("in", "inout"):
                enter_copyin.append(p.name)
            else:
                enter_create.append(p.name)
            if p.category in ("out", "inout"):
                exit_copyout.append(p.name)
            else:
                exit_delete.append(p.name)

        if p.category in ("in", "inout"):
            lines = _read_lines("in", p.name, p.name)
            if p.rank == 0:
                scalar_before_reads += lines
            else:
                array_before_reads += lines
        if p.category in ("out", "inout"):
            expected = f"{p.name}_expected"
            if p.rank == 0:
                _declare(expected, f"{decl_type} :: {expected}")
            else:
                colons = ", ".join(":" for _ in range(p.rank))
                _declare(expected, f"{decl_type}, allocatable :: {expected}({colons})")
                allocates += _allocate_lines(expected, p.rank, None, "out", p.name)
            after_reads += _read_lines("out", p.name, expected)
            if p.rank == 0:
                # Scalar: no "which index" diagnostic makes sense, and the
                # driver already has both values in scope -- print them
                # directly on FAIL rather than asking ccpp_capture_mod.F90
                # for anything.
                if p.arg_type == "real":
                    compares.append(f"ok = ccpp_capture_compare({p.name}, {expected}, tolerance)")
                else:
                    compares.append(f"ok = ccpp_capture_compare({p.name}, {expected})")
                compares.append(f'call report("{p.name}", call_count, ok, n_failed)')
                compares.append(
                    f"if (.not. ok) write(*,*) '  actual=', {p.name}, ' expected=', {expected}"
                )
            elif p.arg_type == "real":
                compares.append(
                    f"ok = ccpp_capture_compare({p.name}, {expected}, tolerance, "
                    "diag_max_abs_diff, diag_mean_abs_diff, diag_first_mismatch_index)"
                )
                compares.append(f'call report("{p.name}", call_count, ok, n_failed)')
                compares.append(
                    "if (.not. ok) write(*,*) '  max abs diff=', diag_max_abs_diff, "
                    "' mean abs diff=', diag_mean_abs_diff, "
                    "' first mismatch at linear index=', diag_first_mismatch_index"
                )
            else:
                compares.append(
                    f"ok = ccpp_capture_compare({p.name}, {expected}, diag_first_mismatch_index)"
                )
                compares.append(f'call report("{p.name}", call_count, ok, n_failed)')
                compares.append(
                    "if (.not. ok) write(*,*) '  first mismatch at linear index=', "
                    "diag_first_mismatch_index"
                )

    enter_data_line = (
        _render_driver_enter_data(directive, enter_copyin, enter_create) if directive else None
    )
    exit_data_line = (
        _render_driver_exit_data(directive, exit_copyout, exit_delete) if directive else None
    )

    body: list[str] = [
        f"  ! -- {table_name} --",
        "  call_count = 1",
        "  do",
        f'    call ccpp_capture_open_call("{table_name}", call_count, found)',
        "    if (.not. found) exit",
    ]
    # Order matters: scalar "before" reads must land before the
    # allocate()s that size arrays off of them, which must in turn land
    # before the array "before" reads they size. The enter-data directive
    # (when present) comes last of all, right before the call, so every
    # device-resident array's host side already holds its captured
    # "before" value (or is at least allocated, for an out-only array)
    # before it's transferred to the device.
    body += [f"    {r}" for r in scalar_before_reads]
    body += [f"    {a}" for a in allocates]
    body += [f"    {r}" for r in array_before_reads]
    if enter_data_line is not None:
        body += [f"    {enter_data_line}"]
    body += ["", f"    call {table_name}({', '.join(call_kwargs)})", ""]
    if errflg_param is not None:
        body += [
            f"    if ({errflg_param} /= 0) then",
            f"      write(*,*) 'FAIL: {table_name} returned errflg=', {errflg_param}, "
            "' (call ', call_count, ')'"
            + (f", ' errmsg=', trim({errmsg_param})" if errmsg_param else ""),
            "      n_failed = n_failed + 1",
            "    end if",
            "",
        ]
    # The exit-data directive comes first of all here, before any
    # after/compare step -- it's what actually brings a device-resident
    # out/inout array's real, scheme-computed result back into the host
    # variable those later steps read; without it they'd silently compare
    # against the array's unchanged pre-call host value on every GPU build.
    if exit_data_line is not None:
        body += [f"    {exit_data_line}"]
    body += [f"    {r}" for r in after_reads]
    body += ["    call ccpp_capture_close()"]
    body += [f"    {c}" for c in compares]
    body += [
        "    call_count = call_count + 1",
        "  end do",
        "  if (call_count == 1) then",
        f"    write(*,*) 'FAIL: no captured calls of {table_name} found'",
        "    n_failed = n_failed + 1",
        "  end if",
    ]
    return decls, body


def render_scheme_io_capture_test_driver(
    scheme_name: str,
    phase_tables: "list[tuple[str, list[TestDriverParam], str]]",
    tolerance: str,
    directive: "str | None" = None,
) -> str:
    """Render a standalone Fortran test-driver program (`test_<scheme_name>
    .F90`'s own content) replaying every captured phase of one scheme, in
    the lifecycle order the caller already sorted `phase_tables` into
    (register/initialize/timestep_initial/run/timestep_final/finalize --
    see scheme_io_capture_pass.py's own phase-ordering logic, a CCPP
    semantics decision this function doesn't make). A scheme's `_run`
    phase routinely depends on module-private state only its own
    `_initialize` phase sets (confirmed directly: kessler_run reads
    module-level lv/pref/rhoqr that only kessler_init sets) -- replaying
    a scheme as this whole, ordered unit, not one isolated phase at a
    time, is what makes the comparison meaningful instead of spuriously
    failing on uninitialized state.

    Each `phase_tables` entry is (table name, params, Fortran module of
    the table's subroutine -- not always the scheme name: CAM-SIMA's
    state_converters module holds several schemes).

    Each `TestDriverParam` list in `phase_tables` is already fully
    resolved and filtered by the caller (no `optional` entries, every
    array's `dims` already a resolved local-name list) -- this function
    only knows Fortran syntax, not why a given param has the category it
    has.

    `tolerance` is a pre-formatted Fortran real literal (the caller's
    job, via `format_fortran_real_literal`) used as the compiled-in
    default passed to `ccpp_capture_tolerance_override` at program
    startup -- NOT a `parameter` anymore. That lets the generated binary
    be re-run with a different tolerance (the `CCPP_CAPTURE_TOLERANCE`
    environment variable) without regenerating or recompiling, which
    matters for cross-compiler/GPU-port comparisons where the right
    tolerance is discovered by iterating, not known up front.

    `directive` ("acc", "omp", or None -- scheme-io-capture-gpu-residency)
    is the same CLI choice `--directive` makes for the real cap; when set,
    every `TestDriverParam.is_device` argument gets its own
    `!$acc enter data`/`!$omp target enter data` before the call and the
    matching exit-data after it, since this standalone driver has no
    surrounding suite-level device residency to lean on the way a real
    cap does. None (the default) emits no directive text at all, exactly
    like today for every existing CPU-only driver.
    """
    declared: set = set()
    all_decls: list[str] = []
    all_body: list[str] = []
    for table_name, params, _module in phase_tables:
        decls, body = _render_test_driver_phase_block(table_name, params, declared, directive)
        all_decls += decls
        all_body += body

    table_names = [t for t, _, _ in phase_tables]
    use_lines = [f"  use {module}, only: {t}" for t, _, module in phase_tables]
    # Derived types: their declaring module and the procedure rebuilding them.
    ddt_uses: list[str] = []
    for _, params, _module in phase_tables:
        for p in params:
            if p.ddt_read is None:
                continue
            for line in (f"  use {p.type_module}, only: {p.arg_type}",
                         f"  use {p.ddt_read_module}, only: {p.ddt_read}"):
                if line not in ddt_uses:
                    ddt_uses.append(line)
    use_lines = ddt_uses + use_lines

    lines = [
        "! Generated by xdsl_ccpp's --capture-test-driver-dir -- reads back a",
        f"! fixture captured from a real run of {scheme_name} (via --capture-scheme",
        f"! {scheme_name}), replays each captured phase ({', '.join(table_names)})",
        "! against it in lifecycle order, and compares outputs against the captured",
        "! 'after' snapshot. Not hand-maintained -- regenerate rather than hand-edit.",
        f"program test_{scheme_name}",
        "  use ccpp_kinds, only: kind_phys",
        "  use ccpp_capture_mod, only: ccpp_capture_open_call, ccpp_capture_close, &",
        "                              ccpp_capture_read, ccpp_capture_compare, &",
        "                              ccpp_capture_extents, ccpp_capture_tolerance_override",
    ]
    lines += use_lines
    lines += [
        "",
        "  implicit none",
        "",
        "  real(kind=kind_phys) :: tolerance",
        "  integer :: n_failed",
        "  integer :: call_count",
        "  logical :: found",
        "  logical :: ok",
        "  real(kind=kind_phys) :: diag_max_abs_diff, diag_mean_abs_diff",
        "  integer :: diag_first_mismatch_index",
        "  integer :: extents1(1), extents2(2), extents3(3)",
        "  logical :: extents_found",
    ]
    lines += [f"  {d}" for d in all_decls]
    lines += [
        "",
        f"  tolerance = ccpp_capture_tolerance_override({tolerance})",
        "  n_failed = 0",
        "",
    ]
    lines += all_body
    lines += [
        "",
        "  if (n_failed == 0) then",
        "    write(*,*) 'ALL TESTS PASSED'",
        "  else",
        "    write(*,*) n_failed, ' TEST(S) FAILED'",
        "    call exit(1)",
        "  end if",
        "",
        "contains",
        "",
        "  subroutine report(name, call_count, ok, n_failed)",
        "    character(len=*), intent(in) :: name",
        "    integer, intent(in) :: call_count",
        "    logical, intent(in) :: ok",
        "    integer, intent(inout) :: n_failed",
        "",
        "    if (ok) then",
        "      write(*,*) 'PASS: ', trim(name), ' (call ', call_count, ')'",
        "    else",
        "      write(*,*) 'FAIL: ', trim(name), ' (call ', call_count, ')'",
        "      n_failed = n_failed + 1",
        "    end if",
        "  end subroutine report",
        "",
        f"end program test_{scheme_name}",
    ]
    return "\n".join(lines) + "\n"


def classify_arg_intent(
    *,
    is_allocatable_char: bool,
    is_alloc: bool,
    is_in: bool,
    has_array_dims: bool,
    is_inout_return: bool,
    declared_intent: "str | None" = None,
) -> str:
    """Return the CCPP-cap intent ('in'/'inout'/'out') for a block argument.

    Single source of truth for the intent-classification decision tree --
    both this file's own `_print_fn` (the Fortran printer) and
    `print_cpp_header.py`'s `_intent_from_arg` (the BIND(C) header printer)
    must produce the identical intent for the identical argument, since
    they're printing two views of the same generated subroutine signature.
    Before this was extracted, `print_cpp_header.py` carried its own
    hand-copied replica that was missing the `is_alloc` branch entirely --
    harmless today only because every current allocatable (non-character)
    argument also happens to have array dims, so it fell through to the
    same "inout" via `has_array_dims` instead; a future scalar allocatable
    argument (e.g. a scalar workspace scratch var) would have silently
    gotten the wrong intent in the C++ header while the Fortran side
    stayed correct. A pure function over booleans (no xDSL type
    dependency) so it can't accidentally pick up file-specific state and
    both callers are forced through the exact same branch order.

    is_allocatable_char -- True for memref<memref<?xi8>> (allocatable
        character array): always intent(out), the callee allocates and
        fills it.
    is_alloc -- True for an allocatable (non-character) arg (arg_decl):
        intent(inout).
    is_in -- True for an array arg narrowed to intent(in) (arg_decl):
        intent(in).
    has_array_dims -- True when the type has at least one dynamic array
        dimension: intent(inout) (the host provides the buffer, the
        scheme may write to it in place).
    is_inout_return -- True when this block arg is echoed back in the
        function's own ReturnOp (see `_print_fn`'s `inout_block_args`
        scan): intent(inout).
    declared_intent -- the intent the function's arg_attrs fix for this
        argument (arg_decl), which overrides everything above.
    """
    if declared_intent is not None:
        return declared_intent
    if is_allocatable_char:
        return "out"
    if is_alloc:
        return "inout"
    if is_in:
        return "in"
    if has_array_dims:
        return "inout"
    if is_inout_return:
        return "inout"
    return "in"


@dataclass
class _FnBodyAnalysis:
    """Pure-analysis results for one ``func.FuncOp`` body, computed by
    ``ftnPrintContext._analyze_fn_body`` before any printing begins.

    input_names/output_names -- dummy-argument names (arg_decls' names,
        and the alloca results' name hints).
    arg_decls -- each block arg's ArgDecl (name and declaration flags).
    output_ret_vals -- the AllocaOp results paired 1:1 with output_names.
    inout_block_args -- block args echoed back in the function's own
        ReturnOp -- these get intent(inout) rather than the default in.
    local_allocas -- AllocaOps whose result is not itself a return value
        (i.e. real local variables, not output arguments).
    untracked_call_results -- (SSA value, hint) pairs for call results with
        no CopyOp consumer -- these become anonymous local declarations.
    """

    input_names: list
    arg_decls: list
    output_names: list
    output_ret_vals: list
    inout_block_args: set
    local_allocas: list
    untracked_call_results: list


@dataclass
class ftnPrintContext:
    """Stateful context for printing MLIR IR as Fortran source text.

    Each context owns an indentation prefix and a mapping from SSA values to
    Fortran variable names.  Nested structures (subroutines, if-blocks, etc.)
    are handled by creating a child context via `descend`, which inherits the
    current variable map and adds one level of indentation.
    """

    _INDEX = "i32"
    _INDENT = "  "
    output: IO[str]

    # Current indentation string prepended to every line
    _prefix: str = field(default="")

    # Map from SSA value to its Fortran variable name
    variables: dict[SSAValue, str] = field(default_factory=dict[SSAValue, str])

    # Counter used to generate unique fallback variable names
    _counter: int = field(default=0)

    # The enclosing function's optional dummy arguments (block args), set by
    # _print_fn from its arg_attrs: an absent one has no bounds, so array
    # copies of it are gated on present().
    optional_args: set = field(default_factory=set)

    # Whether the program being printed actually contains a generated
    # @ccpp_kinds module (generate_kinds.py is a no-op, and emits none, when
    # no ccpp.kinds op is present anywhere -- e.g. an example with no
    # kind_phys/kind_dyn declarations at all). Every other module's preamble
    # must skip `use ccpp_kinds` in that case, or the generated Fortran
    # references a module that was never written. Defaults to True so
    # existing single-module callers (unit tests constructing a context
    # directly) keep today's behavior; print_to_ftn sets this explicitly
    # after inspecting the whole program.
    has_kinds_module: bool = field(default=True)

    # Buffer accumulating the current line being built via partial print() calls
    _line_buf: str = field(default="")

    # Maps arith op names to their Fortran infix operator strings
    _binops: dict[str, str] = field(default_factory=dict[str, str])

    # Maps comparison op names to a predicate-string → Fortran-operator dict
    _cmp_ops: dict[str, dict[str, str | None]] = field(
        default_factory=dict[str, dict[str, str | None]]
    )

    # Tracks how many times each allocatable char array has been stored to.
    # Key: id of the SSA value; value: 1-based index of the next store.
    # Used to emit allocate(arr(N)) once and suites(i) = ... with correct indices.
    _allocatable_store_indices: dict = field(default_factory=dict)

    def register_binops(self):
        """Populate the binary-operator and comparison-operator lookup tables.

        Must be called once before printing begins.  Kept separate from
        __init__ so that child contexts created by `descend` can share the
        already-populated dicts without re-building them.
        """
        self._binops.update(
            {
                arith.AddfOp.name: "+",
                arith.AddiOp.name: "+",
                arith.MulfOp.name: "*",
                arith.MuliOp.name: "*",
                arith.DivfOp.name: "/",
                arith.DivSIOp.name: "/",
                arith.DivUIOp.name: "/",
                arith.SubfOp.name: "-",
                arith.SubiOp.name: "-",
                arith.RemSIOp.name: "%",
                arith.RemUIOp.name: "%",
                arith.ShLIOp.name: "<<",
                # Fortran logical .and./.or., not C-style bitwise & / | --
                # this codebase's only real use of AndIOp/OrIOp is on i1
                # (boolean) operands (the XOrIOp-as-NOT idiom's siblings),
                # never wide-integer bitwise ops, so the Fortran-valid
                # logical spelling is correct here. (This table was unread
                # by any code before Stage 1a of lang-neutral-expr-ir, so
                # these entries were never exercised/verified -- fixed as
                # part of actually wiring the table up for the first time.)
                arith.AndIOp.name: ".and.",
                arith.OrIOp.name: ".or.",
            }
        )
        self._cmp_ops.update(
            {
                arith.CmpiOp.name: {
                    "eq": ".eq.",
                    "ne": ".ne.",
                    "slt": ".lt.",
                    "sle": ".le.",
                    "sgt": ".gt.",
                    "sge": ".ge.",
                    "ult": ".lt.",
                    "ule": ".le.",
                    "ugt": ".gt.",
                    "uge": ".ge.",
                },
                arith.CmpfOp.name: {
                    "false": None,
                    "oeq": "==",
                    "ogt": ">",
                    "oge": ">=",
                    "olt": "<",
                    "ole": "<=",
                    # "one" (ordered not-equal) must be FALSE for a NaN
                    # operand, but Fortran's "/=" is always TRUE for NaN --
                    # mapping it there silently changes NaN semantics.
                    # Same reasoning for "ueq"/unordered relational
                    # predicates below: they must be TRUE for a NaN
                    # operand, but the mapped ordinary comparison tokens
                    # are always FALSE for NaN. Only "une" (unordered
                    # not-equal) actually matches Fortran "/=" (true
                    # whenever the values differ OR either is NaN).
                    # Reject rather than silently change NaN semantics
                    # (Copilot PR #109 review, 2026-10-05).
                    "one": None,
                    "ord": None,
                    "ueq": None,
                    "ugt": None,
                    "uge": None,
                    "ult": None,
                    "ule": None,
                    "une": "/=",
                    "uno": None,
                    "true": None,
                },
            }
        )

    def _get_variable_name_for(self, val: SSAValue, hint: str | None = None) -> str:
        """Return the Fortran variable name assigned to an SSA value.

        If the value has already been assigned a name it is returned directly.
        Otherwise a new name is chosen, preferring the value's name_hint (or
        the caller-supplied hint), and falling back to a numbered prefix when
        the hint is absent or already taken.
        """
        if val in self.variables:
            return self.variables[val]

        taken_names = set(self.variables.values())

        if hint is None:
            hint = val.name_hint

        if hint is not None and hint not in taken_names:
            name = hint
        else:
            # Generate a unique name using a numeric suffix
            prefix = "v" if val.name_hint is None else val.name_hint

            name = f"{prefix}{self._counter}"
            self._counter += 1

            while name in taken_names:
                name = f"{prefix}{self._counter}"
                self._counter += 1

        self.variables[val] = name
        return name

    @staticmethod
    def _is_allocatable_char(type_attr: Attribute) -> bool:
        """Return True if type_attr is memref<memref<?xi8>> (allocatable character array)."""
        match type_attr:
            case MemRefType(
                element_type=MemRefType(element_type=IntegerType(width=IntAttr(data=8)))
            ):
                return True
            case _:
                return False


    def mlir_type_to_ftn_type(self, type_attr: Attribute) -> str:
        """Convert an MLIR type attribute to its Fortran type declaration string.

        Supported types:
          - f32 / f64       → real(kind=4) / real(kind=8)
          - i1              → logical
          - i8              → character
          - i32             → integer
          - memref<T>       → the Fortran type of T (scalar, no dimensions)
          - memref<NxT>     → character(len=N) for character, T(N) otherwise
        """
        match type_attr:
            case CCPPDerivedType() as dt:
                return f"type({dt.type_name.data})"
            case CCPPRealKindType() as rkt:
                return f"real(kind={rkt.kind_name.data})"
            case Float32Type():
                return "real(kind=4)"
            case Float64Type():
                return "real(kind=8)"
            case IntegerType(width=IntAttr(1)):
                return "logical"
            case IntegerType(width=IntAttr(8)):
                return "character"
            case IntegerType():
                assert cast(IntegerType, type_attr).width.data == 32
                return "integer"
            case MemRefType(element_type=IntegerType(width=IntAttr(data=8)), shape=shape):
                # Character memref: the last dimension encodes the string length;
                # preceding dimensions (if any) are array dimensions.
                # e.g. memref<?xi8>   → character(len=*)  (scalar string)
                #      memref<32xi8>  → character(len=32) (scalar fixed-len)
                #      memref<?x?xi8> → character(len=*)  (1D array of strings)
                if not shape:
                    return "character"
                last_dim = list(shape)[-1]
                len_str = "*" if last_dim.data == DYNAMIC_INDEX else str(last_dim.data)
                return f"character(len={len_str})"
            case MemRefType(element_type=Attribute() as elem_t, shape=shape):
                if any(dim.data == DYNAMIC_INDEX for dim in shape):
                    # Dynamic-dimension array: return only the base type string.
                    # The caller uses _ftn_dim_suffix to append '(:, :)' etc. to
                    # the variable name in the declaration.
                    return self.mlir_type_to_ftn_type(elem_t)
                if not shape:
                    # Zero-dimensional memref — treat as a plain scalar
                    return self.mlir_type_to_ftn_type(elem_t)
                # A static-shape array (character memrefs are handled
                # above): its dimensions belong on the name, which this
                # type spelling cannot express.
                raise ValueError(
                    f"mlir_type_to_ftn_type: no Fortran type for static-shape {type_attr}"
                )

    def _elem_kind_name(self, type_attr: Attribute) -> str | None:
        """Return the Fortran kind name for the element of a real memref, or None."""
        match type_attr:
            case MemRefType(element_type=CCPPRealKindType() as rk):
                return rk.kind_name.data
            case CCPPRealKindType() as rk:
                return rk.kind_name.data
            case MemRefType(element_type=Float32Type()):
                return "4"
            case MemRefType(element_type=Float64Type()):
                return "8"
            case Float32Type():
                return "4"
            case Float64Type():
                return "8"
            case _:
                return None

    @staticmethod
    def _unit_conversion_text(op, kind: str | None) -> str:
        """The conversion a UnitConvertOp/UnitWriteBackOp applies, as the
        tail of its assignment's right-hand side (e.g. "+ 273.15_kind_phys");
        "" for none. The factor takes the variable's kind, so Fortran uses
        the right precision instead of default real (REAL32)."""
        if op.operation is None:
            return ""
        symbol = {"add": "+", "sub": "-", "mul": "*"}[op.operation.data]
        factor = op.factor.data
        return f"{symbol} {factor}_{kind}" if kind is not None else f"{symbol} {factor}"

    def _ftn_dim_suffix(self, type_attr: Attribute) -> str:
        """Return the Fortran assumed-shape array suffix for a memref type.

        For a memref with N dynamic dimensions this returns ``"(:, :, ...)"``
        (N colons), which is appended to the variable name in a declaration to
        produce e.g. ``real(kind=8), intent(inout) :: temp_level(:, :)``.

        Returns an empty string for scalar types and statically-sized memrefs
        (such as ``character(len=512)``).
        """
        if self._is_allocatable_char(type_attr):
            return "(:)"
        match type_attr:
            case MemRefType(element_type=IntegerType(width=IntAttr(data=8)), shape=shape):
                # Character memref: last dim = string length, preceding = array dims.
                # Only the array dims (all but last) produce a '(:, ...)' suffix.
                n_array_dims = len(shape) - 1
                if n_array_dims <= 0:
                    return ""
                return "(" + ", ".join(":" for _ in range(n_array_dims)) + ")"
            case MemRefType(shape=shape) if any(
                dim.data == DYNAMIC_INDEX for dim in shape
            ):
                # One ':' per dynamic dimension
                return "(" + ", ".join(":" for _ in shape) + ")"
            case _:
                return ""

    def attribute_value_to_str(self, attr: Attribute) -> str:
        """Convert an arith.ConstantOp's value attribute (an integer, logical
        or float) to a Fortran literal string."""
        match attr:
            case IntAttr():
                return str(cast(IntAttr[int], attr).data)
            case IntegerAttr(value=val, type=IntegerType(width=IntAttr(data=1))):
                # i1 values are printed as Fortran logical literals --
                # ".true."/".false.", not bare "true"/"false" (not valid
                # Fortran; fixed as part of Stage 1a of lang-neutral-expr-ir,
                # since nothing previously exercised an i1 arith.ConstantOp
                # reaching this specific rendering path to catch the bug)
                return f".{bool(val.data)}.".lower()
            case IntegerAttr(value=val):
                return str(val.data)
            case FloatAttr(value=val) if val.data == 0:
                return "0.0"
            case FloatAttr(value=val):
                return str(val.data)
            case _:
                raise ValueError(f"attribute_value_to_str: no Fortran literal for {attr}")

    def _value_to_expr_str(self, val: SSAValue) -> str:
        """Return the Fortran expression string for an SSA value without printing.

        Checks the variable map first, then falls back to reading the literal
        value for arith.ConstantOp results, and finally generates a fresh name.
        """
        if val in self.variables:
            return self.variables[val]
        if isa(val.owner, arith.ConstantOp):
            return self.attribute_value_to_str(val.owner.value)
        return self._get_variable_name_for(val)

    def print_expr(self, op: Operation):
        """Recursively print op as an inline Fortran expression (no newline).

        Only operations that can appear as sub-expressions are handled here.
        Statement-level operations are handled by print_op instead. Thin
        wrapper over _render_expr (lang-neutral-expr-ir Stage 2): the whole
        expression is rendered to a string first so that precedence-correct
        parenthesization can be applied, then printed in one shot -- same
        final output as printing incrementally, since nothing here ever
        needs a newline mid-expression.
        """
        self.print(self._render_expr(op), end="", use_prefix=False)

    def _target_text(self, op, name_attr) -> str:
        """The variable an op names: its identifier property, or its target
        reference expression (see ccpp_utils._name_or_target)."""
        if name_attr is not None:
            return name_attr.data
        return self._render_expr(op.target.block.last_op)

    def _render_value(self, val: SSAValue) -> str:
        """Render an SSA value used as an operand: resolve it by name
        first (covers function block arguments, whose owner is a Block,
        not an Operation -- _render_expr's own match must never recurse
        into val.owner blindly for those), falling back to recursively
        rendering its defining operation."""
        if val in self.variables:
            return self.variables[val]
        if isinstance(val, BlockArgument):
            return self._get_variable_name_for(val)
        return self._render_expr(val.owner)

    def _is_negative_numeric_literal(self, val: SSAValue) -> bool:
        """True if val is an arith.ConstantOp holding a negative int/float
        value -- needed because math.Pow*'s lhs must be parenthesized when
        negative: Fortran's ** binds tighter than unary minus, so
        "-2.0 ** 2.0" parses as "-(2.0 ** 2.0)" == -4.0, not
        "(-2.0) ** 2.0" == 4.0, and the generic atom/precedence mechanism
        alone never parenthesizes a bare literal (ATOM_LEVEL never needs
        outer parens)."""
        owner = val.owner
        if not isa(owner, arith.ConstantOp):
            return False
        match owner.value:
            # i1 (logical) constants are never "negative" -- xDSL stores
            # a 1-bit True as the signed bit pattern -1, which would
            # otherwise misclassify every .true. literal as negative
            # once this helper started being used more broadly than
            # math.Pow*'s own numeric-only lhs (Copilot PR #109 review,
            # 2026-10-05 generalization of _render_binop surfaced this).
            case IntegerAttr(type=IntegerType(width=IntAttr(data=1))):
                return False
            case IntegerAttr(value=v):
                return v.data < 0
            case FloatAttr(value=v):
                return v.data < 0
            case _:
                return False

    def _is_i1(self, val: SSAValue) -> bool:
        """True if val's type is i1 -- AndIOp/OrIOp only have a valid
        Fortran rendering (.and./.or.) when both operands are logical
        (i1); for a wider integer type, Fortran's .and./.or. are invalid
        between integers (the bitwise intrinsics iand/ior are needed
        instead, not yet implemented here -- Copilot PR #109 review,
        2026-10-05)."""
        return isa(val.type, IntegerType) and val.type.width.data == 1

    def _cmp_token(self, op: Operation, predicate_name: str) -> str:
        """Look up op's Fortran comparison token for predicate_name,
        raising instead of silently rendering a literal "None" when the
        predicate has no Fortran-safe rendering (e.g. CmpfOp's
        NaN-unordered predicates)."""
        tok = self._cmp_ops[op.name][predicate_name]
        if tok is None:
            raise AssertionError(
                f"print_expr: predicate {predicate_name!r} on {op.name} has "
                "no Fortran rendering"
            )
        return tok

    def _render_binop(self, op: Operation, l: SSAValue, r: SSAValue, token: str) -> str:
        """Render `{lhs} {token} {rhs}`, wrapping either side in parens
        when its own precedence/associativity requires it relative to
        `op`'s (shared xdsl_ccpp/backend/expr_precedence.py table).

        A negative-literal RIGHT operand gets an extra forced paren
        regardless of precedence: a bare literal is always ATOM_LEVEL, so
        the generic precedence mechanism alone never parenthesizes it,
        but a negative literal sitting directly next to `token` (e.g.
        "x * -2") is a nonstandard consecutive-operator sequence some
        Fortran compilers reject outright -- same reasoning as
        math.Pow*'s own existing negative-base handling below,
        generalized here instead of being special-cased to just that one
        op (Copilot PR #109 review, 2026-10-05). Only the right operand
        needs this: a negative literal on the left has no preceding
        operator token to collide with.
        """
        my_level = expr_precedence.level_of(op)
        my_assoc = expr_precedence.assoc_of(op)
        lhs_str = expr_precedence.parenthesize(
            self._render_value(l), expr_precedence.level_of(l.owner),
            my_level, "lhs", my_assoc,
        )
        rhs_str = expr_precedence.parenthesize(
            self._render_value(r), expr_precedence.level_of(r.owner),
            my_level, "rhs", my_assoc,
        )
        if self._is_negative_numeric_literal(r):
            rhs_str = f"({rhs_str})"
        return f"{lhs_str} {token} {rhs_str}"

    def _render_base_expr(self, base_region: Region) -> str:
        """Render a 'base' region (MemberAccessExprOp/IndexExprOp/
        SliceExprOp.lower/upper/stride): its last op is the root/value
        (any earlier ops are flattened-in floating dependencies -- see
        _flatten_floating_deps), parenthesized if its own precedence is
        looser than the atomic postfix access binding to it (e.g. a
        member access on a binary-op result -- not exercised by any real
        call site yet, but structurally possible once this op composes
        with arith ops)."""
        base_op = base_region.block.last_op
        return expr_precedence.parenthesize(
            self._render_expr(base_op), expr_precedence.level_of(base_op),
            expr_precedence.ATOM_LEVEL, "lhs", "left",
        )

    def _render_expr(self, op: Operation) -> str:
        """Recursively render op as a Fortran expression string.

        Only operations that can appear as sub-expressions are handled here.
        Statement-level operations are handled by print_op instead.
        """
        match op:
            case arith.ConstantOp(value=v):
                # Emit the literal value of the constant
                return self.attribute_value_to_str(v)
            case memref.LoadOp(memref=arr):
                # A load from a memref is represented by the variable name itself
                return self._get_variable_name_for(arr)
            case arith.CmpiOp(predicate=v, lhs=l, rhs=r):
                # Emit lhs <op> rhs using the Fortran comparison operator
                str_pred = arith.CMPI_COMPARISON_OPERATIONS[v.value.data]
                return self._render_binop(op, l, r, self._cmp_token(op, str_pred))
            case arith.CmpfOp(predicate=v, lhs=l, rhs=r):
                # Float-comparison sibling of the CmpiOp case above -- same
                # shape, arith's own float predicate table instead of the
                # int one.
                str_pred = arith.CMPF_COMPARISON_OPERATIONS[v.value.data]
                return self._render_binop(op, l, r, self._cmp_token(op, str_pred))
            case arith.XOrIOp():
                # XOrI(x, 1_i1) is a logical NOT; detect which operand is
                # the constant. NOTE: this detection is constant-VALUE-
                # blind (any constant operand, true or false, triggers the
                # NOT shortcut) -- a pre-existing latent bug that predates
                # lang-neutral-expr-ir, deliberately not fixed here since it
                # would change already-shipped Fortran output for a
                # currently-passing real call site; flagged separately as
                # its own backlog item, not touched by this change.
                l, r = op.lhs, op.rhs
                if isa(r.owner, arith.ConstantOp):
                    return f".NOT. ({self._render_value(l)})"
                elif isa(l.owner, arith.ConstantOp):
                    return f".NOT. ({self._render_value(r)})"
                else:
                    # General XOR, now precedence-aware via the shared
                    # expr_precedence table: .eqv./.neqv. bind looser than
                    # .and./.or. in Fortran, so a nested AndIOp/OrIOp child
                    # now gets correctly parenthesized (previously this
                    # branch printed flat, unparenthesized text
                    # unconditionally).
                    return self._render_binop(op, l, r, ".neqv.")
            case CCPPTrimOp():
                lhs_name = self._get_variable_name_for(op.lhs)
                return f"trim({lhs_name})"
            case CCPPStrCmpOp():
                if op.literal is not None:
                    return f"{self._render_expr(op.lhs.owner)} .eq. '{op.literal.data}'"
                else:
                    lhs_name = self._get_variable_name_for(op.lhs)
                    rhs_name = self._get_variable_name_for(op.rhs)
                    return f"{lhs_name} .eq. {rhs_name}"
            case arith.AndIOp() | arith.OrIOp():
                # .and./.or. are only valid Fortran between LOGICAL (i1)
                # operands -- a wider integer AndIOp/OrIOp (real bitwise
                # AND/OR) would need the iand/ior intrinsics instead, not
                # implemented here. Reject rather than silently emit
                # invalid Fortran (Copilot PR #109 review, 2026-10-05).
                if not (self._is_i1(op.lhs) and self._is_i1(op.rhs)):
                    raise AssertionError(
                        f"print_expr: {op.name} on non-i1 operands has no "
                        "Fortran rendering -- .and./.or. are logical-only; "
                        "integer bitwise and/or needs iand/ior, not "
                        "implemented"
                    )
                return self._render_binop(op, op.lhs, op.rhs, self._binops[op.name])
            case (
                arith.AddiOp() | arith.SubiOp()
                | arith.MuliOp() | arith.DivSIOp() | arith.DivUIOp()
                | arith.AddfOp() | arith.SubfOp() | arith.MulfOp() | arith.DivfOp()
            ):
                # Table-driven: every op here reads its Fortran token from
                # the shared _binops table (populated by register_binops)
                # and is parenthesized against its neighbors via the shared
                # xdsl_ccpp/backend/expr_precedence table -- lang-neutral-
                # expr-ir Stage 2 unifies AddiOp/SubiOp (previously
                # hand-written, unparenthesized) with the rest of this group.
                return self._render_binop(op, op.lhs, op.rhs, self._binops[op.name])
            case math.PowFOp() | math.IPowIOp() | math.FPowIOp():
                # Fortran has a native ** operator (unlike C++, which needs
                # std::pow) -- first real use of the math dialect in this
                # project. ** is right-associative and binds tighter than
                # unary minus, so a negative-literal base needs a forced
                # paren the generic atom/precedence mechanism alone can't
                # supply (a bare literal is always ATOM_LEVEL, so
                # parenthesize() alone never wraps it): "-2.0 ** 2.0"
                # parses as "-(2.0 ** 2.0)" == -4.0 in Fortran, not
                # "(-2.0) ** 2.0" == 4.0.
                lhs_str = expr_precedence.parenthesize(
                    self._render_value(op.lhs), expr_precedence.level_of(op.lhs.owner),
                    expr_precedence.LEVEL_POW, "lhs", "right",
                )
                if self._is_negative_numeric_literal(op.lhs):
                    lhs_str = f"({lhs_str})"
                rhs_str = expr_precedence.parenthesize(
                    self._render_value(op.rhs), expr_precedence.level_of(op.rhs.owner),
                    expr_precedence.LEVEL_POW, "rhs", "right",
                )
                if self._is_negative_numeric_literal(op.rhs):
                    # "2.0 ** -3.0" is the same nonstandard consecutive-
                    # operator sequence _render_binop's own rhs fix
                    # addresses -- needed here too since this branch
                    # builds its own lhs/rhs strings directly rather than
                    # going through _render_binop (Copilot PR #109
                    # review, 2026-10-05).
                    rhs_str = f"({rhs_str})"
                return f"{lhs_str} ** {rhs_str}"
            case CCPPStringLiteralExprOp():
                # Fortran escapes an embedded single quote by doubling it
                # inside a '...'-delimited literal.
                escaped = op.text.data.replace("'", "''")
                return f"'{escaped}'"
            case CCPPVarRefExprOp():
                return op.var_name.data
            case CCPPValueExprOp():
                return self._render_value(op.value)
            case CCPPExprTextLiteralOp():
                text = op.prefix.data + self._render_expr(op.expr.block.last_op) + op.suffix.data
                escaped = text.replace("'", "''")
                return f"'{escaped}'"
            case CCPPMetadataLiteralExprOp():
                return op.text.data
            case CCPPNullPointerExprOp():
                return "null()"
            case CCPPMethodCallExprOp():
                base_str = self._render_base_expr(op.base)
                args = ", ".join(self._render_expr(r.block.last_op) for r in op.args)
                return f"{base_str}%{op.method.data}({args})"
            case CCPPStringConcatExprOp():
                pieces = [self._render_expr(r.block.last_op) for r in op.pieces]
                return " // ".join(pieces)
            case CCPPMemberAccessExprOp():
                base_str = self._render_base_expr(op.base)
                return f"{base_str}%{op.member.data}"
            case CCPPIndexExprOp():
                base_str = self._render_base_expr(op.base)
                idx_strs = [self._render_index_piece(r.block.last_op) for r in op.indices]
                return f"{base_str}({', '.join(idx_strs)})"
            case CCPPCallExprOp():
                pos = [self._render_expr(r.block.last_op) for r in op.args]
                kw = [self._render_expr(r.block.last_op) for r in op.kwargs]
                return f"{op.callee.data}({', '.join(pos + kw)})"
            case CCPPKeywordArgExprOp():
                value_op = op.value.block.last_op
                return f"{op.arg_name.data}={self._render_expr(value_op)}"
            case CCPPArrayConstructorExprOp():
                elems = [self._render_expr(r.block.last_op) for r in op.elements]
                prefix = (
                    f"{self.mlir_type_to_ftn_type(op.elem_type)} :: "
                    if op.elem_type is not None else ""
                )
                # One element per continuation line: the elements are often
                # long string literals (cam_model_const_stdnames), and the
                # automatic continuation (_write_with_continuation) can only
                # split at a comma within the first _MAX_LINE_LEN columns.
                sep = ", &\n      "
                return f"[ {prefix}{sep.join(elems)} ]"
            case _:
                raise AssertionError(f"Unhandled op in print_expr: {type(op)}")

    def _host_ref_base(self, op) -> str:
        """A HostVarRefOp's reference without the leaf's subscripts:
        var_name, var_name(index_expr), then %member for each member."""
        index_expr = op.attributes.get("index_expr")
        base = op.var_name.data
        if index_expr is not None:
            base = f"{base}({index_expr.data})"
        if op.member_path is not None:
            base = "%".join([base, *(m.data for m in op.member_path.data)])
        return base

    def _subscripted(self, val: SSAValue) -> tuple[str, list] | None:
        """(base, [(is_range, text), ...]) for a value whose reference ends
        in subscripts -- a DDT member with subscripts (HostVarRefOp) or an
        array section (RankReducingSliceOp) -- else None.

        A section of an already-subscripted value merges into its
        subscripts instead of adding a second set of parentheses: each new
        subscript, in order, replaces the next range-shaped one (``:`` or
        ``lo:hi``), and a fixed index stays in place. Three real shapes
        reach this: a DDT member with a constituent index
        (``q(:, :, index_qv)`` sliced to
        ``q(col_start:col_end, 1:pver, index_qv)``), a cap variable's
        whole-array section (``lc_qv(:, :)``, a CapVarRefOp), and a section
        of a section (suite_cap.py's _build_promoted_call_ops).
        """
        owner = val.owner
        if isa(owner, CCPPHostVarRefOp):
            if not owner.member_subscripts:
                return None
            subs = [r.block.last_op for r in owner.member_subscripts]
            return self._host_ref_base(owner), self._index_pieces(subs)
        if isa(owner, CCPPCapVarRefOp) and owner.target is not None:
            # A cap variable's whole-array section, e.g. lc_qv(:, :).
            target = owner.target.block.last_op
            if not isa(target, CCPPIndexExprOp):
                return None
            return self._render_base_expr(target.base), self._index_pieces(
                [r.block.last_op for r in target.indices]
            )
        if not isa(owner, CCPPRankReducingSliceOp):
            return None
        r_lowers = iter(owner.range_lowers)
        r_uppers = iter(owner.range_uppers)
        scalars = iter(owner.scalar_indices)
        new = []
        for ch in owner.dim_pattern.data:
            if ch == "R":
                lo = self._value_to_expr_str(next(r_lowers))
                hi = self._value_to_expr_str(next(r_uppers))
                new.append((True, f"{lo}:{hi}"))
            else:  # 'S'
                new.append((False, self._get_variable_name_for(next(scalars))))
        source = self._subscripted(owner.source)
        if source is None:
            return self._value_to_expr_str(owner.source), new
        base, existing = source
        replacements = iter(new)
        merged = [next(replacements, sub) if sub[0] else sub for sub in existing]
        return base, merged

    def _index_pieces(self, subs: list) -> list:
        """(is_range, text) for each subscript op."""
        return [(isa(sub, CCPPSliceExprOp), self._render_index_piece(sub)) for sub in subs]

    @staticmethod
    def _subscripted_text(base: str, subscripts: list) -> str:
        return f"{base}({', '.join(text for _is_range, text in subscripts)})"

    def _render_index_piece(self, op: Operation) -> str:
        """Render one child of an IndexExprOp.indices region: either a
        plain expression op, or a SliceExprOp (Fortran range syntax)."""
        if isa(op, CCPPSliceExprOp):
            lower = self._render_base_expr(op.lower) if op.lower is not None else ""
            upper = self._render_base_expr(op.upper) if op.upper is not None else ""
            stride = f":{self._render_base_expr(op.stride)}" if op.stride is not None else ""
            return f"{lower}:{upper}{stride}"
        return self._render_expr(op)

    def _print_guarded_alloc_and_assign(
        self, src_name: str, result_name: str, sizes: list, is_optional_array: bool,
        assign_expr: str | None = None,
    ) -> None:
        """Print a reentry-safe (deallocate-if-allocated) allocate for
        result_name, sized by `sizes`, followed by an optional assignment --
        the whole block gated on `if (present(src_name))` when
        is_optional_array is True.

        Shared by CCPPKindCastOp/CCPPUnitConvertOp/CCPPVerticalFlipOp's own
        array-case printing. RowMajorConvertOp is deliberately NOT included: its rank/sizes come
        from an explicit `dim_exprs` attribute, not the result type's own
        shape the way the other three derive theirs from
        `self._ftn_dim_suffix`, and its source is always a host module-var
        reference (`HostVarRefOp`), which can never be an optional dummy
        argument (only block args are, see `optional_args`), so it needs
        no present() gate at all.

        assign_expr=None skips the assignment line entirely (UnitConvertOp's
        own intent(out) case, where to_expr is empty and there is nothing to
        pre-copy).

        The reentry-safe deallocate-before-allocate guards against a
        subcycle loop re-invoking this same conversion with no intervening
        deallocate -- see the original per-case comments this replaced for
        the full reasoning.
        """
        sizes_str = ", ".join(sizes)

        def _body(printer) -> None:
            printer.print(f"if (allocated({result_name})) deallocate({result_name})")
            printer.print(f"allocate({result_name}({sizes_str}))")
            if assign_expr is not None:
                printer.print(assign_expr)

        if is_optional_array:
            self.print(f"if (present({src_name})) then")
            with self.descend() as inner:
                _body(inner)
            self.print("end if")
        else:
            _body(self)

    def _print_guarded_writeback_and_dealloc(
        self, dest_name: str, conv_name: str, is_optional_array: bool,
        assign_expr: str, has_dims: bool = True,
    ) -> None:
        """Print a write-back assignment followed by deallocate(conv_name),
        gated on `if (present(dest_name))` when is_optional_array is True
        (else unconditional, with the deallocate only when has_dims -- a
        scalar write-back has nothing allocated to free).

        Shared by CCPPKindWriteBackOp/CCPPUnitWriteBackOp/
        CCPPVerticalFlipWriteBackOp's own write-back printing -- see
        _print_guarded_alloc_and_assign's own docstring for why
        RowMajorWriteBackOp is deliberately excluded.
        """
        if is_optional_array:
            self.print(f"if (present({dest_name})) then")
            with self.descend() as inner:
                inner.print(assign_expr)
                inner.print(f"deallocate({conv_name})")
            self.print("end if")
        else:
            self.print(assign_expr)
            if has_dims:
                self.print(f"deallocate({conv_name})")

    def print_op(self, op: Operation):
        """Dispatch an MLIR operation to the appropriate Fortran printer.

        Operations that produce values but emit no Fortran statement (e.g.
        address-of, load) register names in the variables dict and return
        silently.  Operations that have no Fortran equivalent (e.g. alloca,
        global declarations, yield) are skipped with a pass.
        """
        match op:
            case builtin.ModuleOp(sym_name=name, body=bdy):
                self._print_module(name, bdy)
            case memref.AllocaOp():
                pass  # Variable registration is handled up-front in _print_fn
            case llvm.GlobalOp():
                pass  # Module-level globals are declared in _print_module preamble
            case llvm.AddressOfOp():
                name = op.global_name.root_reference.data
                if "ccpp_instance_ref" in op.attributes:
                    # Real capgen-v1's multi-instance model
                    # ("instances/instances_advection" entry): ccpp_instance_ref
                    # holds
                    # the plain local Fortran name of this call's own
                    # instance_number-standard-name scalar arg -- the
                    # global (ccpp_suite_state) is itself dimensioned by
                    # number_of_instances for such a suite (see suite_cap.py's
                    # _build_state_globals), so indexing it directly by that
                    # bare scalar is the whole story; no member access needed.
                    instance_var = op.attributes["ccpp_instance_ref"].data
                    name = f"{name}({instance_var})"
                self.variables[op.result] = name
            case llvm.LoadOp():
                # Propagate the pointer's name to the loaded value
                self.variables[op.dereferenced_value] = self._get_variable_name_for(
                    op.ptr
                )
            case llvm.StoreOp():
                if isa(op.ptr.type, MemRefType):
                    # Storing a loaded string value into a memref<?xi8> buffer:
                    # suppress output here — the Fortran assignment is emitted by
                    # the memref.StoreOp that places the buffer into the allocatable.
                    pass
                else:
                    # Emit a Fortran assignment from the source value to the destination
                    dst_name = self._get_variable_name_for(op.ptr)
                    src_name = self._get_variable_name_for(op.value)
                    self.print(f"{dst_name} = {src_name}")
            case func.FuncOp(sym_name=name, body=bdy, function_type=ftyp):
                # Skip external declarations; only print subroutine definitions
                if not op.is_declaration:
                    self._print_fn(
                        name, bdy, ftyp, bind_c="bind_c" in op.attributes, fn_op=op,
                    )
            case func.CallOp(callee=tgt, arguments=args, res=results):
                self._print_call(tgt, args, results)
            case CCPPKeywordCallOp():
                self._print_kw_call(op)
            case scf.IfOp(
                cond=conditional, true_region=true_bdy, false_region=false_bdy
            ):
                self._print_if(conditional, true_bdy, false_bdy)
            case memref.AllocOp():
                pass  # Heap allocations are emitted via the StoreOp that uses the result
            case CCPPKindDefOp():
                pass  # Kind definitions are declared in _print_module preamble
            case CCPPTrimOp():
                pass  # Used only as a sub-expression; printed inline by print_expr
            case CCPPSetStringOp():
                # Register the source global name as the variable name for dest
                # so that the memref.StoreOp into the allocatable can find it.
                src_name = self._get_variable_name_for(op.src)
                self.variables[op.dest] = src_name
            case memref.StoreOp(value=val, memref=arr, indices=idxs):
                if self._is_allocatable_char(arr.type) and isa(
                    val.owner, memref.AllocOp
                ):
                    # Storing a memref<?xi8> (string buffer) into memref<memref<?xi8>>
                    # (the allocatable out arg).  On the first store emit
                    # allocate(arr(N)) where N is the total number of such stores in
                    # this block; then emit arr(i) = string_src for each store.
                    arr_name = self._get_variable_name_for(arr)
                    string_src = self.variables.get(val)
                    key = id(arr)
                    if key not in self._allocatable_store_indices:
                        total = sum(
                            1
                            for sibling in op.parent.ops
                            if isa(sibling, memref.StoreOp)
                            and sibling.memref is arr
                            and isa(sibling.value.owner, memref.AllocOp)
                        )
                        self._allocatable_store_indices[key] = (1, total)
                        self.print(f"allocate({arr_name}({total}))")
                    idx, total = self._allocatable_store_indices[key]
                    self._allocatable_store_indices[key] = (idx + 1, total)
                    if string_src is not None:
                        self.print(f"{arr_name}({idx}) = {string_src}")
                else:
                    arr_name = self._get_variable_name_for(arr)
                    idx_args = ", ".join(map(self._get_variable_name_for, idxs))
                    if len(idx_args) > 0:
                        self.print(f"{arr_name}[{idx_args}] = ", end="")
                    else:
                        self.print(f"{arr_name} = ", end="")
                    self.print_expr(val.owner)
                    self.print("")
            case CCPPCapVarRefOp():
                # Register the cap module variable reference — no Fortran code emitted
                self.variables[op.res] = self._target_text(op, op.var_name)
            case CCPPHostVarRefOp():
                # Register the host variable reference for the result -- no
                # Fortran emitted (see HostVarRefOp).
                parts = self._subscripted(op.res)
                self.variables[op.res] = (
                    self._subscripted_text(*parts) if parts is not None
                    else self._host_ref_base(op)
                )
            case CCPPClearStringOp():
                dest_name = self._get_variable_name_for(op.dest)
                self.print(f"{dest_name} = ''")
            case CCPPWriteErrMsgOp():
                dest_name = self._get_variable_name_for(op.dest)
                self.print(f"write({dest_name}, '(3a)') \"{op.prefix.data}\", ", end="")
                self.print_expr(op.var.owner)
                self.print(f', "{op.suffix.data}"', use_prefix=False)
            case CCPPWriteStmtOp():
                dest = self._render_expr(op.dest.block.last_op)
                items = [self._render_expr(r.block.last_op) for r in op.items]
                self.print(f"write({dest}, '({len(items)}a)') {', '.join(items)}")
            case CCPPPrintStmtOp():
                items = [self._render_expr(r.block.last_op) for r in op.items]
                self.print(f"write(*,*) {', '.join(items)}")
            case builtin.UnrealizedConversionCastOp():
                # Type annotation cast — transparent to Fortran; map each result
                # to the same variable name as the corresponding input operand.
                for result, operand in zip(op.results, op.inputs):
                    self.variables[result] = self._get_variable_name_for(operand)
            case CCPPAccDataBeginOp():
                copy_names    = [self._get_variable_name_for(v) for v in op.copy_arrays]
                copyin_names  = [self._get_variable_name_for(v) for v in op.copyin_arrays]
                copyout_names = [self._get_variable_name_for(v) for v in op.copyout_arrays]
                present_names = [self._get_variable_name_for(v) for v in op.present_arrays]
                self.print("#ifdef USE_GPU", use_prefix=False)
                if not copy_names and not copyin_names and not copyout_names and not present_names:
                    self.print("!$acc data")
                else:
                    self._emit_acc_directive("data", [
                        ("copy",    copy_names),
                        ("copyin",  copyin_names),
                        ("copyout", copyout_names),
                        ("present", present_names),
                    ])
                self.print("#endif", use_prefix=False)
            case CCPPAccDataEndOp():
                self.print("#ifdef USE_GPU", use_prefix=False)
                self.print("!$acc end data")
                self.print("#endif", use_prefix=False)
            case CCPPAccEnterDataOp():
                copyin_names = [self._get_variable_name_for(v) for v in op.copyin_arrays]
                create_names = [self._get_variable_name_for(v) for v in op.create_arrays]
                self.print("#ifdef USE_GPU", use_prefix=False)
                self._emit_acc_directive("enter data", [
                    ("copyin", copyin_names),
                    ("create", create_names),
                ])
                self.print("#endif", use_prefix=False)
            case CCPPAccExitDataOp():
                copyout_names = [self._get_variable_name_for(v) for v in op.copyout_arrays]
                delete_names  = [self._get_variable_name_for(v) for v in op.delete_arrays]
                self.print("#ifdef USE_GPU", use_prefix=False)
                self._emit_acc_directive("exit data", [
                    ("copyout", copyout_names),
                    ("delete",  delete_names),
                ])
                self.print("#endif", use_prefix=False)
            case CCPPModuleVarOp():
                pass  # declared in _print_module preamble, not here
            case CCPPDerivedTypeDefOp() | CCPPDdtComponentDeclOp():
                pass  # declared in _print_module preamble, not here (see ModuleVarOp)
            case CCPPLazyAllocOp():
                vname = op.var_name.data
                dim_names = [self._get_variable_name_for(v) for v in op.dim_vars]
                dim_str = ", ".join(dim_names)
                if op.init_value_region is not None:
                    init_value_str = self._render_expr(op.init_value_region.block.last_op)
                else:
                    init_value_str = None
                _is_run_local = (
                    op.is_run_local is not None
                    and bool(op.is_run_local.value.data)
                )
                if _is_run_local:
                    # Run-local var: unconditional allocate each call (no lazy guard).
                    # Declared as a local allocatable in the subroutine spec section;
                    # a matching SafeDeallocOp is injected at end of the subroutine.
                    self.print(f"allocate({vname}({dim_str}))")
                    if init_value_str is not None:
                        self.print(f"{vname} = {init_value_str}")
                else:
                    _device = (op.needs_device_residency is not None
                               and bool(op.needs_device_residency.value.data))
                    if op.realloc_on_resize is not None and bool(op.realloc_on_resize.value.data):
                        self.print(f"if (allocated({vname})) then")
                        with self.descend() as inner:
                            inner.print(f"if (any(shape({vname}) /= [{dim_str}])) then")
                            with inner.descend() as body:
                                if _device:
                                    body.print("#ifdef USE_GPU", use_prefix=False)
                                    body.print(f"!$acc exit data delete({vname})")
                                    body.print("#endif", use_prefix=False)
                                body.print(f"deallocate({vname})")
                            inner.print("end if")
                        self.print("end if")
                    self.print(f"if (.not. allocated({vname})) then")
                    with self.descend() as inner:
                        inner.print(f"allocate({vname}({dim_str}))")
                        if init_value_str is not None:
                            inner.print(
                                f"{vname} = {init_value_str}"
                            )
                        if _device:
                            inner.print("#ifdef USE_GPU", use_prefix=False)
                            inner.print(f"!$acc enter data create({vname})")
                            inner.print("#endif", use_prefix=False)
                    self.print("end if")
            case CCPPSafeDeallocOp():
                vname = self._target_text(op, op.var_name)
                self.print(f"if (allocated({vname})) deallocate({vname})")
            case CCPPNullifyPointerOp():
                ptr = self._target_text(op, op.ptr_name)
                if op.if_associated is not None:
                    self.print(f"if (associated({ptr})) nullify({ptr})")
                else:
                    self.print(f"nullify({ptr})")
            case CCPPAllocateOp():
                dims = ", ".join(self._render_expr(r.block.last_op) for r in op.dims_region)
                name = self._target_text(op, op.var_name)
                target = f"{name}({dims})" if dims else name
                stat = f", stat={op.stat_var.data}" if op.stat_var is not None else ""
                self.print(f"allocate({target}{stat})")
            case CCPPZeroFillOp():
                self.print(f"{self._target_text(op, op.var_name)} = 0.0_kind_phys")
            case CCPPPointerAssignOp():
                rhs_str = self._render_expr(op.rhs_expr_region.block.last_op)
                self.print(f"{self._target_text(op, op.ptr_name)} => {rhs_str}")
            case CCPPAssignOp():
                lhs = self._render_expr(op.lhs.block.last_op)
                rhs = self._render_expr(op.rhs.block.last_op)
                self.print(f"{lhs} = {rhs}")
            case CCPPDdtMethodCallOp():
                obj_str = self._render_expr(op.obj_expr_region.block.last_op)
                all_args = [
                    self._render_expr(r.block.last_op)
                    for r in (*op.args_region, *op.kwargs_region)
                ]
                self.print(f"call {obj_str}%{op.method.data}({', '.join(all_args)})")
            case CCPPErrorGuardOp():
                errflg_var = op.errflg_var.data if op.errflg_var is not None else "errflg"
                errmsg_var = op.errmsg_var.data if op.errmsg_var is not None else "errmsg"
                cond_root = op.condition_region.block.last_op
                cond_str = self._render_expr(cond_root)
                # Fortran's .not. binds TIGHTER than .and./.or./
                # .eqv./.neqv. (but looser than relational/concat/
                # arithmetic) -- "if (.not. a .or. b)" parses as
                # "(.not. a) .or. b", not the intended ".not. (a .or.
                # b)", silently inverting the guard for any compound
                # condition at this level. A bare comparison/call/
                # var-ref needs no parens (those bind tighter than
                # .not. already). Not yet exercised by any real
                # constituent_cap.py call site (all use a single
                # CallExprOp today), but a real bug in the general
                # mechanism (Copilot PR #109 review, 2026-10-05).
                if expr_precedence.level_of(cond_root) < expr_precedence.LEVEL_CMP:
                    cond_str = f"({cond_str})"
                self.print(f"if (.not. {cond_str}) then")
                with self.descend() as inner:
                    inner.print(f"{errflg_var} = 1")
                    inner.print(f"{errmsg_var} = '{op.errmsg_text.data}'")
                    inner.print("return")
                self.print("end if")
            case CCPPDoLoopOp():
                upper = self._render_expr(op.upper.block.last_op)
                self.print(f"do {op.loop_var.data} = 1, {upper}")
                with self.descend() as inner:
                    inner.print_block(op.body.block)
                self.print("end do")
            case CCPPScopedBlockOp():
                self.print("block")
                with self.descend() as blk:
                    for local in op.body.block.ops:
                        if isa(local, memref.AllocaOp):
                            name = blk._get_variable_name_for(
                                local.memref,
                                hint=recorded_local_name(local) or local.memref.name_hint,
                            )
                            blk.print(ftnPrintContext._local_decl_line(blk, local, name))
                    blk.print_block(op.body.block)
                self.print("end block")
            case CCPPCToFortranStringCopyOp():
                c_var = op.c_var.data
                f_var = op.f_var.data
                self.print(f"{f_var} = ' '")
                self.print(f"do i = 1, len({f_var})")
                with self.descend() as inner:
                    inner.print(f"if ({c_var}(i) == c_null_char) exit")
                    inner.print(f"{f_var}(i:i) = {c_var}(i)")
                self.print("end do")
            case CCPPFortranToCStringCopyOp():
                c_var = op.c_var.data
                f_var = op.f_var.data
                self.print(f"do i = 1, len_trim({f_var})")
                with self.descend() as inner:
                    inner.print(f"{c_var}(i) = {f_var}(i:i)")
                self.print("end do")
                self.print(f"{c_var}(len_trim({f_var})+1) = c_null_char")
            case CCPPConstituentApiOp():
                self.print_block(op.body.block)
            case CCPPCamDirectCallOp():
                args = ", ".join(self._render_expr(r.block.last_op) for r in op.arg_exprs)
                self.print(f"call {op.callee.data}({args})")
            case CCPPCallStatementOp():
                call_args = [self._render_expr(r.block.last_op) for r in op.arg_exprs]
                lines = wrap_paren_list(
                    f"call {op.callee.data}(", call_args, ")", 80, "    "
                )
                for line in lines:
                    self.print(line)
            case CCPPClearErrStateOp():
                self.print(f"{op.errcode_var.data} = 0")
                self.print(f"{op.errmsg_var.data} = ''")
            case CCPPErrorPropagateOp():
                ev = op.errcode_var.data
                self.print(f"if ({ev} /= 0) return")
            case CCPPReturnStmtOp():
                if op.value is not None:
                    raise NotImplementedError(
                        "print_ftn: a Fortran subroutine returns no value"
                    )
                if op.condition is None:
                    self.print("return")
                else:
                    cond = self._render_expr(op.condition.block.last_op)
                    self.print(f"if ({cond}) return")
            case CCPPErrorExitOp():
                if op.errflg_var is not None:
                    self.print(f"{op.errflg_var.data} = 1")
                if op.errmsg_text is not None:
                    message = f"'{op.errmsg_text.data}'"
                else:
                    message = self._render_expr(op.message.block.last_op)
                self.print(f"{op.errmsg_var.data} = {message}")
                self.print("return")
            case CCPPCamSuiteDispatchOp():
                dispatcher = op.dispatcher_fn.data
                wrapper    = op.wrapper_fn.data
                ev         = op.errcode_var.data
                em         = op.errmsg_var.data
                other_args = [self._render_expr(r.block.last_op) for r in op.arg_exprs]
                part_at    = op.suite_part_index.value.data
                first = True
                for inner in op.suite_groups.data:
                    attrs    = inner.data
                    sn       = attrs[0].data
                    groups   = [a.data for a in attrs[1:]]
                    kw = "if" if first else "else if"
                    first = False
                    self.print(f"{kw} (trim(suite_name) == '{sn}') then")
                    with self.descend() as blk:
                        for grp in groups:
                            args = [*other_args[:part_at], f"'{grp}'", *other_args[part_at:]]
                            blk.print(f"call {dispatcher}({', '.join(args)})")
                            blk.print(f"if ({ev} /= 0) return")
                if not first:
                    self.print("else")
                    with self.descend() as blk:
                        blk.print(
                            f"write({em}, '(3a)') '{wrapper}: no suite named ', "
                            f"trim(suite_name), ' found'"
                        )
                        blk.print(f"{ev} = 1")
                    self.print("end if")
            case CCPPPresentCheckOp():
                var_name = op.var_name.data
                self.print(f"if (present({var_name})) then")
                with self.descend() as inner:
                    inner.print_block(op.with_body.blocks[0])
                self.print("else")
                with self.descend() as inner:
                    inner.print_block(op.without_body.blocks[0])
                self.print("end if")
            case CCPPActiveCheckOp():
                condition = self._render_expr(op.condition.block.last_op)
                self.print(f"if ({condition}) then")
                with self.descend() as inner:
                    inner.print_block(op.with_body.blocks[0])
                self.print("else")
                with self.descend() as inner:
                    inner.print_block(op.without_body.blocks[0])
                self.print("end if")
            case CCPPPromotionLoopOp():
                loop_name  = self._get_variable_name_for(op.loop_var)
                upper_name = self._get_variable_name_for(op.upper_bound)
                self.print(f"do {loop_name} = 1, {upper_name}")
                with self.descend() as inner:
                    inner.print_block(op.body.blocks[0])
                self.print("end do")
            case CCPPSubcycleLoopOp():
                loop_name = self._get_variable_name_for(op.loop_var)
                if op.loop_count is not None:
                    loop_count_str = op.loop_count.data
                else:
                    loop_count_str = self._render_expr(op.loop_count_region.block.last_op)
                self.print(f"do {loop_name} = 1, {loop_count_str}")
                with self.descend() as inner:
                    inner.print_block(op.body.blocks[0])
                self.print("end do")
            case CCPPCHostCapOp():
                # Complete standalone Fortran module — emit ftn_body verbatim.
                # Normally emitted via print_to_ftn at the top level, but handled
                # here too in case the op appears inside a module body.
                self.print_block(op.ftn_body.block)
            case CCPPRankReducingSliceOp():
                # Register the Fortran array-section expression for the
                # result, e.g. "RS" -> source(lower:upper, scalar); see
                # _subscripted for how it merges into a source that is
                # already subscripted.
                self.variables[op.res] = self._subscripted_text(*self._subscripted(op.res))
            case CCPPAccParallelOp():
                present_names = [self._get_variable_name_for(v) for v in op.present_arrays]
                if present_names:
                    self._emit_acc_directive("parallel", [("present", present_names)])
                else:
                    self.print("!$acc parallel")
                self.print_block(op.body.block)
                self.print("!$acc end parallel")
            case CCPPAccUpdateSelfOp():
                var_names = [self._get_variable_name_for(v) for v in op.arrays]
                self._emit_acc_directive("update", [("self", var_names)])
            case CCPPAccUpdateDeviceOp():
                var_names = [self._get_variable_name_for(v) for v in op.arrays]
                self._emit_acc_directive("update", [("device", var_names)])
            case CCPPOmpTargetDataBeginOp():
                tofrom_names = [self._get_variable_name_for(v) for v in op.tofrom_arrays]
                alloc_names  = [self._get_variable_name_for(v) for v in op.alloc_arrays]
                if not tofrom_names and not alloc_names:
                    self.print("!$omp target data")
                else:
                    self._emit_omp_directive("target data", [
                        ("map(tofrom:", tofrom_names, ""),
                        ("map(alloc:",  alloc_names,  ""),
                    ])
            case CCPPOmpTargetDataEndOp():
                self.print("!$omp end target data")
            case CCPPOmpTargetUpdateFromOp():
                var_names = [self._get_variable_name_for(v) for v in op.arrays]
                self._emit_omp_directive("target update", [("from", var_names)])
            case CCPPOmpTargetUpdateToOp():
                var_names = [self._get_variable_name_for(v) for v in op.arrays]
                self._emit_omp_directive("target update", [("to", var_names)])
            case CCPPOmpTargetEnterDataOp():
                to_names    = [self._get_variable_name_for(v) for v in op.to_arrays]
                alloc_names = [self._get_variable_name_for(v) for v in op.alloc_arrays]
                self._emit_omp_directive("target enter data", [
                    ("map(to:",    to_names,    ""),
                    ("map(alloc:", alloc_names, ""),
                ])
            case CCPPOmpTargetExitDataOp():
                from_names    = [self._get_variable_name_for(v) for v in op.from_arrays]
                release_names = [self._get_variable_name_for(v) for v in op.release_arrays]
                self._emit_omp_directive("target exit data", [
                    ("map(from:",    from_names,    ""),
                    ("map(release:", release_names, ""),
                ])
            case CCPPKindCastOp():
                src_name    = self._get_variable_name_for(op.source)
                result_name = self._get_variable_name_for(op.res)
                target_kind = op.target_kind.data
                dim_suffix = self._ftn_dim_suffix(op.res.type)
                if dim_suffix:
                    # mold= requires matching kind; use explicit size() dims instead
                    rank = dim_suffix.count(":")
                    sizes = [f"size({src_name}, {i+1})" for i in range(rank)]
                    # An optional array dummy that the caller genuinely did
                    # not pass has no bounds to call size() on at all --
                    # gate the whole allocate+convert on present() so this
                    # only runs when the source is actually there.
                    is_optional_array = op.source in self.optional_args
                    self._print_guarded_alloc_and_assign(
                        src_name, result_name, sizes, is_optional_array,
                        assign_expr=f"{result_name} = real({src_name}, kind={target_kind})",
                    )
                else:
                    self.print(f"{result_name} = real({src_name}, kind={target_kind})")
            case CCPPKindWriteBackOp():
                conv_name = self._get_variable_name_for(op.conv_result)
                dest_name = self._get_variable_name_for(op.original_dest)
                orig_kind = op.original_kind.data
                dim_suffix = self._ftn_dim_suffix(op.conv_result.type)
                # Mirror the presence-gating above: an absent optional array
                # was never allocated/converted in the first place, so there
                # is nothing to write back or deallocate either.
                is_optional_array = bool(
                    dim_suffix and op.original_dest in self.optional_args
                )
                self._print_guarded_writeback_and_dealloc(
                    dest_name, conv_name, is_optional_array,
                    assign_expr=f"{dest_name} = real({conv_name}, kind={orig_kind})",
                    has_dims=bool(dim_suffix),
                )
            case CCPPUnitConvertOp():
                # Local-copy pre-conversion (host units → scheme units).
                # Allocates a local temp and copies the converted value into it;
                # the host's array is never modified.
                src_name    = self._get_variable_name_for(op.source)
                result_name = self._get_variable_name_for(op.res)
                scheme_kind = self._elem_kind_name(op.res.type)
                to_expr = self._unit_conversion_text(op, scheme_kind)
                dim_suffix = self._ftn_dim_suffix(op.res.type)
                if dim_suffix:
                    rank = dim_suffix.count(":")
                    sizes = [f"size({src_name}, {i+1})" for i in range(rank)]
                    # See CCPPKindCastOp's own comment above: an absent
                    # optional array has no bounds to call size() on, so
                    # gate the whole allocate(+copy) on present().
                    is_optional_array = op.source in self.optional_args
                    self._print_guarded_alloc_and_assign(
                        src_name, result_name, sizes, is_optional_array,
                        assign_expr=f"{result_name} = {src_name} {to_expr}" if to_expr else None,
                    )
                elif to_expr:
                    self.print(f"{result_name} = {src_name} {to_expr}")
                # intent(out): no pre-copy — scheme fills the local from scratch
            case CCPPUnitWriteBackOp():
                # Post-conversion: write local temp back to host in original units.
                conv_name = self._get_variable_name_for(op.conv_result)
                dest_name = self._get_variable_name_for(op.original_dest)
                host_kind = self._elem_kind_name(op.original_dest.type)
                to_expr = self._unit_conversion_text(op, host_kind)
                dim_suffix = self._ftn_dim_suffix(op.conv_result.type)
                # Mirror CCPPUnitConvertOp's own presence gating: an absent
                # optional array was never allocated/converted, so there is
                # nothing to write back or deallocate either.
                is_optional_array = bool(
                    dim_suffix and op.original_dest in self.optional_args
                )
                self._print_guarded_writeback_and_dealloc(
                    dest_name, conv_name, is_optional_array,
                    assign_expr=f"{dest_name} = {conv_name} {to_expr}",
                    has_dims=bool(dim_suffix),
                )
            case CCPPVerticalFlipOp():
                # Local-copy vertical flip: reverse an array section along the
                # vertical dimension into a local temp; the host's array is
                # never modified. Always array-shaped (top_at_one is only
                # ever meaningful for an array with a vertical dimension),
                # unlike CCPPKindCastOp/CCPPUnitConvertOp -- no scalar branch.
                src_name    = self._get_variable_name_for(op.source)
                result_name = self._get_variable_name_for(op.res)
                vert_dim = op.vertical_dim.value.data
                dim_suffix = self._ftn_dim_suffix(op.res.type)
                rank = dim_suffix.count(":")
                sizes = [f"size({src_name}, {i + 1})" for i in range(rank)]
                sections = [
                    f"size({src_name}, {vert_dim}):1:-1" if i + 1 == vert_dim else ":"
                    for i in range(rank)
                ]
                # See CCPPKindCastOp's own comment above: an absent optional
                # array has no bounds to call size() on, so gate the whole
                # allocate+flip on present() -- this arg only ever reaches
                # this op via suite_cap.py's _apply_divergent_marshaling
                # (a cross-scheme divergent standard_name with top_at_one
                # set), which doesn't itself exclude optional args, so the
                # gate is a real (if not yet exercised by any current
                # example) latent-crash guard, not just defensive symmetry.
                is_optional_array = op.source in self.optional_args
                self._print_guarded_alloc_and_assign(
                    src_name, result_name, sizes, is_optional_array,
                    assign_expr=f"{result_name} = {src_name}({', '.join(sections)})",
                )
            case CCPPVerticalFlipWriteBackOp():
                # Post-flip: write the local temp back to the host, reversed
                # along the same vertical dimension (a second reversal
                # restores the original order).
                conv_name = self._get_variable_name_for(op.conv_result)
                dest_name = self._get_variable_name_for(op.original_dest)
                vert_dim = op.vertical_dim.value.data
                rank = self._ftn_dim_suffix(op.conv_result.type).count(":")
                sections = [
                    f"size({conv_name}, {vert_dim}):1:-1" if i + 1 == vert_dim else ":"
                    for i in range(rank)
                ]
                # See CCPPVerticalFlipOp's own comment above for why this
                # gate matters despite no current example exercising it.
                is_optional_array = op.original_dest in self.optional_args
                self._print_guarded_writeback_and_dealloc(
                    dest_name, conv_name, is_optional_array,
                    assign_expr=f"{dest_name} = {conv_name}({', '.join(sections)})",
                )
            case CCPPRowMajorConvertOp():
                # Forward transpose: row-major host → column-major local temp.
                src_name    = self._get_variable_name_for(op.source)
                result_name = self._get_variable_name_for(op.res)
                rank = len(op.dim_exprs.data)
                dims = [e.data for e in op.dim_exprs.data]
                dims_str  = ", ".join(dims)
                order_str = ", ".join(str(rank - i) for i in range(rank))
                # See CCPPKindCastOp's own comment above: guards against
                # re-entry (e.g. a subcycle loop) with no intervening
                # deallocate when this value is pure intent=in (no
                # write-back, so the *WriteBackOp case's own deallocate
                # never runs at all).
                self.print(f"if (allocated({result_name})) deallocate({result_name})")
                self.print(f"allocate({result_name}({dims_str}))")
                self.print(f"{result_name} = reshape({src_name}, [{dims_str}], order=[{order_str}])")
            case CCPPRowMajorWriteBackOp():
                # Reverse transpose: column-major local temp → row-major host.
                local_name = self._get_variable_name_for(op.local_val)
                dest_name  = self._get_variable_name_for(op.host_var)
                rank = len(op.dim_exprs.data)
                dims = [e.data for e in op.dim_exprs.data]
                rev_dims_str = ", ".join(reversed(dims))
                order_str    = ", ".join(str(rank - i) for i in range(rank))
                self.print(f"{dest_name} = reshape({local_name}, [{rev_dims_str}], order=[{order_str}])")
                self.print(f"deallocate({local_name})")
    # ISO_FORTRAN_ENV named constants recognised as kind values
    _ISO_FORTRAN_ENV_KINDS: frozenset[str] = frozenset(
        {
            "REAL32",
            "REAL64",
            "REAL128",
            "INT8",
            "INT16",
            "INT32",
            "INT64",
        }
    )

    def _print_module(self, module_name, body):
        """Print a builtin.ModuleOp as a Fortran module block.

        The preamble contains:
          - use ccpp_kinds (skipped for the ccpp_kinds module itself)
          - use iso_fortran_env if any KindDefOp values are ISO constants
          - use <module>, only: <name> lines for external declarations
          - implicit none / private defaults
          - integer, parameter declarations for every KindDefOp
          - character variable declarations for every llvm.GlobalOp
          - a public :: line for each subroutine definition marked public
        The CONTAINS section follows only when subroutine definitions are present.
        """
        assert module_name is not None
        is_kinds_module = module_name.data == "ccpp_kinds"

        self.print(f"module {module_name.data}")

        # The ccpp_kinds module must not use itself (circular dependency).
        # Also skipped when no @ccpp_kinds module was generated at all (see
        # has_kinds_module's own docstring) -- otherwise this `use` statement
        # would reference a module that doesn't exist.
        if not is_kinds_module and self.has_kinds_module:
            self.print("\nuse ccpp_kinds", prefix="  ")

        # When any subroutine uses BIND(C), or any C++ scheme is called,
        # import iso_c_binding at module scope.
        if not is_kinds_module:
            has_bind_c = any(
                isa(op, func.FuncOp) and not op.is_declaration
                and "bind_c" in op.attributes
                for op in body.ops
            )
            has_cxx_schemes = any(
                isa(op, func.FuncOp) and op.is_declaration
                and "language" in op.attributes
                for op in body.ops
            )
            if has_bind_c or has_cxx_schemes:
                self.print("use iso_c_binding", prefix="  ")

        # For the ccpp_kinds module, emit ISO_FORTRAN_ENV renames:
        #   use ISO_FORTRAN_ENV, only: kind_phys => REAL64
        # This imports and re-exports each kind under its CCPP name in one step.
        if is_kinds_module:
            iso_renames = ", ".join(
                f"{op.kind_name.data} => {op.kind_value.data}"
                for op in body.ops
                if isa(op, CCPPKindDefOp)
                and op.kind_module.data == "iso_fortran_env"
                and op.kind_value.data in self._ISO_FORTRAN_ENV_KINDS
            )
            if iso_renames:
                self.print(f"use ISO_FORTRAN_ENV, only: {iso_renames}", prefix="  ")

            # Kinds resolved via a real metadata kind_spec (module !=
            # iso_fortran_env) get the same rename-on-import treatment from
            # their own module, grouped and sorted by module name. This is
            # additive: every existing example has kind_module ==
            # "iso_fortran_env" for every kind, so the block above is
            # unaffected and this loop is a no-op for them.
            non_iso_by_module: dict[str, list[str]] = {}
            for op in body.ops:
                if isa(op, CCPPKindDefOp) and op.kind_module.data != "iso_fortran_env":
                    non_iso_by_module.setdefault(op.kind_module.data, []).append(
                        f"{op.kind_name.data} => {op.kind_value.data}"
                    )
            for mod in sorted(non_iso_by_module):
                renames = ", ".join(sorted(non_iso_by_module[mod]))
                self.print(f"use {mod}, only: {renames}", prefix="  ")

        # Emit 'use <module>, only: <name>' lines.  Two sources:
        #   1. External FuncOps with a 'module' attribute (suite cap callees).
        #   2. llvm.GlobalOp stubs with a 'module' attribute (host model vars).
        use_map: dict[str, list[str]] = {}
        for op in body.ops:
            if isa(op, func.FuncOp) and op.is_declaration and "module" in op.attributes:
                if "language" in op.attributes:
                    continue  # C++ scheme — emitted as BIND(C) interface block, not use
                mod = op.attributes["module"].data
                use_map.setdefault(mod, []).append(op.sym_name.data)
            elif isa(op, llvm.GlobalOp) and "module" in op.attributes:
                mod = op.attributes["module"].data
                use_map.setdefault(mod, []).append(op.sym_name.data)
        # Also emit USE statements for CCPP framework DDT types used as
        # function argument types — e.g. ccpp_constituent_properties_t.
        _CCPP_DDT_MODULES = {
            "ccpp_constituent_properties_t": "ccpp_constituent_prop_mod",
            "ccpp_constituent_prop_ptr_t":   "ccpp_constituent_prop_mod",
            "ccpp_t":                        "ccpp_types",
        }
        from xdsl_ccpp.dialects.ccpp_utils import DerivedType as _DerivedType
        for op in body.ops:
            if not isa(op, func.FuncOp):
                continue
            for blk in op.body.blocks:
                for arg in blk.args:
                    if not isa(arg.type, MemRefType):
                        continue
                    elem = cast(MemRefType, arg.type).element_type
                    if not isa(elem, _DerivedType):
                        continue
                    ddt_mod = _CCPP_DDT_MODULES.get(
                        cast(_DerivedType, elem).type_name.data
                    )
                    if ddt_mod:
                        use_map.setdefault(ddt_mod, [])
                        if cast(_DerivedType, elem).type_name.data \
                                not in use_map[ddt_mod]:
                            use_map[ddt_mod].append(
                                cast(_DerivedType, elem).type_name.data
                            )

        for mod, procs in sorted(use_map.items()):
            for proc in sorted(procs):
                self.print(f"use {mod}, only: {proc}", prefix="  ")

        # Emit BIND(C) interface blocks for C++ scheme entry points.
        cxx_fns = [op for op in body.ops
                   if isa(op, func.FuncOp) and op.is_declaration
                   and "language" in op.attributes]
        if cxx_fns:
            self._print_cxx_interface_blocks(cxx_fns)

        self.print("\nimplicit none", prefix="  ")
        self.print("private", prefix="  ")
        self.print("")

        # Emit 'public :: kind_name' for each kind (the rename in the use statement
        # above already brings the name into scope; only visibility needs declaring).
        for op in body.ops:
            if isa(op, CCPPKindDefOp):
                self.print(f"public :: {op.kind_name.data}", prefix="  ")

        # Emit module-level character variable declarations for each LLVM global.
        # Globals with a 'module' attribute are USE-associated (already emitted
        # above as 'use' lines) and must not be re-declared here.
        for op in body.ops:
            if isa(op, llvm.GlobalOp) and "module" not in op.attributes:
                name = op.sym_name.data
                val = op.value.data if isa(op.value, StringAttr) else ""
                is_const = op.constant is not None
                # Derive character length from the LLVM array type when available
                char_len: int | str = 16
                if isa(op.global_type, llvm.LLVMArrayType):
                    char_len = cast(llvm.LLVMArrayType, op.global_type).size.data
                if is_const:
                    # Read-only string constants use the parameter attribute
                    self.print(
                        f"character(len={char_len}), parameter :: {name} = '{val}'",
                        prefix="  ",
                    )
                else:
                    # Mutable state variable (e.g. ccpp_suite_state). For a
                    # multi-instance suite (see suite_cap.py's
                    # _build_state_globals), "allocatable" is set: one entry
                    # per model instance is needed, but number_of_instances
                    # is itself a runtime HOST scalar, not a compile-time
                    # constant, so this must be a deferred-shape allocatable
                    # -- actually allocated+initialized on first use by a
                    # LazyAllocOp (see _build_suite_state_lazy_alloc), not
                    # given an inline initializer here.
                    if "allocatable" in op.attributes:
                        self.print(
                            f"character(len={char_len}), allocatable,"
                            f" dimension(:) :: {name}",
                            prefix="  ",
                        )
                    else:
                        self.print(
                            f"character(len={char_len}) :: {name} = '{val}'",
                            prefix="  ",
                        )

        # Emit derived-type definitions a ConstituentApiOp needs
        # declared in the specification part (before CONTAINS) -- e.g. the
        # multi-instance constituent-API fix's own per-instance bundle
        # type. Must come BEFORE the plain ModuleVarOp declarations below:
        # a var of this new type is one of them (lc_instances), and
        # Fortran requires a derived-type definition to appear before any
        # variable declared with it in the same specification part --
        # confirmed the hard way, printing these in the other order
        # produced "has no IMPLICIT type" on lc_instances' own type name.
        # Also its own reason Fortran forbids a `type :: ... end type`
        # block inside CONTAINS in the first place, hence needing this
        # separate emission point at all.
        type_defs = [op for op in body.ops if isa(op, CCPPDerivedTypeDefOp)] + [
            child
            for op in body.ops if isa(op, CCPPConstituentApiOp)
            for child in op.body.block.ops if isa(child, CCPPDerivedTypeDefOp)
        ]
        for child in type_defs:
            attrs = (", public" if child.is_public is not None else "") + (
                ", bind(c)" if child.bind_c is not None else "")
            self.print(f"type{attrs} :: {child.type_name.data}", prefix="  ")
            for comp in child.body.block.ops:
                if not isa(comp, CCPPDdtComponentDeclOp):
                    continue
                rank      = comp.rank.value.data
                ftn_type  = _decl_fortran_type(comp)
                var_name  = comp.var_name.data
                is_ptr    = comp.is_pointer is not None and comp.is_pointer.value.data
                if comp.fixed_dim is not None:
                    dim = comp.fixed_dim.value.data
                    if comp.init_value_region is not None:
                        init_part = " = " + self._render_expr(
                            comp.init_value_region.block.last_op)
                    else:
                        init_part = ""
                    self.print(f"{ftn_type} :: {var_name}({dim}){init_part}", prefix="    ")
                elif rank == 0:
                    self.print(f"{ftn_type} :: {var_name}", prefix="    ")
                else:
                    shape = ", ".join([":"] * rank)
                    if is_ptr:
                        self.print(f"{ftn_type} :: {var_name}({shape}) => null()", prefix="    ")
                    else:
                        self.print(f"{ftn_type}, allocatable :: {var_name}({shape})", prefix="    ")
            self.print(f"end type {child.type_name.data}", prefix="  ")

        # Emit module-level variable declarations (unified ModuleVarOp).
        # rank=0: scalar, fixed_dim set: fixed-size non-allocatable array,
        # rank>0 otherwise: allocatable array with that many deferred dimensions.
        for op in body.ops:
            if isa(op, CCPPModuleVarOp):
                rank     = op.rank.value.data
                ftn_type = _decl_fortran_type(op)
                var_name = op.var_name.data
                is_ptr   = op.is_pointer is not None and op.is_pointer.value.data
                if op.fixed_dim is not None:
                    dim = op.fixed_dim.value.data
                    if op.init_value_region is not None:
                        init_part = f" = {self._render_expr(op.init_value_region.block.last_op)}"
                    else:
                        init_part = ""
                    self.print(f"{ftn_type} :: {var_name}({dim}){init_part}", prefix="  ")
                elif rank == 0:
                    self.print(f"{ftn_type} :: {var_name}", prefix="  ")
                else:
                    shape = ", ".join([":"] * rank)
                    if is_ptr:
                        self.print(
                            f"{ftn_type} :: {var_name}({shape}) => null()",
                            prefix="  ",
                        )
                    else:
                        self.print(
                            f"{ftn_type}, allocatable :: {var_name}({shape})",
                            prefix="  ",
                        )
                        if (
                            op.needs_device_residency is not None
                            and bool(op.needs_device_residency.value.data)
                        ):
                            # A runtime `!$acc enter data create(...)`
                            # inside a later subroutine (see LazyAllocOp)
                            # establishes the actual device buffer, but for
                            # a module-scope ALLOCATABLE array referenced
                            # across many separate, later subroutine calls
                            # over the life of the run (unlike a single
                            # lexically-scoped `!$acc data` region),
                            # nvfortran needs this companion `declare
                            # create` at the point of declaration itself,
                            # or the array's device-side descriptor/size is
                            # undefined -- confirmed as the actual cause of
                            # a "PRESENT clause was not found on device"
                            # runtime failure for a SuiteOwned scratch
                            # array even after its enter-data-create/
                            # update-device calls were verified compiling
                            # and executing correctly.
                            self.print("#ifdef USE_GPU", use_prefix=False)
                            self.print(
                                f"!$acc declare create({var_name})",
                                prefix="  ",
                            )
                            self.print("#endif", use_prefix=False)

        # Emit one public :: line per subroutine definition that is marked public.
        public_procs = [
            op.sym_name.data
            for op in body.ops
            if (
                isa(op, func.FuncOp)
                and not op.is_declaration
                and op.sym_visibility is not None
                and op.sym_visibility.data == "public"
            )
        ] + [
            name.data
            for op in body.ops
            if isa(op, CCPPConstituentApiOp)
            for name in op.public_names.data
        ]
        for proc in public_procs:
            self.print(f"public :: {proc}", prefix="  ")

        # Only emit CONTAINS when there are subroutine definitions to print
        has_func_defs = any(
            (isa(op, func.FuncOp) and not op.is_declaration)
            or isa(op, CCPPConstituentApiOp)
            for op in body.ops
        )
        if has_func_defs:
            self.print("\nCONTAINS")
            with self.descend() as inner:
                inner.print_block(body)

        self.print(f"end module {module_name.data}")

    def get_call_result_var_ssa(self, res_ssa):
        """Resolve a call result SSA value to the Fortran variable it writes into.

        After a scheme subroutine call the MLIR IR contains a memref.CopyOp
        that copies each result into its destination storage.  This method
        follows that use edge to find the destination variable name.  If no
        CopyOp is found the result was pre-registered as an anonymous local by
        _print_fn and its name is looked up directly in self.variables.
        """
        for use in res_ssa.uses:
            if isa(use.operation, memref.CopyOp):
                return self._get_variable_name_for(use.operation.destination)
        # No CopyOp — must have been pre-registered as an anonymous local
        return self.variables.get(res_ssa)

    def _print_call(self, tgt, args, results):
        """Print a func.CallOp as a Fortran subroutine call statement.

        Input arguments are printed by variable name.  Output arguments are
        resolved through the CopyOp use-chain to find the destination variable
        that will receive each result.

        Inout-echo returns are suppressed: when the suite cap returns a scalar
        inout arg as an SSA value (MLIR SSA convention), the resolved destination
        name is the same variable already printed as an input.  Printing it again
        would produce an invalid duplicate argument in the Fortran call.
        """
        self.print(f"call {tgt.string_value()}(", end="")

        # Collect input variable names to detect inout-echo returns.
        input_var_names = {self._get_variable_name_for(arg) for arg in args}

        # Print input arguments
        printed = 0
        for arg in args:
            if printed > 0:
                self.print(", ", end="", use_prefix=False)
            self.print(self._get_variable_name_for(arg), end="", use_prefix=False)
            printed += 1

        # Print output argument destinations, skipping inout echoes
        for res in results:
            ret_name = self.get_call_result_var_ssa(res)
            if ret_name is not None and ret_name in input_var_names:
                continue  # inout echo — already in the input list, skip
            if printed > 0:
                self.print(", ", end="", use_prefix=False)
            self.print(ret_name, end="", use_prefix=False)
            printed += 1

        self.print(")", use_prefix=False)

    def _print_kw_call(self, op: CCPPKeywordCallOp):
        """Print a ccpp_utils.kw_call as a Fortran keyword-argument subroutine call.

        Compile-time literal overrides are emitted first as ``name=literal``,
        then SSA input operands as ``name=var_name``, then SSA output results
        as ``name=dest_var``.  Inout arguments (present in both operand_names
        and result_names under the SAME keyword name) are deduplicated via a
        seen-names set.

        A leading inout-echo result (see run_dispatch.py's
        _get_suite_leading_inout_ret_info) is a SEPARATE case that name-based
        dedup above misses: the callee's own combined signature only ever
        gives it ONE real dummy argument, but the synthetic result keyword
        name generated for it (e.g. "_out_0") never string-matches the
        operand keyword name that already passed the same variable (e.g.
        "scalar_var") -- so without an extra value-based check here, the
        same variable would get bound twice under two different keyword
        names to what is really the same dummy argument, which is invalid
        Fortran (mirrors _print_call's own input_var_names check for the
        positional-call case).
        """
        self.print(f"call {op.callee.data}(", end="")
        idx = 0
        seen: set[str] = set()
        printed_operand_values: set[str] = set()
        for r in op.override_ops_region:
            kw_op = r.block.last_op
            if idx > 0:
                self.print(", ", end="", use_prefix=False)
            self.print(self._render_expr(kw_op), end="", use_prefix=False)
            seen.add(kw_op.arg_name.data)
            idx += 1
        for name_attr, arg in zip(op.operand_names.data, op.args):
            name = name_attr.data
            if name not in seen:
                resolved = self._get_variable_name_for(arg)
                if idx > 0:
                    self.print(", ", end="", use_prefix=False)
                self.print(f"{name}={resolved}", end="", use_prefix=False)
                seen.add(name)
                printed_operand_values.add(resolved)
                idx += 1
        for name_attr, res in zip(op.result_names.data, op.res):
            name = name_attr.data
            if name not in seen:
                dest = self.get_call_result_var_ssa(res)
                if dest is not None and dest in printed_operand_values:
                    continue  # inout echo — same dummy arg already passed as an input
                if idx > 0:
                    self.print(", ", end="", use_prefix=False)
                self.print(f"{name}={dest}", end="", use_prefix=False)
                seen.add(name)
                idx += 1
        self.print(")", use_prefix=False)

    def _print_if(
        self,
        conditional,
        true_bdy: Region,
        false_bdy: Region,
    ):
        """Print an scf.IfOp as a Fortran if / else / end if block."""
        self.print("if (", end="")
        self.print_expr(conditional.owner)
        self.print(") then", use_prefix=False)

        with self.descend() as inner:
            inner.print_block(true_bdy)

        if len(false_bdy.blocks) > 0:
            self.print("else")
            with self.descend() as inner:
                inner.print_block(false_bdy)

        self.print("end if")

    def _map_ftn_to_c_type(self, ftn_type: str) -> str:
        """Map a Fortran type string to its ISO_C_BINDING equivalent."""
        if ftn_type == "integer":
            return "integer(c_int)"
        if ftn_type == "logical":
            return "logical(c_bool)"
        if ftn_type.startswith("real(kind=4"):
            return "real(c_float)"
        if ftn_type.startswith("real"):
            # All named real kinds (kind_phys, kind_dyn, kind=8, etc.) → c_double
            return "real(c_double)"
        if ftn_type.startswith("type("):
            return "type(c_ptr)"
        return ftn_type

    def _bind_c_arg_decl_line(
        self, arg_type: Attribute, arg_name: str, intent: str, is_opt: bool = False,
        explicit_dims: "list[str] | None" = None, keep_derived: bool = False,
    ) -> str:
        """Return a BIND(C)-compatible Fortran argument declaration line.

        Character types are mapped to ``character(kind=c_char, len=1), dimension(*)``.
        Integer scalars with ``intent(in)`` use the ``VALUE`` attribute (pass by value).
        All real kinds default to ``real(c_double)`` (CCPP physics kinds are 64-bit).

        explicit_dims -- when given (the per-dimension extents spelled
        from a bind_c_extents entry, e.g. ["col_end - col_start + 1", "nz"]
        -- see cap_shared.bind_c_extents_attr), an array
        argument is declared with EXPLICIT shape + target instead of flat
        assumed-size (*) -- chost-rank3-bindc: assumed-size (*) cannot be
        passed to the suite cap's own assumed-shape (:,...) dummy for any
        rank (confirmed via gfortran), the same fix already proven in the
        chost path's own ftn_decl. None (unresolved) keeps today's exact
        (*) output -- Fortran's explicit-shape declarator has no partial
        form, so a partially-resolved dimension list is never passed here.

        keep_derived -- a derived type is passed as itself (a BIND(C) struct
        of a fixed interface), not as an opaque type(c_ptr).
        """
        opt_clause = ", optional" if is_opt else ""
        ftn_type = self.mlir_type_to_ftn_type(arg_type)
        dim_suffix = self._ftn_dim_suffix(arg_type)
        if keep_derived and ftn_type.startswith("type("):
            dims = f"({', '.join(explicit_dims)})" if explicit_dims else dim_suffix
            return f"{ftn_type}, intent({intent}){opt_clause} :: {arg_name}{dims}"

        if ftn_type.startswith("character"):
            # All character arguments → c_char assumed-size array
            return (
                f"character(kind=c_char, len=1), intent({intent}){opt_clause}"
                f" :: {arg_name}(*)"
            )

        c_type = self._map_ftn_to_c_type(ftn_type)

        if not dim_suffix:
            # Scalar: intent(in) → VALUE (C passes by value, not pointer)
            if intent == "in":
                return f"{c_type}, value, intent(in){opt_clause} :: {arg_name}"
            return f"{c_type}, intent({intent}){opt_clause} :: {arg_name}"

        if explicit_dims:
            dims_str = ", ".join(explicit_dims)
            return (
                f"{c_type}, target, intent({intent}){opt_clause}"
                f" :: {arg_name}({dims_str})"
            )

        # Fallback: dimension resolution unavailable -- assumed-size (*),
        # C side passes a raw pointer (known-broken for rank >= 1 when
        # forwarded to the suite cap's assumed-shape dummy, but strictly
        # no worse than today's output).
        return f"{c_type}, intent({intent}){opt_clause} :: {arg_name}(*)"

    def _print_cxx_interface_blocks(self, cxx_fns: list) -> None:
        """Emit Fortran BIND(C) interface blocks for C++ scheme entry points.

        Each external func.FuncOp with a ``language`` attribute gets one
        ``interface`` / ``end interface`` block.  Argument names and intents
        are read from the ``arg_names`` and ``arg_intents`` ArrayAttr stamps
        placed by ``_build_fn_signatures`` in the suite cap pass; if absent
        (e.g. the entry point had no arg table) positional fallback names are
        used.
        """
        self.print("")
        self.print("interface", prefix="  ")
        for fn_op in cxx_fns:
            fn_name = fn_op.sym_name.data
            arg_types = list(fn_op.function_type.inputs)

            names_attr = fn_op.attributes.get("arg_names")
            arg_names = (
                [a.data for a in names_attr.data]
                if names_attr is not None
                else [f"arg_{i}" for i in range(len(arg_types))]
            )
            intents_attr = fn_op.attributes.get("arg_intents")
            arg_intents = (
                [a.data for a in intents_attr.data]
                if intents_attr is not None
                else ["inout"] * len(arg_types)
            )

            arg_list = ", ".join(arg_names)
            self.print(f"  subroutine {fn_name}({arg_list}) &", prefix="  ")
            self.print(f"      BIND(C, name='{fn_name}')", prefix="  ")
            self.print("    use iso_c_binding", prefix="    ")
            for arg_name, arg_type, intent in zip(arg_names, arg_types, arg_intents):
                decl = self._bind_c_arg_decl_line(arg_type, arg_name, intent)
                self.print(decl, prefix="    ")
            self.print(f"  end subroutine {fn_name}", prefix="  ")
        self.print("end interface", prefix="  ")

    @staticmethod
    def _analyze_fn_body(bdy: Region, fn_op: "object | None" = None) -> _FnBodyAnalysis:
        """Pure IR analysis for one func.FuncOp body, run before any printing
        begins.

        Argument names and declaration flags (allocatable, optional,
        intent(in)) come from the function's arg_attrs (arg_decl).
        Output-argument names come from the alloca results' name hints.

        The ReturnOp is scanned to detect inout arguments (block args that
        appear in the return list) so they can be declared intent(inout) rather
        than the default intent(in).  Pure output arguments come from AllocaOp
        results also present in the return list.
        """
        attrs = (arg_attr_values(fn_op) if fn_op is not None
                 else [{} for _ in bdy.block.args])
        arg_decls = [
            arg_decl(a, arg.name_hint, idx)
            for idx, (arg, a) in enumerate(zip(bdy.block.args, attrs))
        ]
        input_names = [d.name for d in arg_decls]

        # Scan ReturnOp to separate output allocas from returned inout block args
        output_names: list[str] = []
        output_ret_vals: list = []
        inout_block_args: set = set()
        for op in bdy.block.ops:
            if isa(op, func.ReturnOp):
                for ret_val in op.arguments:
                    if isa(ret_val.owner, memref.AllocaOp):
                        # AllocaOp result → a true output argument
                        out_name = (
                            ret_val.name_hint
                            if ret_val.name_hint is not None
                            else f"out_{len(output_names)}"
                        )
                        output_names.append(out_name)
                        output_ret_vals.append(ret_val)
                    else:
                        # Block arg in return position → inout argument
                        inout_block_args.add(ret_val)
                break

        # Collect local allocas — AllocaOps whose result is not in the return list.
        # walk() (not just bdy.block.ops): most allocas are top-level, but e.g.
        # run_dispatch.py's per-suite-part horizontal_dimension scalar recompute
        # (col_end - col_start + 1) allocates its own local nested inside the
        # suite_name/suite_part dispatch chain's scf.IfOps -- same reasoning as
        # the CCPPKindCastOp/CCPPUnitConvertOp walk() below.
        # A BLOCK construct's own locals (ScopedBlockOp) are declared in the
        # block, not here.
        local_allocas = [
            op
            for op in bdy.block.walk()
            if isa(op, memref.AllocaOp) and op.memref not in output_ret_vals
            and not isa(op.parent_op(), CCPPScopedBlockOp)
        ]

        # Collect call results that have no CopyOp consumer — they become anonymous locals
        # (e.g. DDT outputs from init that the ccpp_cap doesn't route anywhere).
        # Also look one level through UnrealizedConversionCastOp (inserted for type mismatches).
        def _has_copy_consumer(ssa):
            for u in ssa.uses:
                if isa(u.operation, memref.CopyOp):
                    return True
                if isa(u.operation, builtin.UnrealizedConversionCastOp):
                    if any(
                        isa(u2.operation, memref.CopyOp)
                        for u2 in u.operation.results[0].uses
                    ):
                        return True
            return False

        untracked_call_results: list[tuple[OpResult, str]] = []
        for nested_op in bdy.block.walk():
            if not isa(nested_op, func.CallOp) and not isa(
                nested_op, CCPPKeywordCallOp
            ):
                continue
            for res in nested_op.results:
                has_copy = _has_copy_consumer(res)
                if not has_copy:
                    hint = (
                        res.name_hint
                        if res.name_hint
                        else f"ccpp_tmp_{len(untracked_call_results)}"
                    )
                    untracked_call_results.append((res, hint))

        return _FnBodyAnalysis(
            input_names=input_names,
            arg_decls=arg_decls,
            output_names=output_names,
            output_ret_vals=output_ret_vals,
            inout_block_args=inout_block_args,
            local_allocas=local_allocas,
            untracked_call_results=untracked_call_results,
        )

    def _setup_bind_c_char_conversions(
        self, inner: ftnPrintContext, bdy: Region, analysis: _FnBodyAnalysis, bind_c: bool,
    ) -> list[tuple[str, str, str]]:
        """BIND(C) character conversion: re-map each character parameter's SSA
        value to a Fortran-local ``_f`` variable so that trim() and calls to
        non-BIND(C) suite-cap routines use a proper scalar character string
        instead of the raw c_char(*) assumed-size array. Mutates
        inner.variables for every character arg found. Conversion loops for
        the returned list are emitted separately, by
        _print_c_to_f_char_conversions/_print_f_to_c_char_conversions.

        Returns [] (no-op) when bind_c is False.
        """
        bind_c_char_conversions: list[tuple[str, str, str]] = []
        if not bind_c:
            return bind_c_char_conversions
        for arg, arg_name in zip(bdy.block.args, analysis.input_names):
            if inner.mlir_type_to_ftn_type(arg.type).startswith("character"):
                ftn_local = f"{arg_name}_f"
                inner.variables[arg] = ftn_local
                conv_intent = "inout" if arg in analysis.inout_block_args else "in"
                bind_c_char_conversions.append((arg_name, ftn_local, conv_intent))
        for ret_val, out_name in zip(analysis.output_ret_vals, analysis.output_names):
            if inner.mlir_type_to_ftn_type(ret_val.type).startswith("character"):
                ftn_local = f"{out_name}_f"
                inner.variables[ret_val] = ftn_local
                bind_c_char_conversions.append((out_name, ftn_local, "out"))
        return bind_c_char_conversions

    def _declare_fn_arguments(
        self, inner: ftnPrintContext, bdy: Region, analysis: _FnBodyAnalysis, bind_c: bool,
        fn_op: "object | None" = None,
    ) -> None:
        """Print the subroutine's own dummy-argument declarations: intent(in)/
        intent(inout) for inputs, intent(out) for outputs (always scalars).

        fn_op -- when given and bind_c is set, its own bind_c_extents
        attribute (cap_shared.bind_c_extents_attr: one entry per block arg
        in order, empty meaning "no override") supplies an
        explicit-shape dimension list for an array argument instead of
        today's flat assumed-size (*) (chost-rank3-bindc). Absent/missing/
        empty falls straight back to the existing (*) behavior -- additive,
        every other caller of this function (there are none besides
        _print_fn's own single call site) and every non-array/non-bind_c
        case is completely unaffected.
        """
        extents_attr = (
            fn_op.attributes.get("bind_c_extents") if fn_op is not None else None
        )
        # Declare input arguments with intent(in) or intent(inout).
        # Array block args (dynamic memref) are always intent(inout): the host
        # provides the buffer and the scheme may write to it in-place.
        # Exception: memref<memref<?xi8>> is an allocatable character array
        # passed intent(out) — the callee allocates and fills it.
        for idx, (arg, decl) in enumerate(zip(bdy.block.args, analysis.arg_decls)):
            arg_name, is_alloc, is_opt = decl.name, decl.is_alloc, decl.is_opt
            type_str = inner.mlir_type_to_ftn_type(arg.type)
            dim_suffix = inner._ftn_dim_suffix(arg.type)
            is_allocatable_char = ftnPrintContext._is_allocatable_char(arg.type)
            intent = classify_arg_intent(
                is_allocatable_char=is_allocatable_char,
                is_alloc=is_alloc,
                is_in=decl.is_in,
                has_array_dims=bool(dim_suffix),
                is_inout_return=arg in analysis.inout_block_args,
                declared_intent=decl.declared_intent,
            )
            if is_allocatable_char or is_alloc:
                type_str = type_str + ", allocatable"
            if bind_c:
                explicit_dims = None
                if extents_attr is not None and idx < len(extents_attr.data):
                    explicit_dims = [
                        _extent_text([n.data for n in extent.data])
                        for extent in extents_attr.data[idx].data
                    ] or None
                inner.print(inner._bind_c_arg_decl_line(
                    arg.type, arg_name, intent, is_opt, explicit_dims=explicit_dims,
                    keep_derived=decl.declared_intent is not None,
                ))
            else:
                if is_opt:
                    type_str = type_str + ", optional"
                if decl.declared_intent is not None:
                    # A fixed interface: exactly the attributes it declares.
                    if decl.is_pointer:
                        type_str = type_str + ", pointer"
                    if decl.is_target:
                        type_str = type_str + ", target"
                elif dim_suffix and not is_alloc and not ftnPrintContext._is_allocatable_char(arg.type):
                    type_str = type_str + ", target"
                inner.print(f"{type_str}, intent({intent}) :: {arg_name}{dim_suffix}")

        # A function's result variable (FN_RESULT): its alloca's own type and
        # attributes, no intent.
        if fn_op is not None and FN_RESULT in fn_op.attributes:
            for ret_val, out_name in zip(analysis.output_ret_vals, analysis.output_names):
                if bind_c:
                    c_type = inner._map_ftn_to_c_type(inner.mlir_type_to_ftn_type(ret_val.type))
                    inner.print(f"{c_type} :: {out_name}")
                else:
                    inner.print(ftnPrintContext._local_decl_line(inner, ret_val.owner, out_name))
            return

        # Declare output arguments with intent(out) (always scalars)
        for ret_val, out_name in zip(analysis.output_ret_vals, analysis.output_names):
            type_str = inner.mlir_type_to_ftn_type(ret_val.type)
            dim_suffix = inner._ftn_dim_suffix(ret_val.type)
            if bind_c:
                inner.print(inner._bind_c_arg_decl_line(ret_val.type, out_name, "out"))
            else:
                if dim_suffix:
                    type_str = type_str + ", target"
                inner.print(f"{type_str}, intent(out) :: {out_name}{dim_suffix}")

    @staticmethod
    def _local_decl_line(inner: "ftnPrintContext", alloca_op, ftn_name: str) -> str:
        """Declaration of the variable an alloca stands for: a local, or a
        function's result. An allocatable or pointer one is deferred-shape:
        its memref shape encodes only the rank (via [0]*rank static zeros to
        satisfy MLIR verification), so the base type comes from the element
        type and no shape literal leaks into the type string."""
        memref_type = alloca_op.memref.type
        for marked, attr in ((is_allocatable_local(alloca_op), "allocatable"),
                             (is_pointer_local(alloca_op), "pointer")):
            if marked:
                rank = len(memref_type.shape.data)
                type_str = inner.mlir_type_to_ftn_type(memref_type.element_type)
                dims = "(" + ", ".join(":" for _ in range(rank)) + ")" if rank else ""
                return f"{type_str}, {attr} :: {ftn_name}{dims}"
        return f"{inner.mlir_type_to_ftn_type(memref_type)} :: {ftn_name}"

    def _declare_fn_locals(
        self,
        inner: ftnPrintContext,
        bdy: Region,
        analysis: _FnBodyAnalysis,
        bind_c_char_conversions: list[tuple[str, str, str]],
    ) -> None:
        """Print declarations for every local variable the subroutine body
        itself needs: non-returned allocas, kind-cast/unit-convert/
        vertical-flip temporaries, row-major transpose temporaries, anonymous
        locals for untracked call results, and (BIND(C) only) the character
        marshaling buffers + loop counter."""
        # Declare local variables (non-returned allocas, e.g. computed scalars).
        #
        # Two or more sibling subcycles (nested or not) each allocate their
        # own loop-count variable with the same "ccpp_loop_cnt" name_hint
        # (see suite_cap.py's _build_call_ops) -- de-duplicate through
        # _get_variable_name_for (the same mechanism the do-loop body's own
        # references already use) rather than printing the raw name_hint
        # directly, which would emit the identical declaration line twice
        # (a Fortran compile error) whenever that collision happens.
        for alloca_op in analysis.local_allocas:
            hint = (
                local_name(alloca_op)
                or alloca_op.memref.name_hint
                or f"local_{id(alloca_op)}"
            )
            ftn_name = inner._get_variable_name_for(alloca_op.memref, hint=hint)
            inner.print(ftnPrintContext._local_decl_line(inner, alloca_op, ftn_name))

        # Declare kind-cast and unit-convert temporaries. These are usually
        # top-level ops in suite caps (the suite-boundary conversion), but
        # the per-call, cross-scheme-divergent marshaling in suite_cap.py's
        # generateSchemeSubroutineCallOps can nest them inside scf.IfOps
        # and subcycle loop bodies -- walk() finds both.
        for op in bdy.block.walk():
            if isa(op, CCPPKindCastOp):
                # Two or more per-call marshaling instances (see
                # suite_cap.py's generateSchemeSubroutineCallOps) can share
                # the same name_hint -- e.g. one scheme's own call and
                # another scheme's own call both adapting the same shared
                # argument -- de-duplicate through _get_variable_name_for
                # the same way local_allocas above does, rather than
                # assigning the raw name_hint directly, which would print
                # the identical declaration twice.
                hint = (
                    op.res.name_hint
                    if op.res.name_hint is not None
                    else f"kind_cast_{id(op)}"
                )
                var_name = inner._get_variable_name_for(op.res, hint=hint)
                type_str = inner.mlir_type_to_ftn_type(op.res.type)
                dim_suffix = inner._ftn_dim_suffix(op.res.type)
                if dim_suffix:
                    inner.print(f"{type_str}, allocatable :: {var_name}{dim_suffix}")
                else:
                    inner.print(f"{type_str} :: {var_name}")
            elif isa(op, CCPPUnitConvertOp):
                # Local-copy conversion: declare a temp in the same type as source.
                # Same de-duplication reasoning as CCPPKindCastOp above.
                hint = (
                    op.res.name_hint
                    if op.res.name_hint is not None
                    else f"unit_conv_{id(op)}"
                )
                var_name = inner._get_variable_name_for(op.res, hint=hint)
                type_str = inner.mlir_type_to_ftn_type(op.res.type)
                dim_suffix = inner._ftn_dim_suffix(op.res.type)
                if dim_suffix:
                    inner.print(f"{type_str}, allocatable :: {var_name}{dim_suffix}")
                else:
                    inner.print(f"{type_str} :: {var_name}")
            elif isa(op, CCPPVerticalFlipOp):
                # Always an array (a vertical flip is meaningless for a
                # scalar). Same de-duplication reasoning as above.
                hint = (
                    op.res.name_hint
                    if op.res.name_hint is not None
                    else f"vertical_flip_{id(op)}"
                )
                var_name = inner._get_variable_name_for(op.res, hint=hint)
                type_str = inner.mlir_type_to_ftn_type(op.res.type)
                dim_suffix = inner._ftn_dim_suffix(op.res.type)
                inner.print(f"{type_str}, allocatable :: {var_name}{dim_suffix}")

        # Declare row-major transpose temps (may be nested inside scf.IfOps in CCPP caps)
        for op in bdy.block.walk():
            if isa(op, CCPPRowMajorConvertOp):
                var_name = (
                    op.res.name_hint
                    if op.res.name_hint is not None
                    else f"row_major_col_{id(op)}"
                )
                inner.variables[op.res] = var_name
                type_str = inner.mlir_type_to_ftn_type(op.res.type)
                dim_suffix = inner._ftn_dim_suffix(op.res.type)
                if dim_suffix:
                    inner.print(f"{type_str}, allocatable :: {var_name}{dim_suffix}")
                else:
                    inner.print(f"{type_str} :: {var_name}")

        # Declare anonymous locals for call results that have no CopyOp consumer
        for res, var_name in analysis.untracked_call_results:
            inner.variables[res] = var_name
            type_str = inner.mlir_type_to_ftn_type(res.type)
            dim_suffix = inner._ftn_dim_suffix(res.type)
            inner.print(f"{type_str} :: {var_name}{dim_suffix}")

        # Declare Fortran-local character(len=512) temps + loop counter for
        # the C↔Fortran string conversions emitted below.
        if bind_c_char_conversions:
            inner.print("integer :: ccpp_c2f_i")
            for _, ftn_local, _ in bind_c_char_conversions:
                inner.print(f"character(len=512) :: {ftn_local}")

    def _print_c_to_f_char_conversions(
        self, inner: ftnPrintContext, bind_c_char_conversions: list[tuple[str, str, str]],
    ) -> None:
        """Emit C→Fortran conversion loops for input/inout BIND(C) character args."""
        for c_name, ftn_local, conv_intent in bind_c_char_conversions:
            if conv_intent in ("in", "inout"):
                inner.print(f"{ftn_local} = ' '")
                with inner.descend(
                    f"do ccpp_c2f_i = 1, len({ftn_local})", "end do"
                ) as loop:
                    loop.print(f"if ({c_name}(ccpp_c2f_i) == c_null_char) exit")
                    loop.print(
                        f"{ftn_local}(ccpp_c2f_i:ccpp_c2f_i) = {c_name}(ccpp_c2f_i)"
                    )
            else:
                inner.print(f"{ftn_local} = ' '")

    def _print_f_to_c_char_conversions(
        self, inner: ftnPrintContext, bind_c_char_conversions: list[tuple[str, str, str]],
    ) -> None:
        """Emit Fortran→C conversion loops for output/inout BIND(C) character args."""
        for c_name, ftn_local, conv_intent in bind_c_char_conversions:
            if conv_intent in ("out", "inout"):
                with inner.descend(
                    f"do ccpp_c2f_i = 1, len_trim({ftn_local})", "end do"
                ) as loop:
                    loop.print(
                        f"{c_name}(ccpp_c2f_i) = {ftn_local}(ccpp_c2f_i:ccpp_c2f_i)"
                    )
                inner.print(f"{c_name}(len_trim({ftn_local})+1) = c_null_char")

    def _print_fn(
        self,
        fn_name: StringAttr,
        bdy: Region,
        ftyp: FunctionType,
        bind_c: bool = False,
        fn_op: "object | None" = None,
    ):
        """Print a func.FuncOp definition as a Fortran subroutine.

        Delegates to _analyze_fn_body for the pure IR analysis (arg names,
        ReturnOp inout/output split, local allocas, untracked call results),
        then _setup_bind_c_char_conversions/_declare_fn_arguments/
        _declare_fn_locals to print the declaration preamble, then wraps the
        actual body print (print_block) with the BIND(C) character
        marshaling loops (_print_c_to_f_char_conversions/
        _print_f_to_c_char_conversions).

        fn_op -- the owning func.FuncOp itself (not just its decomposed
        name/body/type), so _declare_fn_arguments can read its own
        bind_c_extents attribute (chost-rank3-bindc) -- optional, so
        every other existing concern stays unaffected.
        """
        analysis = self._analyze_fn_body(bdy, fn_op)

        # FN_RESULT: a Fortran function, whose returned alloca is its result
        # variable rather than an intent(out) argument.
        is_function = fn_op is not None and FN_RESULT in fn_op.attributes
        if is_function:
            kw = "function"
            args_str = ", ".join(analysis.input_names)
            result_part = f" result({analysis.output_names[0]})"
        else:
            kw = "subroutine"
            args_str = ", ".join(analysis.input_names + analysis.output_names)
            result_part = ""
        if bind_c:
            start_signature = (
                f"\n{kw} {fn_name.data}({args_str}){result_part}"
                f" BIND(C, name='{fn_name.data}')"
            )
        else:
            start_signature = f"\n{kw} {fn_name.data}({args_str}){result_part}"
        end_signature = f"end {kw} {fn_name.data}"

        with self.descend(start_signature, end_signature) as inner:
            # Register input block args so downstream ops can look them up by name
            for arg, arg_name in zip(bdy.block.args, analysis.input_names):
                inner.variables[arg] = arg_name
            inner.optional_args = {
                arg for arg, decl in zip(bdy.block.args, analysis.arg_decls)
                if decl.is_opt
            }

            # Register output alloca results so StoreOp and CallOp can resolve them
            for ret_val, out_name in zip(analysis.output_ret_vals, analysis.output_names):
                inner.variables[ret_val] = out_name

            # A fixed interface's body does its own character copies.
            fixed = fn_op is not None and FN_FIXED_INTERFACE in fn_op.attributes
            bind_c_char_conversions = self._setup_bind_c_char_conversions(
                inner, bdy, analysis, bind_c and not fixed
            )

            uses = fn_op.attributes.get(FN_USES) if fn_op is not None else None
            if uses is not None:
                for module, names in uses.data.items():
                    inner.print(f"use {module}, only: {', '.join(n.data for n in names.data)}")
            self._declare_fn_arguments(inner, bdy, analysis, bind_c, fn_op)
            self._declare_fn_locals(inner, bdy, analysis, bind_c_char_conversions)

            inner.print("")

            self._print_c_to_f_char_conversions(inner, bind_c_char_conversions)
            inner.print_block(bdy.block)
            self._print_f_to_c_char_conversions(inner, bind_c_char_conversions)

    def _emit_acc_directive(
        self, keyword: str, clauses: list, *, sentinel: str = "!$acc"
    ) -> None:
        """Emit an OpenACC directive with proper continuation at variable boundaries.

        Builds the directive token by token.  When adding the next token would
        push the current line past _MAX_LINE_LEN, the line is flushed with a
        Fortran continuation marker ' &' and a new line is started with the
        OpenACC sentinel prefix '!$acc     '.

        This handles both inter-clause breaks (between copyin/copyout/present)
        and intra-clause breaks within a long variable list, making it suitable
        for suites with 40+ variables per clause.

        Args:
            keyword:  The OpenACC directive keyword, e.g. 'data' or 'update'.
            clauses:  List of (clause_name, [var_name_strings]) pairs, or
                      (clause_name, [var_name_strings], opener) triples.
                      Pairs with empty variable lists are skipped. `opener`
                      defaults to "(" -- the ACC/OMP-update convention, where
                      clause_name is a bare keyword and exactly one paren is
                      added (e.g. "copyin" -> "copyin(var)"). OMP's map-based
                      clauses have a two-level shape instead -- "map(" then a
                      map-type modifier then ":" then the list, e.g.
                      "map(tofrom:var)" (no space after the colon -- no
                      whitespace is inserted beyond what clause_name itself
                      contains) -- which doesn't fit a single auto-added "(":
                      pass clause_name as the complete literal prefix (e.g.
                      "map(tofrom:") with opener="" so nothing extra is
                      inserted.

        Example output for a long copyin list::

            !$acc data copyin(var1, var2, var3, &
            !$acc      var4, var5) copyout(var6)
        """
        acc_start = self._prefix + sentinel + " " + keyword
        acc_cont  = self._prefix + sentinel + "     "

        current = acc_start
        output_lines: list[str] = []

        for clause in clauses:
            clause_name, var_names = clause[0], clause[1]
            opener = clause[2] if len(clause) > 2 else "("
            if not var_names:
                continue
            # Build tokens: first includes the clause opener, last closes the paren.
            # e.g. ["copyin(var1,", "var2,", "var3)"]
            tokens = []
            for i, var in enumerate(var_names):
                prefix = f"{clause_name}{opener}" if i == 0 else ""
                suffix = ")" if i == len(var_names) - 1 else ","
                tokens.append(prefix + var + suffix)

            for token in tokens:
                candidate = current + " " + token
                if len(candidate) <= _MAX_LINE_LEN:
                    current = candidate
                else:
                    output_lines.append(current + " &")
                    current = acc_cont + " " + token

        output_lines.append(current)
        for line in output_lines:
            print(line, file=self.output)
    def _emit_omp_directive(self, keyword: str, clauses: list) -> None:
        self._emit_acc_directive(keyword, clauses, sentinel="!$omp")

    @contextmanager
    def descend(self, block_start: str = None, block_end: str = None):
        """Return a child context with one extra level of indentation.

        The child inherits a copy of the parent's variable map so that names
        defined in an outer scope remain visible inside nested blocks.  An
        optional block_start string (e.g. a subroutine signature) is printed
        before yielding, and block_end (e.g. 'end subroutine') is printed
        after the with-block completes.

        Usage::

            with self.descend("subroutine foo()", "end subroutine foo") as inner:
                inner.print_block(body)
        """
        if block_start is not None:
            self.print(f"{block_start} ")
        yield ftnPrintContext(
            output=self.output,
            variables=self.variables.copy(),
            _cmp_ops=self._cmp_ops,
            _binops=self._binops,
            _counter=self._counter,
            _prefix=self._prefix + self._INDENT,
            optional_args=self.optional_args,
        )
        if block_end is not None:
            self.print(f"{block_end} ")

    def print(self, text: str, prefix: str = "", end: str = "\n", use_prefix=True):
        """Append text to the current line buffer, flushing on newline.

        Embedded newlines in text cause an immediate buffer flush each time
        they are encountered.  When end="\\n" (the default) the buffer is
        flushed at the end of the call.  Passing use_prefix=False suppresses
        the indentation prefix for inline continuations.
        """
        parts = text.split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                self._emit_line()
            self._line_buf += (self._prefix + prefix if use_prefix else "") + part
        if end == "\n":
            self._emit_line()

    def _emit_line(self):
        """Flush the line buffer, splitting at commas if the line is too long.
        Trailing whitespace is dropped: a statement ended by an empty print
        (e.g. ``self.print("")`` after ``end=""``) or a blank line would
        otherwise end in its indentation."""
        line = self._line_buf.rstrip()
        self._line_buf = ""
        self._write_with_continuation(line, self._prefix + self._INDENT)

    def _write_with_continuation(self, line: str, cont_prefix: str):
        """Write line, inserting Fortran continuation markers at commas if needed.

        If line exceeds _MAX_LINE_LEN characters, the last comma at parenthesis
        depth zero at or before position _MAX_LINE_LEN - 2 is used as the split
        point: the first part is written with a trailing ' &' and the remainder
        is written on the next line starting with cont_prefix.  Recurses until
        the remainder fits.

        Only commas at depth zero are considered so that array subscript
        expressions such as arr(col_start:col_end, 1:pver) are never split
        in the middle.
        """
        if len(line) <= _MAX_LINE_LEN:
            print(line, file=self.output)
            return
        # Find the last comma at paren depth ≤ 1 within the line limit.
        # Depth 0: top-level commas.
        # Depth 1: commas between function/subroutine arguments — valid break points.
        # Depth > 1: commas inside nested subscript expressions such as
        #   arr(col_start:col_end, 1:pver) — never break inside these.
        split_pos = -1
        depth = 0
        for i, ch in enumerate(line[: _MAX_LINE_LEN - 2]):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth <= 1 and line[i + 1 :].strip() != "&":
                # Not the comma before the line's own trailing "&": that
                # would leave a line holding only "&" (nvfortran rejects it).
                split_pos = i
        if split_pos == -1:
            # No valid split point — emit as-is rather than produce invalid Fortran
            print(line, file=self.output)
            return
        print(line[: split_pos + 1].ljust(_MAX_LINE_LEN - 1) + "&", file=self.output)
        remainder = cont_prefix + line[split_pos + 1 :].lstrip()
        self._write_with_continuation(remainder, cont_prefix)

    def print_block(self, body: Block):
        """Iterate over every operation in body and dispatch it to print_op."""
        for op in body.ops:
            self.print_op(op)


def print_to_ftn(
    prog: ModuleOp, output: IO[str], Ctx: type[ftnPrintContext] = ftnPrintContext
):
    """Print all named sub-modules in prog as Fortran source to output.

    Each sub-module is preceded by a FILE comment that indicates the suggested
    output filename (e.g. '// FILE: hello_world_suite_cap.F90').  Multiple
    modules are separated by a '// -----' divider.
    """
    ctx = Ctx(output)
    ctx.register_binops()
    ctx.has_kinds_module = any(
        isinstance(op, builtin.ModuleOp) and op.sym_name.data == "ccpp_kinds"
        for op in prog.body.ops
    )
    divider = False
    for op in prog.body.ops:
        if isinstance(op, builtin.ModuleOp):
            if divider:
                ctx.print("// -----")
            divider = True
            ctx.print("// FILE: " + op.sym_name.data + ".F90")
            ctx.print_op(op)
        elif isinstance(op, CCPPCHostCapOp):
            if divider:
                ctx.print("// -----")
            divider = True
            ctx.print("// FILE: " + op.mod_name.data + ".F90")
            ctx.print_block(op.ftn_body.block)
