from xdsl.dialects.arith import ConstantOp as ArithConstantOp
from xdsl.dialects.builtin import (
    DYNAMIC_INDEX,
    ArrayAttr,
    BoolAttr,
    DictionaryAttr,
    IntegerAttr,
    IntegerType,
    MemRefType,
    StringAttr,
    i1,
)
from xdsl.dialects.llvm import LLVMArrayType
from xdsl.ir import (
    Dialect,
    Operation,
    ParametrizedAttribute,
    SSAValue,
    TypeAttribute,
    VerifyException,
)
from xdsl.irdl import (
    AttrSizedOperandSegments,
    AttrSizedRegionSegments,
    IRDLOperation,
    irdl_attr_definition,
    irdl_op_definition,
    operand_def,
    opt_operand_def,
    opt_prop_def,
    opt_region_def,
    opt_result_def,
    param_def,
    prop_def,
    region_def,
    result_def,
    traits_def,
    var_operand_def,
    var_region_def,
    var_result_def,
)
from xdsl.traits import NoTerminator


def _coerce_str_attr(value: "str | StringAttr | None") -> "StringAttr | None":
    """Coerce a plain str to StringAttr, passing an already-built StringAttr
    (or None) through.

    Extracted after this exact
    2-line `if isinstance(value, str): value = StringAttr(value)` pattern
    was found repeated, byte-identical, across 15 op/attribute constructors
    in this file. Accepts None because StrCmpOp.__init__ calls this
    unconditionally on its own optional `literal` param.
    """
    return StringAttr(value) if isinstance(value, str) else value


def _coerce_int_attr(value: "int | IntegerAttr", width: int = 64) -> IntegerAttr:
    """Coerce a plain int to IntegerAttr (given bit width), passing an
    already-built IntegerAttr through. Sibling of _coerce_str_attr -- see
    its docstring; this covers VerticalFlipOp/VerticalFlipWriteBackOp's own
    int-coercion pattern, found alongside the 15 str-coercion sites."""
    return IntegerAttr.from_int_and_width(value, width) if isinstance(value, int) else value


def _coerce_str_list_attr(value: "list[str] | ArrayAttr") -> ArrayAttr:
    """Coerce a list[str] to ArrayAttr[StringAttr], passing an already-built
    ArrayAttr through. Sibling of _coerce_str_attr -- see its docstring;
    this covers RowMajorConvertOp/RowMajorWriteBackOp's own list-coercion
    pattern, found alongside the 15 str-coercion sites."""
    return ArrayAttr([StringAttr(e) for e in value]) if isinstance(value, list) else value


def _flatten_floating_deps(root: Operation) -> "list[Operation]":
    """Return [*dependencies, root] in dependency order.

    When root is a freshly-built arith/math op tree (e.g. an
    arith.CmpiOp whose operands are a brand-new VarRefExprOp and
    arith.ConstantOp, built just for this one expression and never
    inserted into any block), every op it transitively depends on via a
    real SSA operand must be an explicit sibling in the same block as
    root -- xDSL's IsolatedFromAbove verifier rejects a region
    referencing a value whose defining op isn't itself a proper member
    of that same region (real MLIR semantics: an SSA edge alone isn't
    enough, the defining op must actually be placed in the IR tree).
    Already-attached operand providers (e.g. a block argument, or an op
    already inserted elsewhere in the real function body -- such as
    UnitConvertOp's own `source` operand) are left alone; only ops with
    no parent block get collected and placed alongside root.
    """
    seen: set[int] = set()
    order: list[Operation] = []

    def visit(op: Operation) -> None:
        if id(op) in seen:
            return
        seen.add(id(op))
        for operand in op.operands:
            owner = operand.owner
            if isinstance(owner, Operation) and owner.parent is None:
                visit(owner)
        order.append(op)

    visit(root)
    return order


def _single_op_region(ops: "list | None", *, required: bool = True) -> "Region":
    """Build a Region containing exactly one op (or zero, if required=False
    and ops is empty) -- the shared 'expression slot' shape for the new
    ccpp_utils expr-* ops that have no real SSA value to anchor an operand
    to. Raises ValueError on any other op count.

    Precedent for enforcing "exactly one op" despite IRDL enforcing
    nothing about region cardinality: CppStructDefOp.__init__ already
    raises ValueError for an invariant IRDL can't express.

    The single op given may itself be the root of a freshly-built
    arith/math expression tree (e.g. IfThenOp's new `condition_op` or
    UnitConvertOp's `conversion_op`) -- see _flatten_floating_deps for
    why its unattached operand-providing ops must also become block
    siblings here, not just the root itself.
    """
    from xdsl.ir import Block, Region

    ops = list(ops or [])
    if required and len(ops) != 1:
        raise ValueError(f"expected exactly one op in expression slot, got {len(ops)}")
    if not required and len(ops) > 1:
        raise ValueError(f"expected at most one op in expression slot, got {len(ops)}")
    if not ops:
        return Region([Block()])
    (root,) = ops
    return Region([Block(_flatten_floating_deps(root))])


@irdl_attr_definition
class RealKindType(ParametrizedAttribute, TypeAttribute):
    """MLIR type representing a Fortran real with a named kind qualifier.

    Used for Fortran code generation only — carries the kind name through
    the IR so the printer can emit 'real(kind=kind_name)' declarations.
    """

    name = "ccpp_utils.real_kind"
    kind_name: StringAttr = param_def()

    def __init__(self, kind_name: str | StringAttr):
        super().__init__(_coerce_str_attr(kind_name))


@irdl_attr_definition
class DerivedType(ParametrizedAttribute, TypeAttribute):
    """MLIR type representing a Fortran derived data type (DDT).

    Used for Fortran code generation only — carries the DDT name through
    the IR so the printer can emit 'type(type_name)' declarations.
    """

    name = "ccpp_utils.derived_type"
    type_name: StringAttr = param_def()

    def __init__(self, type_name: str | StringAttr):
        super().__init__(_coerce_str_attr(type_name))


@irdl_op_definition
class StrCmpOp(IRDLOperation):
    """String equality comparison.

    Two modes (enforced by verify_):
      - rhs/length mode: lhs and rhs are LLVMArrayType or MemRefType buffers;
        length is the number of bytes to compare.  literal must be absent.
        Emitted as: lhs .eq. rhs
      - literal mode: lhs is a MemRefType buffer; literal is a compile-time
        string constant.  rhs and length must be absent.
        Emitted as: trim(lhs) .eq. 'literal'

    Returns i1: 1 if equal, 0 if not.
    """

    name = "ccpp_utils.strcmp"

    lhs = operand_def(LLVMArrayType | MemRefType)
    rhs = opt_operand_def(LLVMArrayType | MemRefType)
    length = opt_prop_def(IntegerAttr)
    literal = opt_prop_def(StringAttr)
    res = result_def(i1)

    def __init__(
        self,
        lhs,
        rhs=None,
        length: int | None = None,
        literal: str | StringAttr | None = None,
    ):
        literal = _coerce_str_attr(literal)
        props: dict = {}
        if length is not None:
            props["length"] = IntegerAttr.from_int_and_width(length, 64)
        if literal is not None:
            props["literal"] = literal
        super().__init__(
            operands=[lhs, rhs],
            properties=props,
            result_types=[i1],
        )

    def verify_(self) -> None:
        has_rhs = self.rhs is not None
        has_length = self.length is not None
        has_literal = self.literal is not None
        if has_literal and (has_rhs or has_length):
            raise VerifyException(
                "StrCmpOp: literal cannot be combined with rhs or length"
            )
        if not has_literal and not (has_rhs and has_length):
            raise VerifyException(
                "StrCmpOp: must have either (rhs and length) or literal"
            )


@irdl_op_definition
class HostVarRefOp(IRDLOperation):
    """SSA reference to a host model module variable.

    Produces an SSA value of the given result type representing `var_name`
    from `module_name`.  No Fortran code is emitted — the printer registers
    `var_name` as the variable name for the result so that downstream ops
    (e.g. call arguments) print the correct host variable name.

    When `member_name` is set the variable is a DDT member accessed as
    ``var_name%member_name`` (e.g. ``phys_state%ps``).  The USE statement
    is still generated for `var_name` (the DDT instance), not the member.

    When `index_expr` is also set (real capgen-v1's multi-instance model:
    `var_name` is itself a HOST-owned array of DDT, one entry per model
    instance -- see cap_shared.py's _build_ddt_resolution_maps and
    run_dispatch.py's CCPP_INSTANCE_NUMBER_STD_NAME handling), the printed
    reference becomes ``var_name(index_expr)%member_name`` -- `var_name` is
    subscripted before the member access, matching real capgen-v1's own
    ``instance_data(instance)%data_array`` shape.

    A corresponding llvm.GlobalOp stub (with a 'module' attribute) is placed
    at the enclosing module level to drive 'use module, only: var' generation
    -- for `var_name` itself (the bare array/DDT name), never for `index_expr`.
    """

    name = "ccpp_utils.host_var_ref"

    var_name = prop_def(StringAttr)
    module_name = prop_def(StringAttr)
    # member_name and index_expr are stored in the attributes dict (not
    # formal properties): member_name when this op references a DDT member
    # (reference emitted as var_name%member_name), index_expr when var_name
    # is itself an array that must be subscripted first (see class docstring
    # -- not yet consumed by the printer).
    res = result_def()  # type set at construction to match callee expectation

    def __init__(
        self, var_name: str | StringAttr, module_name: str | StringAttr,
        result_type, member_name: str | None = None, index_expr: str | None = None,
    ):
        var_name = _coerce_str_attr(var_name)
        module_name = _coerce_str_attr(module_name)
        super().__init__(
            properties={"var_name": var_name, "module_name": module_name},
            result_types=[result_type],
        )
        if member_name is not None:
            self.attributes["member_name"] = StringAttr(member_name)
        if index_expr is not None:
            self.attributes["index_expr"] = StringAttr(index_expr)


@irdl_op_definition
class ClearStringOp(IRDLOperation):
    """Set a character buffer to an empty string: dest = ''"""

    name = "ccpp_utils.clear_string"

    dest = operand_def(MemRefType)

    def __init__(self, dest):
        super().__init__(operands=[dest])


@irdl_op_definition
class WriteErrMsgOp(IRDLOperation):
    """Write a formatted error message into an errmsg buffer.

    dest is a memref<512xi8> (errmsg buffer).
    var is a memref<?xi8> (the dynamic string part, will be trim()-ed).
    prefix and suffix are compile-time string literals.

    Printed as: write(dest, '(3a)') "prefix", trim(var), "suffix"
    """

    name = "ccpp_utils.write_errmsg"

    dest = operand_def(MemRefType)  # memref<512xi8>
    var = operand_def(MemRefType | LLVMArrayType)  # memref<?xi8> or !llvm.array<N x i8>
    prefix = prop_def(StringAttr)
    suffix = prop_def(StringAttr)

    def __init__(self, dest, var, prefix: str | StringAttr, suffix: str | StringAttr):
        prefix = _coerce_str_attr(prefix)
        suffix = _coerce_str_attr(suffix)
        super().__init__(
            operands=[dest, var],
            properties={"prefix": prefix, "suffix": suffix},
        )


@irdl_op_definition
class WriteStmtOp(IRDLOperation):
    """A Fortran formatted ``write`` statement with an arbitrary item list.

    Emits::

        write({dest}, '{format_spec}') {items[0]}, {items[1]}, ...

    Sibling of ``WriteErrMsgOp`` for files with no SSA locals to wrap in
    operands (e.g. ``constituent_cap.py`` -- "every reference is a plain
    text name," per ``TextBoundedDoLoopOp``'s own docstring): ``dest`` and
    every item are opaque text, same declaration-stays-text convention
    used throughout this codebase. Use ``WriteErrMsgOp`` instead when the
    dynamic part is a real SSA buffer value.
    """

    name = "ccpp_utils.write_stmt"

    dest        = prop_def(StringAttr)
    format_spec = prop_def(StringAttr)
    items       = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]

    def __init__(self, dest: str, format_spec: str, items: "list[str]"):
        super().__init__(properties={
            "dest":        StringAttr(dest),
            "format_spec": StringAttr(format_spec),
            "items":       ArrayAttr([StringAttr(i) for i in items]),
        })


@irdl_op_definition
class ArraySectionOp(IRDLOperation):
    """Represent a Fortran array section: source(lower0:upper0, lower1:upper1, ...).

    Used purely for Fortran code generation — no transformation semantics.
    The result type matches the source type.  The Fortran printer resolves the
    result to 'source_name(lower0:upper0, lower1:upper1)' so that downstream
    call ops emit the correct Fortran array-section notation.

    lowers and uppers must have the same length (one pair per dimension).
    """

    name = "ccpp_utils.array_section"

    source = operand_def(MemRefType)
    lowers = var_operand_def(MemRefType | IntegerType)
    uppers = var_operand_def(MemRefType | IntegerType)
    res = result_def(MemRefType)

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(self, source, lowers, uppers):
        source_val = SSAValue.get(source)
        super().__init__(
            operands=[source, list(lowers), list(uppers)],
            result_types=[source_val.type],
        )


@irdl_op_definition
class KindDefOp(IRDLOperation):
    """Declare a named Fortran kind parameter in the @ccpp_kinds module.

    Represents one ``integer, parameter :: kind_name = kind_value`` line in the
    generated ``ccpp_kinds`` Fortran module.  ``kind_name`` is the Fortran
    identifier (e.g. ``kind_phys``) and ``kind_value`` is its definition (e.g.
    ``REAL64`` from iso_fortran_env, or a spec name imported from a real
    host/scheme module).  ``kind_module`` names that source module --
    ``"iso_fortran_env"`` by default, matching this codebase's existing
    behavior when no metadata ``kind_spec`` resolved the kind instead.
    """

    name = "ccpp_utils.kind_def"

    kind_name = prop_def(StringAttr)
    kind_value = prop_def(StringAttr)
    kind_module = prop_def(StringAttr)

    def __init__(
        self,
        kind_name: str | StringAttr,
        kind_value: str | StringAttr,
        kind_module: str | StringAttr = "iso_fortran_env",
    ):
        kind_name = _coerce_str_attr(kind_name)
        kind_value = _coerce_str_attr(kind_value)
        kind_module = _coerce_str_attr(kind_module)
        super().__init__(
            properties={
                "kind_name": kind_name,
                "kind_value": kind_value,
                "kind_module": kind_module,
            }
        )


@irdl_op_definition
class SetStringOp(IRDLOperation):
    """Assign a string constant (llvm.array) into a character memref buffer.

    dest is a memref<?xi8> (character buffer).
    src is an !llvm.array<N x i8> obtained by loading a module-level global
    via llvm.mlir.addressof + llvm.load.

    No Fortran statement is emitted directly; the printer registers the global
    name as the variable name for dest so that a downstream memref.StoreOp into
    an allocatable can emit the correct assignment (e.g. suites(1) = str_name).
    """

    name = "ccpp_utils.set_string"

    dest = operand_def(MemRefType)  # memref<?xi8>
    src = operand_def(LLVMArrayType)  # !llvm.array<N x i8>

    def __init__(self, dest, src):
        super().__init__(operands=[dest, src])


@irdl_op_definition
class TrimOp(IRDLOperation):
    """Apply Fortran trim() to an assumed-length string memref.

    Used purely for Fortran code generation — the result carries the trimmed
    string expression through the IR so the printer emits 'trim(var_name)'
    wherever the result is used as a sub-expression.
    """

    name = "ccpp_utils.trim"

    lhs = operand_def(LLVMArrayType | MemRefType)
    res = result_def()

    def __init__(self, lhs):
        lhs_val = SSAValue.get(lhs)
        super().__init__(
            operands=[lhs],
            result_types=[lhs_val.type],
        )


@irdl_op_definition
class KeywordCallOp(IRDLOperation):
    """Fortran subroutine call with keyword (named) argument syntax.

    Used when one or more arguments are overridden with compile-time literal
    values.  All arguments — both SSA-sourced and literal-overridden — are
    printed with ``name=value`` syntax::

        call hello_scheme_run(var_a=92, ncol=ncol, lev=lev, errmsg=errmsg)

    Properties:
        callee:         The called subroutine name.
        operand_names:  Scheme parameter names for each SSA operand, in order.
        result_names:   Scheme parameter names for each SSA result, in order.
        overrides:      Compile-time literal overrides: {arg_name → value_str}.

    The printer deduplicates inout arguments (which appear in both operands
    and results) using a seen-names set.
    """

    name = "ccpp_utils.kw_call"

    callee = prop_def(StringAttr)
    operand_names = prop_def(ArrayAttr)
    result_names = prop_def(ArrayAttr)
    overrides = prop_def(DictionaryAttr)

    args = var_operand_def()
    res = var_result_def()

    def __init__(
        self,
        callee: str | StringAttr,
        operand_names: ArrayAttr,
        result_names: ArrayAttr,
        overrides: DictionaryAttr,
        args: list,
        out_types: list,
    ):
        callee = _coerce_str_attr(callee)
        super().__init__(
            operands=[args],
            properties={
                "callee": callee,
                "operand_names": operand_names,
                "result_names": result_names,
                "overrides": overrides,
            },
            result_types=[out_types],
        )

@irdl_op_definition
class AccDataBeginOp(IRDLOperation):
    """Emit !$acc data copy(...) copyin(...) copyout(...) present(...) directive."""
    name = "ccpp_utils.acc_data_begin"
    copy_arrays    = var_operand_def()   # arrays to copy both ways (inout)
    copyin_arrays  = var_operand_def()   # arrays to copy host → device only
    copyout_arrays = var_operand_def()   # arrays to copy device → host only
    present_arrays = var_operand_def()   # arrays asserted already on device

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(self, copy=None, copyin=None, copyout=None, present=None):
        super().__init__(operands=[
            list(copy    or []),
            list(copyin  or []),
            list(copyout or []),
            list(present or []),
        ])

@irdl_op_definition
class AccDataEndOp(IRDLOperation):
    """Emit !$acc end data directive."""
    name = "ccpp_utils.acc_data_end"

    def __init__(self):
        super().__init__()
@irdl_op_definition
class AccUpdateSelfOp(IRDLOperation):
    """Emit !$acc update self(...) — copies variables from GPU to CPU."""
    name = "ccpp_utils.acc_update_self"
    arrays = var_operand_def()   # SSA values from HostVarRefOp or ArraySectionOp

    def __init__(self, array_refs):
        super().__init__(operands=[list(array_refs)])

@irdl_op_definition
class AccUpdateDeviceOp(IRDLOperation):
    """Emit !$acc update device(...) — copies variables from CPU to GPU."""
    name = "ccpp_utils.acc_update_device"
    arrays = var_operand_def()   # SSA values from HostVarRefOp or ArraySectionOp

    def __init__(self, array_refs):
        super().__init__(operands=[list(array_refs)])

@irdl_op_definition
class AccEnterDataOp(IRDLOperation):
    """Emit !$acc enter data copyin(...) create(...) -- unstructured: no
    matching 'begin/end' pairing is enforced by the compiler, unlike
    AccDataBeginOp/AccDataEndOp. Must be balanced by hand with exactly one
    later AccExitDataOp on the same variables, or the device reference count
    never reaches zero (a silent per-run device-memory leak, not a compile
    or runtime error).

    copyin_arrays: host->device transfer, establishing residency for
        variables some caller reads before writing (needs_in).
    create_arrays: device allocation only, no initial transfer -- variables
        that are always written before being read (needs_in is False).
    """
    name = "ccpp_utils.acc_enter_data"
    copyin_arrays = var_operand_def()
    create_arrays = var_operand_def()

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(self, copyin=None, create=None):
        super().__init__(operands=[
            list(copyin or []),
            list(create or []),
        ])

@irdl_op_definition
class AccExitDataOp(IRDLOperation):
    """Emit !$acc exit data copyout(...) delete(...) -- unstructured, the
    exit half of an AccEnterDataOp/AccExitDataOp pair (see AccEnterDataOp).

    copyout_arrays: device->host transfer, then release residency --
        variables some caller reads back after the hoisted region closes
        (needs_out).
    delete_arrays: release residency only, no transfer back -- variables
        nothing reads back on the host side (needs_out is False). Still
        required to balance the matching AccEnterDataOp's reference count
        even though no data moves.
    """
    name = "ccpp_utils.acc_exit_data"
    copyout_arrays = var_operand_def()
    delete_arrays  = var_operand_def()

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(self, copyout=None, delete=None):
        super().__init__(operands=[
            list(copyout or []),
            list(delete or []),
        ])

@irdl_op_definition
class GPUDebugPrintOp(IRDLOperation):
    """Raw-text GPU residency diagnostic block (debug builds only -- see
    gpu_debug_print_pass.py, enabled by xdsl_ccpp's own --gpu-debug-prints
    CLI flag, never emitted otherwise).

    Follows the same raw-text-emission shape as RawFortranLinesOp/
    NonCamHostConstituentApiOp's type_defs (also plain strings, printed
    verbatim) rather than a fully-structured nested-region
    IR for the `!$acc parallel ... end parallel` block this needs --
    unnecessary complexity for a debug-only feature when a flat text block
    already has first-class printer support.

    `scratch_decls` is a semicolon-joined list of "name:fortran_type" pairs
    this block's own `text` references (e.g. "ccpp_dbg_sz1:integer") -- the
    printer declares these as ordinary local scalars alongside the
    function's other locals (print_ftn.py's _declare_fn_locals), since
    Fortran requires every declaration to precede all executable statements
    in a subprogram regardless of where in the executable section this op
    itself is inserted.

    `text` is the literal (possibly multi-line) Fortran source emitted
    verbatim at this point -- the assignments/parallel-region/write
    statements that do the actual diagnostic work.
    """

    name = "ccpp_utils.gpu_debug_print"

    scratch_decls = prop_def(StringAttr)
    text          = prop_def(StringAttr)

    def __init__(self, scratch_decls: "list[tuple[str, str]]", text: str):
        super().__init__(properties={
            "scratch_decls": StringAttr(";".join(f"{n}:{t}" for n, t in scratch_decls)),
            "text": StringAttr(text),
        })

@irdl_op_definition
class OmpTargetDataBeginOp(IRDLOperation):
    """Emit !$omp target data map(tofrom:...) map(alloc:...) directive."""
    name = "ccpp_utils.omp_target_data_begin"
    tofrom_arrays = var_operand_def()   # copy both ways (equivalent to copyin+copyout)
    alloc_arrays  = var_operand_def()   # already on device (equivalent to present)

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(self, tofrom=None, alloc=None):
        super().__init__(operands=[
            list(tofrom or []),
            list(alloc  or []),
        ])

@irdl_op_definition
class OmpTargetDataEndOp(IRDLOperation):
    """Emit !$omp end target data directive."""
    name = "ccpp_utils.omp_target_data_end"

    def __init__(self):
        super().__init__()

@irdl_op_definition
class OmpTargetUpdateFromOp(IRDLOperation):
    """Emit !$omp target update from(...) — copies variables from GPU to CPU."""
    name = "ccpp_utils.omp_target_update_from"
    arrays = var_operand_def()

    def __init__(self, array_refs):
        super().__init__(operands=[list(array_refs)])

@irdl_op_definition
class OmpTargetUpdateToOp(IRDLOperation):
    """Emit !$omp target update to(...) — copies variables from CPU to GPU."""
    name = "ccpp_utils.omp_target_update_to"
    arrays = var_operand_def()

    def __init__(self, array_refs):
        super().__init__(operands=[list(array_refs)])

@irdl_op_definition
class OmpTargetEnterDataOp(IRDLOperation):
    """Emit !$omp target enter data map(to:...) map(alloc:...) -- unstructured,
    the OMP equivalent of AccEnterDataOp (see there for the general
    unstructured-pairing caveat: must be balanced by hand with exactly one
    later OmpTargetExitDataOp on the same variables, or the device reference
    count never reaches zero).

    to_arrays: host->device transfer, establishing residency for variables
        some caller reads before writing (needs_in) -- OMP's map(to:...)
        is the direct equivalent of ACC's copyin(...).
    alloc_arrays: device allocation only, no initial transfer -- variables
        that are always written before being read (needs_in is False) --
        equivalent to ACC's create(...).
    """
    name = "ccpp_utils.omp_target_enter_data"
    to_arrays    = var_operand_def()
    alloc_arrays = var_operand_def()

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(self, to=None, alloc=None):
        super().__init__(operands=[
            list(to    or []),
            list(alloc or []),
        ])

@irdl_op_definition
class OmpTargetExitDataOp(IRDLOperation):
    """Emit !$omp target exit data map(from:...) map(release:...) --
    unstructured, the exit half of an OmpTargetEnterDataOp/OmpTargetExitDataOp
    pair (see OmpTargetEnterDataOp).

    from_arrays: device->host transfer, then release residency -- variables
        some caller reads back after the hoisted region closes (needs_out) --
        equivalent to ACC's copyout(...).
    release_arrays: release residency only, no transfer back -- variables
        nothing reads back on the host side (needs_out is False). Still
        required to balance the matching OmpTargetEnterDataOp's reference
        count even though no data moves. "release" (decrements the
        reference count, freeing only once it reaches zero) is the direct
        equivalent of ACC's delete(...) -- deliberately not OMP 5.0's
        stronger map(delete:...), which forces removal regardless of
        reference count and could tear down a mapping something else still
        expects to be live.
    """
    name = "ccpp_utils.omp_target_exit_data"
    from_arrays    = var_operand_def()
    release_arrays = var_operand_def()

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(self, from_=None, release=None):
        super().__init__(operands=[
            list(from_   or []),
            list(release or []),
        ])

@irdl_op_definition
class ModuleVarOp(IRDLOperation):
    """Unified module-level variable declaration, covering both real vars and
    DDT vars with a single consistent representation.

    Type is described by structured attributes so that language backends other
    than Fortran can interpret the type without parsing:

        base_type  — CCPP base type: "real", "integer", "character",
                     "logical", or "type" (for DDTs)
        kind       — optional kind name ("kind_phys") or character length ("512")
        ddt_name   — DDT type name when base_type == "type" (e.g. "vmr_type")
        is_pointer — True when the variable carries the Fortran POINTER attribute
        is_target  — True when the variable carries the Fortran TARGET attribute

    Printer emits in the module spec section before CONTAINS:
        rank=0: ``{type} :: {var_name}``
        rank>0: ``{type}, allocatable :: {var_name}(:, :, ...)``
        (is_pointer rank>0): ``{type}, pointer :: {var_name}(:) => null()``

    Examples::

        ModuleVarOp("temp_layer", "real", kind="kind_phys", rank=2)
        → real(kind=kind_phys), allocatable :: temp_layer(:, :)

        ModuleVarOp("vmr_cap_ddt_suite", "type", ddt_name="vmr_type")
        → type(vmr_type) :: vmr_cap_ddt_suite

        ModuleVarOp("lc_arr", "real", kind="kind_phys", is_target=True, rank=3)
        → real(kind=kind_phys), target, allocatable :: lc_arr(:, :, :)
    """

    name = "ccpp_utils.module_var"
    var_name   = prop_def(StringAttr)
    base_type  = prop_def(StringAttr)        # "real"|"integer"|"character"|"logical"|"type"
    kind       = opt_prop_def(StringAttr)    # kind name or char length; None if not applicable
    ddt_name   = opt_prop_def(StringAttr)    # DDT type name when base_type == "type"
    is_pointer = opt_prop_def(BoolAttr)      # True → Fortran POINTER attribute
    is_target  = opt_prop_def(BoolAttr)      # True → Fortran TARGET attribute
    rank       = prop_def(IntegerAttr)       # 0 = scalar, >0 = allocatable array
    fixed_dim  = opt_prop_def(IntegerAttr)   # if set: fixed-size non-allocatable 1D array
    init_value = opt_prop_def(StringAttr)    # optional Fortran initializer (for fixed_dim vars)
    # lang-neutral-expr-ir Stage 3a: structured alternative to init_value,
    # pass init_value_op= instead. At most one of the two may be given.
    # Kept as an independent opt slot (not exactly-one) since most real
    # call sites set neither.
    init_value_region = opt_region_def("single_block")
    needs_device_residency = opt_prop_def(BoolAttr)  # True -> also emit a
                                # module-level `!$acc declare create(var_name)`
                                # (guarded by #ifdef USE_GPU) right alongside
                                # this declaration. A runtime `!$acc enter
                                # data create(...)` inside a later subroutine
                                # (see LazyAllocOp) establishes the actual
                                # device buffer, but for a module-scope
                                # ALLOCATABLE array referenced across many
                                # separate, later subroutine calls over the
                                # life of the run (unlike a single lexically-
                                # scoped `!$acc data` region), nvfortran needs
                                # this companion `declare create` at the
                                # point of declaration itself, or the array's
                                # device-side descriptor/size is undefined --
                                # confirmed as the actual cause of a
                                # "PRESENT clause was not found on device"
                                # runtime failure for a SuiteOwned scratch
                                # array even after its enter-data-create/
                                # update-device calls were verified compiling
                                # and executing correctly.

    traits = traits_def(NoTerminator())

    def __init__(
        self,
        var_name: str,
        base_type: str,
        *,
        kind: str | None = None,
        ddt_name: str | None = None,
        is_pointer: bool = False,
        is_target: bool = False,
        rank: int = 0,
        fixed_dim: int | None = None,
        init_value: str | None = None,
        init_value_op=None,
        needs_device_residency: bool = False,
    ):
        if init_value is not None and init_value_op is not None:
            raise ValueError("ModuleVarOp: pass at most one of init_value or init_value_op")
        props: dict = {
            "var_name":  StringAttr(var_name),
            "base_type": StringAttr(base_type),
            "rank":      IntegerAttr.from_int_and_width(rank, 64),
        }
        if kind is not None:
            props["kind"] = StringAttr(kind)
        if ddt_name is not None:
            props["ddt_name"] = StringAttr(ddt_name)
        if is_pointer:
            props["is_pointer"] = BoolAttr.from_bool(True)
        if is_target:
            props["is_target"] = BoolAttr.from_bool(True)
        if fixed_dim is not None:
            props["fixed_dim"] = IntegerAttr.from_int_and_width(fixed_dim, 64)
        init_region = None
        if init_value is not None:
            props["init_value"] = StringAttr(init_value)
        elif init_value_op is not None:
            init_region = _single_op_region([init_value_op])
        if needs_device_residency:
            props["needs_device_residency"] = BoolAttr.from_bool(True)
        super().__init__(properties=props, regions=[init_region])


@irdl_op_definition
class LazyAllocOp(IRDLOperation):
    """Allocate a module-level array on its first use and initialize it.

    Emitted inside _suite_physics before the first scheme call:
        if (.not. allocated(var_name)) then
          allocate(var_name(d1, d2, ...))
          var_name = init_value
    #ifdef USE_GPU
          !$acc enter data create(var_name)
    #endif
        end if

    dim_vars are SSA values whose variable names supply the dimension extents.

    needs_device_residency (SuiteOwned GPU residency): when set, the printer
    also emits the enter-data-create line above, INSIDE this same
    `if (.not. allocated(...))` block -- deliberately not a separately
    inserted AccEnterDataOp, since this array can be allocated from either
    of two lifecycle functions (_suite_register/_suite_initialize, whichever
    runs first at simulation start), each emitting its own LazyAllocOp for
    the same var. A separate, unconditionally-inserted enter-data op after
    each occurrence would double-fire (both would execute regardless of
    which one's allocate actually ran), double-incrementing the OpenACC
    reference count. Baking it into this op's own printer means it inherits
    the exact same "already done" runtime guard the allocate itself uses,
    with no extra bookkeeping.
    """

    name = "ccpp_utils.lazy_alloc"
    var_name   = prop_def(StringAttr)
    kind_name  = prop_def(StringAttr)
    init_value = opt_prop_def(StringAttr)  # Fortran literal, e.g. "0.0_kind_phys"
    needs_device_residency = opt_prop_def(BoolAttr)
    is_run_local = opt_prop_def(BoolAttr)  # when True: plain allocate(), no lazy guard
    dim_vars   = var_operand_def()          # SSA values giving dimension sizes

    def __init__(self, var_name: str, kind_name: str, dim_var_refs: list,
                 init_value: str | None = None,
                 needs_device_residency: bool = False,
                 is_run_local: bool = False):
        props: dict = {
            "var_name":  StringAttr(var_name),
            "kind_name": StringAttr(kind_name),
        }
        if init_value is not None:
            props["init_value"] = StringAttr(init_value)
        if needs_device_residency:
            props["needs_device_residency"] = BoolAttr.from_bool(needs_device_residency)
        if is_run_local:
            props["is_run_local"] = BoolAttr.from_bool(True)
        super().__init__(operands=[dim_var_refs], properties=props)


@irdl_op_definition
class SafeDeallocOp(IRDLOperation):
    """Deallocate a module-level array if it is currently allocated.

    Emitted inside _suite_timestep_final:
        if (allocated(var_name)) deallocate(var_name)
    """

    name = "ccpp_utils.safe_dealloc"
    var_name = prop_def(StringAttr)

    def __init__(self, var_name: str):
        super().__init__(properties={"var_name": StringAttr(var_name)})


@irdl_op_definition
class RankReducingSliceOp(IRDLOperation):
    """General rank-reducing Fortran array section.

    Each dimension of the source array is described by the ``dim_pattern``
    property as either a range (``'R'``) or a scalar index (``'S'``):

    - ``'R'`` — dimension is kept as a range ``lower:upper`` (rank preserved)
    - ``'S'`` — dimension is fixed to a scalar index (rank reduced by 1)

    Operands are grouped into two variadic lists, matched left-to-right as
    the pattern is scanned:
    - ``range_lowers`` / ``range_uppers`` — one pair per ``'R'`` in pattern
    - ``scalar_indices``                  — one value per ``'S'`` in pattern

    Examples::

        dim_pattern="RS", range=(col_start,col_end), scalar=(lev,)
            → source(col_start:col_end, lev)          2D→1D (common CCPP case)

        dim_pattern="SR", scalar=(lev,), range=(col_start,col_end)
            → source(lev, col_start:col_end)          2D→1D (reversed axes)

        dim_pattern="RSS", range=(col_start,col_end), scalar=(lev,spec)
            → source(col_start:col_end, lev, spec)    3D→1D

        dim_pattern="RSR", range=(cs,ce,ss,se), scalar=(lev,)
            → source(cs:ce, lev, ss:se)               3D→2D

    The result rank equals the number of ``'R'`` entries in ``dim_pattern``.
    """

    name = "ccpp_utils.rank_reducing_slice"

    source        = operand_def(MemRefType)
    range_lowers  = var_operand_def(MemRefType)   # lower bound per 'R' dimension
    range_uppers  = var_operand_def(MemRefType)   # upper bound per 'R' dimension
    scalar_indices = var_operand_def(MemRefType)  # scalar index per 'S' dimension
    # e.g. "RS" = first dim is range, second dim is scalar
    dim_pattern   = prop_def(StringAttr)
    res           = result_def(MemRefType)

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(
        self,
        source,
        dim_pattern: str,
        range_lowers: list,
        range_uppers: list,
        scalar_indices: list,
    ):
        source_val = SSAValue.get(source)
        src_type = source_val.type
        # Result rank = number of 'R' entries; each retained dimension is dynamic.
        result_rank = dim_pattern.count("R")
        if isinstance(src_type, MemRefType):
            result_type = MemRefType(
                src_type.element_type, [DYNAMIC_INDEX] * result_rank
            )
        else:
            result_type = src_type
        super().__init__(
            operands=[source, list(range_lowers), list(range_uppers),
                      list(scalar_indices)],
            properties={"dim_pattern": StringAttr(dim_pattern)},
            result_types=[result_type],
        )


@irdl_op_definition
class PromotionLoopOp(IRDLOperation):
    """Fortran do loop for CCPP variable promotion.

    Generates::

        do {loop_var_name} = 1, upper_bound_val
          ... body ...
        end do

    ``loop_var`` is a scalar integer alloca whose name_hint becomes the
    Fortran loop variable name.  ``upper_bound`` is the integer value to
    loop to (inclusive), e.g. the SSA value of ``pver``.

    The body region contains scheme call ops.  Inside those calls,
    RankReducingSliceOp operands reference ``loop_var`` (via LoadOp) to
    produce column-slice expressions like ``arr(col_start:col_end, lev_idx)``.
    """

    name = "ccpp_utils.promotion_loop"

    loop_var    = operand_def(MemRefType)  # integer alloca; name_hint = loop var name
    upper_bound = operand_def(MemRefType)  # integer value giving loop upper bound
    body        = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, loop_var, upper_bound, body_ops):
        super().__init__(
            operands=[loop_var, upper_bound],
            regions=[body_ops],
        )


@irdl_op_definition
class SubcycleLoopOp(IRDLOperation):
    """Fortran do loop for CCPP subcycle blocks.

    Generates::

        do {loop_var_name} = 1, <loop_count>
          ... body ...
        end do

    ``loop_var`` is a scalar integer alloca whose name_hint becomes the
    Fortran loop variable name.  ``loop_count`` is either a literal integer
    from ``loop="N"`` in the suite XML or a CCPP standard name resolved at
    runtime; ``is_literal`` records which case applies.
    """

    name = "ccpp_utils.subcycle_loop"

    loop_count = prop_def(StringAttr)
    is_literal = prop_def(BoolAttr)
    loop_var   = operand_def(MemRefType)

    body = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, loop_count: "int | str", loop_var, body_ops,
                 is_literal: bool = True):
        if isinstance(body_ops, list):
            from xdsl.ir import Block, Region
            body = Region([Block(body_ops)])
        else:
            body = body_ops
        super().__init__(
            operands=[loop_var],
            properties={
                "loop_count": StringAttr(str(loop_count)),
                "is_literal": BoolAttr.from_bool(is_literal),
            },
            regions=[body],
        )


@irdl_op_definition
class PresentCheckOp(IRDLOperation):
    """Fortran if (present(var)) / else / end if for optional promoted args.

    Generates::

        if (present({var_name})) then
          ... with_body ...
        else
          ... without_body ...
        end if

    ``var_name`` is the bare Fortran variable name used in the present() test.
    ``with_body`` contains the slice op(s) + scheme call that include the
    optional arg.  ``without_body`` contains the scheme call that omits it.
    """

    name = "ccpp_utils.present_check"

    var_name = prop_def(StringAttr)

    with_body    = region_def("single_block")
    without_body = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, var_name: str, with_body_ops: list, without_body_ops: list):
        super().__init__(
            properties={"var_name": StringAttr(var_name)},
            regions=[with_body_ops, without_body_ops],
        )


@irdl_op_definition
class ActiveCheckOp(IRDLOperation):
    """Fortran if (<condition>) / else / end if for an 'active'-gated optional arg.

    Generates::

        if ({condition_expr}) then
          ... with_body ...
        else
          ... without_body ...
        end if

    Distinct from PresentCheckOp: this tests an arbitrary host-declared
    Fortran logical expression (from an ArgumentOp's own 'active' property,
    e.g. 'flag_for_opt_arg', copied onto a matched scheme arg as
    model_var_active_expr by HostVariableMatchPass), not whether the current
    subroutine's own optional dummy argument was passed by its caller --
    conceptually related but a different runtime condition, so kept as a
    separate op rather than generalizing PresentCheckOp.

    ``condition_expr`` is printed verbatim as the if-condition. ``with_body``
    contains the slice op(s) + scheme call that include the active-gated
    arg(s). ``without_body`` contains the scheme call that omits them.

    lang-neutral-expr-ir Stage 3a adds a structured alternative to the
    opaque ``condition_expr`` text, same shape as ``IfThenOp``'s own:
    pass ``condition_op`` instead. Exactly one of the two must be given;
    the opaque-text form remains fully supported so suite_cap.py's own
    caller is unaffected.
    """

    name = "ccpp_utils.active_check"

    condition_expr = opt_prop_def(StringAttr)
    condition = opt_region_def("single_block")

    with_body    = region_def("single_block")
    without_body = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self, condition_expr: "str | None" = None, with_body_ops: "list | None" = None,
        without_body_ops: "list | None" = None, *, condition_op=None,
    ):
        if (condition_expr is None) == (condition_op is None):
            raise ValueError(
                "ActiveCheckOp: pass exactly one of condition_expr or condition_op"
            )
        props: dict = {}
        cond_region = None
        if condition_expr is not None:
            props["condition_expr"] = _coerce_str_attr(condition_expr)
        else:
            cond_region = _single_op_region([condition_op])
        super().__init__(
            properties=props,
            regions=[cond_region, with_body_ops or [], without_body_ops or []],
        )


@irdl_op_definition
class NullifyPointerOp(IRDLOperation):
    """Null-initialise a Fortran POINTER variable.

    Emits::

        nullify({ptr_name})
    """

    name = "ccpp_utils.nullify_pointer"
    ptr_name = prop_def(StringAttr)

    def __init__(self, ptr_name: str):
        super().__init__(properties={"ptr_name": StringAttr(ptr_name)})


@irdl_op_definition
class AllocateOp(IRDLOperation):
    """Allocate a Fortran allocatable or pointer variable, with an
    optional shape and an optional STAT= clause.

    Emits, with one or more ``dims`` (an array/array-of-arrays allocation)::

        allocate({var_name}({dims[0]}, {dims[1]}, ...)[, stat={stat_var}])

    or, with zero ``dims`` (a scalar allocatable/pointer allocation, e.g.
    a derived-type pointer target)::

        allocate({var_name}[, stat={stat_var}])

    ``dims`` is an ArrayAttr of StringAttr Fortran expressions (e.g.
    ``"ncols"``, ``"size(lc_const_props)"``). ``stat_var`` is the
    STAT= clause's variable name (opaque text, same declaration-stays-text
    convention as everywhere else in this codebase) -- covers the
    recurring ``allocate(const_prop, stat=errcode)`` idiom, previously a
    one-off ``RawFortranLinesOp`` leaf.

    lang-neutral-expr-ir Stage 3a adds a structured alternative for
    ``dims`` (same shape as other ops in this round): pass ``dim_ops``
    (a list of expression ops, one per dimension) instead. ``var_name``
    and ``stat_var`` stay plain text -- every real call site uses a bare
    variable name for both, never a computed expression.
    """

    name = "ccpp_utils.allocate"
    var_name = prop_def(StringAttr)
    dims     = opt_prop_def(ArrayAttr)   # legacy ArrayAttr[StringAttr]
    dims_region = var_region_def("single_block")   # structured dim expr ops
    stat_var = opt_prop_def(StringAttr)

    traits = traits_def(NoTerminator())

    def __init__(
        self, var_name: str, dims: "list[str] | None" = None,
        stat_var: "str | None" = None, *, dim_ops: "list | None" = None,
    ):
        if dims is not None and dim_ops is not None:
            raise ValueError("AllocateOp: pass at most one of dims or dim_ops")
        props: dict = {"var_name": StringAttr(var_name)}
        if dim_ops is not None:
            dims_regions = [_single_op_region([d]) for d in dim_ops]
        else:
            props["dims"] = ArrayAttr([StringAttr(d) for d in (dims or [])])
            dims_regions = []
        if stat_var is not None:
            props["stat_var"] = StringAttr(stat_var)
        super().__init__(properties=props, regions=[dims_regions])


@irdl_op_definition
class ZeroFillOp(IRDLOperation):
    """Assign 0.0_kind_phys to a real array variable.

    Emits::

        {var_name} = 0.0_kind_phys
    """

    name = "ccpp_utils.zero_fill"
    var_name = prop_def(StringAttr)

    def __init__(self, var_name: str):
        super().__init__(properties={"var_name": StringAttr(var_name)})


@irdl_op_definition
class PointerSliceAssignOp(IRDLOperation):
    """Associate a pointer with a trailing-index slice of a 3-D array.

    Emits::

        {ptr_name} => {array_name}(:, :, {index_var})

    Used to assign constituent-tendency pointer slices into ``lc_const_tend``.
    """

    name = "ccpp_utils.pointer_slice_assign"
    ptr_name   = prop_def(StringAttr)
    array_name = prop_def(StringAttr)
    index_var  = prop_def(StringAttr)

    def __init__(self, ptr_name: str, array_name: str, index_var: str):
        super().__init__(properties={
            "ptr_name":   StringAttr(ptr_name),
            "array_name": StringAttr(array_name),
            "index_var":  StringAttr(index_var),
        })


@irdl_op_definition
class PointerAssignOp(IRDLOperation):
    """Associate a pointer with an arbitrary right-hand-side expression.

    Emits::

        {ptr_name} => {rhs_expr}

    ``rhs_expr`` is printed verbatim -- deliberately general (a bare
    pointer name, a type-bound function-call result, a DDT member access,
    etc.), since composing a fully-structured RHS expression is out of
    scope here. Distinct from PointerSliceAssignOp (which has a fixed
    ``{ptr} => {array}(:, :, {index_var})`` shape); use that one instead
    when the RHS really is a trailing-index 3-D slice.

    lang-neutral-expr-ir Stage 3a adds a structured alternative for
    ``rhs_expr`` (same shape as other ops in this round): pass
    ``rhs_expr_op`` instead. ``ptr_name`` stays plain text -- every real
    call site uses a bare pointer-variable name, never a computed
    expression, so there is nothing for a structured form to buy there.
    """

    name = "ccpp_utils.pointer_assign"
    ptr_name = prop_def(StringAttr)
    rhs_expr = opt_prop_def(StringAttr)
    rhs_expr_region = opt_region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, ptr_name: str, rhs_expr: "str | None" = None, *, rhs_expr_op=None):
        if (rhs_expr is None) == (rhs_expr_op is None):
            raise ValueError(
                "PointerAssignOp: pass exactly one of rhs_expr or rhs_expr_op"
            )
        props: dict = {"ptr_name": StringAttr(ptr_name)}
        rhs_region = None
        if rhs_expr is not None:
            props["rhs_expr"] = StringAttr(rhs_expr)
        else:
            rhs_region = _single_op_region([rhs_expr_op])
        super().__init__(properties=props, regions=[rhs_region])


@irdl_op_definition
class AssignOp(IRDLOperation):
    """A plain (non-pointer) scalar or array-element assignment statement.

    Emits::

        {lhs_expr} = {rhs_expr}

    Both sides are printed verbatim -- this deliberately does not attempt
    to structurally model the assigned expression; a real language-neutral
    expression IR (distinguishing operators/literals/references instead of
    opaque text) is a separate, much larger effort. Covers plain-value
    assignment; use PointerAssignOp/PointerSliceAssignOp instead for `=>`
    pointer association.
    """

    name = "ccpp_utils.assign"
    lhs_expr = prop_def(StringAttr)
    rhs_expr = prop_def(StringAttr)

    def __init__(self, lhs_expr: str, rhs_expr: str):
        super().__init__(properties={
            "lhs_expr": StringAttr(lhs_expr),
            "rhs_expr": StringAttr(rhs_expr),
        })


@irdl_op_definition
class DdtMethodCallOp(IRDLOperation):
    """Call a type-bound procedure on a DDT object, with positional and/or
    keyword arguments.

    Emits::

        call {obj_expr}%{method}({args joined with kwargs, comma-separated})

    ``obj_expr`` is the object expression text (may itself be a resolved
    reference like ``lc_instances(instance)%cam_constituents_obj``).
    ``args`` are positional argument expressions; ``kwargs`` are already-
    formatted ``name=expr`` strings. Distinct from CamDirectCallOp (a plain
    ``call {callee}(...)`` with positional-only args, no ``%`` receiver
    convention implied) and from ConstituentIndexLookupOp (an unrelated,
    fixed-shape batch lookup via the free function
    ``ccpp_constituent_indices(...)`` -- do not confuse the two).

    lang-neutral-expr-ir Stage 3a adds a structured alternative for each
    of the three text slots independently (object expression, positional
    args, keyword args) -- not one all-or-nothing switch, since real call
    sites mix e.g. a plain-text ``obj_expr`` with structured ``kwargs``.
    Pass ``obj_expr_op`` instead of ``obj_expr``; ``arg_ops`` instead of
    ``args``; ``kwarg_ops`` (a list of ``KeywordArgExprOp``) instead of
    ``kwargs``. Each slot accepts at most one of its two forms.
    """

    name = "ccpp_utils.ddt_method_call"
    obj_expr = opt_prop_def(StringAttr)
    obj_expr_region = opt_region_def("single_block")
    method   = prop_def(StringAttr)
    args     = opt_prop_def(ArrayAttr)   # legacy ArrayAttr[StringAttr], positional
    args_region = var_region_def("single_block")   # structured positional arg exprs
    kwargs   = opt_prop_def(ArrayAttr)   # legacy ArrayAttr[StringAttr], "name=expr"
    kwargs_region = var_region_def("single_block")  # structured KeywordArgExprOp children

    irdl_options = [AttrSizedRegionSegments()]
    traits = traits_def(NoTerminator())

    def __init__(
        self, obj_expr: "str | None" = None, method: str = "",
        args: "list[str] | None" = None, kwargs: "list[str] | None" = None,
        *, obj_expr_op=None, arg_ops: "list | None" = None, kwarg_ops: "list | None" = None,
    ):
        if (obj_expr is None) == (obj_expr_op is None):
            raise ValueError(
                "DdtMethodCallOp: pass exactly one of obj_expr or obj_expr_op"
            )
        if args is not None and arg_ops is not None:
            raise ValueError("DdtMethodCallOp: pass at most one of args or arg_ops")
        if kwargs is not None and kwarg_ops is not None:
            raise ValueError("DdtMethodCallOp: pass at most one of kwargs or kwarg_ops")

        props: dict = {}
        obj_region = None
        if obj_expr is not None:
            props["obj_expr"] = StringAttr(obj_expr)
        else:
            obj_region = _single_op_region([obj_expr_op])
        props["method"] = StringAttr(method)
        if arg_ops is not None:
            args_regions = [_single_op_region([a]) for a in arg_ops]
        else:
            props["args"] = ArrayAttr([StringAttr(a) for a in (args or [])])
            args_regions = []
        if kwarg_ops is not None:
            kwargs_regions = [_single_op_region([k]) for k in kwarg_ops]
        else:
            props["kwargs"] = ArrayAttr([StringAttr(k) for k in (kwargs or [])])
            kwargs_regions = []

        super().__init__(
            properties=props,
            regions=[obj_region, args_regions, kwargs_regions],
        )


@irdl_op_definition
class ErrorGuardOp(IRDLOperation):
    """Early-return guard: if NOT condition, set error state and return.

    Emits::

        if (.not. {condition}) then
          {errflg_var} = 1
          {errmsg_var} = '{errmsg_text}'
          return
        end if

    Replaces constituent_cap.py's own ``_error_guard()`` Python helper,
    which built exactly this 5-line block as a joined string.

    lang-neutral-expr-ir Stage 3a adds a structured alternative to the
    opaque ``condition`` text (same shape as ``IfThenOp``'s own): pass
    ``condition_op`` instead. Exactly one of the two must be given.
    ``errmsg_text`` stays a plain string in both cases -- every real call
    site uses a static literal message, never a computed expression, so
    there is nothing for a structured form to buy here.
    """

    name = "ccpp_utils.error_guard"
    condition   = opt_prop_def(StringAttr)
    condition_region = opt_region_def("single_block")
    errmsg_text = prop_def(StringAttr)
    errflg_var  = opt_prop_def(StringAttr)  # default "errflg" if unset
    errmsg_var  = opt_prop_def(StringAttr)  # default "errmsg" if unset

    traits = traits_def(NoTerminator())

    def __init__(
        self, condition: "str | None" = None, errmsg_text: "str | None" = None,
        errflg_var: str = "errflg", errmsg_var: str = "errmsg", *, condition_op=None,
    ):
        if (condition is None) == (condition_op is None):
            raise ValueError(
                "ErrorGuardOp: pass exactly one of condition or condition_op"
            )
        props: dict = {}
        cond_region = None
        if condition is not None:
            props["condition"] = _coerce_str_attr(condition)
        else:
            cond_region = _single_op_region([condition_op])
        props["errmsg_text"] = StringAttr(errmsg_text)
        if errflg_var != "errflg":
            props["errflg_var"] = StringAttr(errflg_var)
        if errmsg_var != "errmsg":
            props["errmsg_var"] = StringAttr(errmsg_var)
        super().__init__(properties=props, regions=[cond_region])


@irdl_op_definition
class IfThenOp(IRDLOperation):
    """A single-branch Fortran conditional, no ``else``.

    Emits::

        if ({condition_expr}) then
          {body}
        end if

    Distinct from PresentCheckOp/ActiveCheckOp, which always emit both an
    ``if`` and an ``else`` branch -- forcing a body through either of those
    with an empty ``without_body_ops`` would print a stray empty ``else``
    this op avoids entirely.

    lang-neutral-expr-ir Stage 3a adds a structured alternative to the
    opaque ``condition_expr`` text: pass ``condition_op`` (any
    print_expr-dispatchable expression op -- e.g. a ``CallExprOp``, or an
    ``arith.CmpiOp``/``OrIOp`` tree built over ``VarRefExprOp``/
    ``MemberAccessExprOp`` leaves) instead. Exactly one of the two must
    be given; the opaque-text form remains fully supported so every
    existing caller (this file's own multi-instance guards, and
    cpp_interop.py's chost cap) is unaffected.
    """

    name = "ccpp_utils.if_then"
    condition_expr = opt_prop_def(StringAttr)
    condition = opt_region_def("single_block")
    body = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self, condition_expr: "str | None" = None, body_ops: "list | None" = None,
        *, condition_op=None,
    ):
        if (condition_expr is None) == (condition_op is None):
            raise ValueError(
                "IfThenOp: pass exactly one of condition_expr or condition_op"
            )
        from xdsl.ir import Block, Region
        props: dict = {}
        cond_region = None
        if condition_expr is not None:
            props["condition_expr"] = _coerce_str_attr(condition_expr)
        else:
            cond_region = _single_op_region([condition_op])
        super().__init__(
            properties=props,
            regions=[cond_region, Region([Block(body_ops or [])])],
        )


@irdl_op_definition
class TextBoundedDoLoopOp(IRDLOperation):
    """Fortran ``do {loop_var} = 1, {upper_expr}`` whose trip count is a
    runtime Fortran text expression (e.g. ``size(x)``), not an SSA value.

    Emits::

        do {loop_var} = 1, {upper_expr}
          {body}
        end do

    Distinct from PromotionLoopOp/SubcycleLoopOp, which loop over SSA-valued
    bounds -- constituent_cap.py has no SSA values for its locals at all
    (every reference is a plain text name via its own ``ref()`` helper), so
    those two ops don't apply here.
    """

    name = "ccpp_utils.text_bounded_do_loop"
    loop_var   = prop_def(StringAttr)
    upper_expr = prop_def(StringAttr)
    body       = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, loop_var: str, upper_expr: str, body_ops: list):
        from xdsl.ir import Block, Region
        super().__init__(
            properties={
                "loop_var":   StringAttr(loop_var),
                "upper_expr": StringAttr(upper_expr),
            },
            regions=[Region([Block(body_ops)])],
        )


@irdl_op_definition
class ScopedBlockOp(IRDLOperation):
    """Fortran BLOCK construct introducing a local scope with declarations.

    Emits::

        block
          {local_decls[0]}
          {local_decls[1]}
          ...
          {body ops}
        end block

    ``local_decls`` is an ArrayAttr of StringAttr complete Fortran declaration
    lines (e.g. ``"integer :: lc_tend_idx"``).  Body ops are emitted at +1
    indent after the declarations.
    """

    name = "ccpp_utils.scoped_block"

    local_decls = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    body        = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, local_decls: "list[str]", body_ops: list):
        from xdsl.ir import Block, Region
        body = Region([Block(body_ops)])
        super().__init__(
            properties={"local_decls": ArrayAttr([StringAttr(d) for d in local_decls])},
            regions=[body],
        )


@irdl_op_definition
class RawFortranLinesOp(IRDLOperation):
    """Escape hatch for Fortran content not yet converted to structured ops.

    The ``lines`` property holds raw Fortran text (one or more lines, newline-
    separated).  The printer emits each line at the current indentation level;
    preprocessor directives (starting with ``#``) are emitted at column 0.
    """

    name = "ccpp_utils.raw_fortran_lines"

    lines = prop_def(StringAttr)

    def __init__(self, text: str):
        super().__init__(properties={"lines": StringAttr(text)})


@irdl_op_definition
class ConstituentFunctionOp(IRDLOperation):
    """One subroutine or function in the constituent registration API.

    ``fn_name``     — Fortran identifier of the subroutine/function.
    ``is_function`` — True for FUNCTION, False for SUBROUTINE.
    ``args``        — argument names for the signature line.
    ``use_stmts``   — complete USE statement lines (no trailing newline).
    ``arg_decls``   — argument declaration lines (no leading/trailing whitespace).
    ``local_decls`` — local variable declaration lines.
    ``result_name`` — (functions only) name of the RESULT variable.
    ``result_decl`` — (functions only) type declaration for the result variable.
    ``body``        — single-block Region of statement ops.
    """

    name = "ccpp_utils.constituent_function"

    fn_name     = prop_def(StringAttr)
    is_function = prop_def(BoolAttr)
    args        = prop_def(ArrayAttr)   # ArrayAttr[StringAttr] — arg name list
    use_stmts   = prop_def(ArrayAttr)   # ArrayAttr[StringAttr] — USE statement lines
    arg_decls   = prop_def(ArrayAttr)   # ArrayAttr[StringAttr] — argument declaration lines
    local_decls = prop_def(ArrayAttr)   # ArrayAttr[StringAttr] — local variable declarations
    result_name = opt_prop_def(StringAttr)  # for functions: result variable name
    result_decl = opt_prop_def(StringAttr)  # for functions: result variable type declaration
    body        = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self,
        fn_name: str,
        is_function: bool,
        args: "list[str]",
        use_stmts: "list[str]",
        arg_decls: "list[str]",
        local_decls: "list[str]",
        body_ops: list,
        result_name: "str | None" = None,
        result_decl: "str | None" = None,
    ):
        from xdsl.ir import Block, Region
        body = Region([Block(body_ops)])
        props: dict = {
            "fn_name":     StringAttr(fn_name),
            "is_function": BoolAttr.from_bool(is_function),
            "args":        ArrayAttr([StringAttr(a) for a in args]),
            "use_stmts":   ArrayAttr([StringAttr(u) for u in use_stmts]),
            "arg_decls":   ArrayAttr([StringAttr(d) for d in arg_decls]),
            "local_decls": ArrayAttr([StringAttr(d) for d in local_decls]),
        }
        if result_name is not None:
            props["result_name"] = StringAttr(result_name)
        if result_decl is not None:
            props["result_decl"] = StringAttr(result_decl)
        super().__init__(properties=props, regions=[body])


@irdl_op_definition
class BindCSubroutineOp(IRDLOperation):
    """A Fortran subroutine or function with a ``bind(C, name='...')``
    interface, e.g. the chost BIND(C) cap's own per-lifecycle entry
    points and its constituent-query functions.

    ``fn_name``     — Fortran identifier of the subroutine/function.
    ``bind_name``   — the C-visible symbol name (``bind(C, name=...)``).
    ``is_function`` — True for FUNCTION, False (default) for SUBROUTINE.
    ``args``        — argument names for the signature line (printer
                       column-wraps this across Fortran continuation
                       lines when it would otherwise exceed the line
                       budget -- see the shared ``wrap_paren_list``
                       helper in print_ftn.py).
    ``arg_decls``   — argument declaration lines.
    ``local_decls`` — local variable declaration lines.
    ``result_name`` — (functions only) name of the RESULT variable.
    ``result_decl`` — (functions only) type declaration for the result
                       variable.
    ``body``        — single-block Region of statement ops.

    Distinct from ConstituentFunctionOp (no bind(C) support, and its
    printer joins the argument list on one line with no wrapping at all
    -- retrofitting it risked destabilizing its own already-proven output
    format across every existing caller, so this is a separate op rather
    than an extension). ``is_function``/``result_name``/``result_decl``
    were added here rather than on a third op since this op had zero real
    callers yet when the chost constituent-query functions (which need
    both RESULT(...) and bind(C) together) were reached -- no proven
    output format at risk.
    """

    name = "ccpp_utils.bind_c_subroutine"

    fn_name     = prop_def(StringAttr)
    bind_name   = prop_def(StringAttr)
    is_function = prop_def(BoolAttr)
    args        = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    arg_decls   = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    local_decls = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    result_name = opt_prop_def(StringAttr)
    result_decl = opt_prop_def(StringAttr)
    body        = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self,
        fn_name: str,
        bind_name: str,
        args: "list[str]",
        arg_decls: "list[str]",
        local_decls: "list[str]",
        body_ops: list,
        is_function: bool = False,
        result_name: "str | None" = None,
        result_decl: "str | None" = None,
    ):
        from xdsl.ir import Block, Region
        props: dict = {
            "fn_name":     StringAttr(fn_name),
            "bind_name":   StringAttr(bind_name),
            "is_function": BoolAttr.from_bool(is_function),
            "args":        ArrayAttr([StringAttr(a) for a in args]),
            "arg_decls":   ArrayAttr([StringAttr(d) for d in arg_decls]),
            "local_decls": ArrayAttr([StringAttr(d) for d in local_decls]),
        }
        if result_name is not None:
            props["result_name"] = StringAttr(result_name)
        if result_decl is not None:
            props["result_decl"] = StringAttr(result_decl)
        super().__init__(properties=props, regions=[Region([Block(body_ops)])])


@irdl_op_definition
class CToFortranStringCopyOp(IRDLOperation):
    """The fixed-shape C-to-Fortran NUL-terminated char-array copy-in idiom
    used by the chost BIND(C) cap to receive a ``character(kind=c_char)``
    array argument into a local deferred-length Fortran string.

    Emits::

        {f_var} = ' '
        do i = 1, len({f_var})
          if ({c_var}(i) == c_null_char) exit
          {f_var}(i:i) = {c_var}(i)
        end do

    ``c_var``/``f_var`` are opaque name text (see AssignOp's own docstring
    for why expression content stays unstructured). The shape is fixed --
    always blank-init then scan-until-NUL -- so a dedicated op is clearer
    here than composing it from smaller loop primitives; it never varies
    across its call sites.

    Relies on a surrounding scope having declared an untyped ``integer``
    loop variable named ``i`` (matching the original hand-written code;
    not owned by this op).
    """

    name = "ccpp_utils.c_to_fortran_string_copy"
    c_var = prop_def(StringAttr)
    f_var = prop_def(StringAttr)

    def __init__(self, c_var: str, f_var: str):
        super().__init__(properties={
            "c_var": StringAttr(c_var),
            "f_var": StringAttr(f_var),
        })


@irdl_op_definition
class FortranToCStringCopyOp(IRDLOperation):
    """The fixed-shape Fortran-to-C NUL-terminated char-array copy-out
    idiom used by the chost BIND(C) cap to return a local Fortran string
    through a ``character(kind=c_char)`` array argument.

    Emits::

        do i = 1, len_trim({f_var})
          {c_var}(i) = {f_var}(i:i)
        end do
        {c_var}(len_trim({f_var})+1) = c_null_char

    ``c_var``/``f_var`` are opaque name text (see AssignOp's own docstring
    for why expression content stays unstructured). Mirror image of
    CToFortranStringCopyOp; kept as a separate op rather than a direction
    flag since the two shapes share no printable text and a flag would
    just push the branching into the printer.

    Relies on a surrounding scope having declared an untyped ``integer``
    loop variable named ``i`` (matching the original hand-written code;
    not owned by this op).
    """

    name = "ccpp_utils.fortran_to_c_string_copy"
    c_var = prop_def(StringAttr)
    f_var = prop_def(StringAttr)

    def __init__(self, c_var: str, f_var: str):
        super().__init__(properties={
            "c_var": StringAttr(c_var),
            "f_var": StringAttr(f_var),
        })


@irdl_op_definition
class DdtComponentDeclOp(IRDLOperation):
    """One component declaration inside a DerivedTypeDefOp.

    Same shape as ModuleVarOp (base_type/kind/ddt_name/is_pointer/rank/
    fixed_dim/init_value) but deliberately has no is_target/
    needs_device_residency properties at all -- TARGET is illegal on a
    Fortran derived-type component (gfortran: "Attribute at (1) is not
    allowed in a TYPE definition"); omitting the property entirely (not
    just leaving it unset by convention) makes that structurally
    impossible to emit by accident.

    Printer output mirrors ModuleVarOp's own declaration-line shapes:
        rank=0: ``{type} :: {var_name}``
        rank>0, not pointer: ``{type}, allocatable :: {var_name}(:, ...)``
        rank>0, pointer: ``{type}, pointer :: {var_name}(:, ...) => null()``
        fixed_dim set: ``{type} :: {var_name}({n}) = {init_value}``
    """

    name = "ccpp_utils.ddt_component_decl"

    var_name   = prop_def(StringAttr)
    base_type  = prop_def(StringAttr)
    kind       = opt_prop_def(StringAttr)
    ddt_name   = opt_prop_def(StringAttr)
    is_pointer = opt_prop_def(BoolAttr)
    rank       = prop_def(IntegerAttr)
    fixed_dim  = opt_prop_def(IntegerAttr)
    init_value = opt_prop_def(StringAttr)

    def __init__(self, var_name: str, base_type: str, *, kind: str | None = None,
                 ddt_name: str | None = None, is_pointer: bool = False,
                 rank: int = 0, fixed_dim: int | None = None,
                 init_value: str | None = None):
        props: dict = {
            "var_name":  StringAttr(var_name),
            "base_type": StringAttr(base_type),
            "rank":      IntegerAttr.from_int_and_width(rank, 64),
        }
        if kind is not None:
            props["kind"] = StringAttr(kind)
        if ddt_name is not None:
            props["ddt_name"] = StringAttr(ddt_name)
        if is_pointer:
            props["is_pointer"] = BoolAttr.from_bool(True)
        if fixed_dim is not None:
            props["fixed_dim"] = IntegerAttr.from_int_and_width(fixed_dim, 64)
        if init_value is not None:
            props["init_value"] = StringAttr(init_value)
        super().__init__(properties=props)


@irdl_op_definition
class DerivedTypeDefOp(IRDLOperation):
    """A Fortran derived-type definition, emitted in the module
    specification part (before CONTAINS, since Fortran forbids a
    ``type :: ... end type`` block inside CONTAINS) -- a Region of
    DdtComponentDeclOp children.

    Emits::

        type :: {type_name}
          {component declarations}
        end type {type_name}

    Lives as a child of NonCamHostConstituentApiOp's own body Region
    (the multi-instance per-instance bundle type is its only user today)
    rather than being printed generically by the main statement dispatch --
    the printer gives it a no-op case there and instead emits it from a
    dedicated pre-scan alongside ModuleVarOp's own module-preamble
    emission, for the same "must come before CONTAINS" reason.
    """

    name = "ccpp_utils.derived_type_def"

    type_name = prop_def(StringAttr)
    body      = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, type_name: str, component_ops: list):
        from xdsl.ir import Block, Region
        super().__init__(
            properties={"type_name": StringAttr(type_name)},
            regions=[Region([Block(component_ops)])],
        )


@irdl_op_definition
class CamHostConstituentApiOp(IRDLOperation):
    """Container for the cam_host=True constituent registration API.

    ``public_names`` — names to export with ``public ::`` in the module preamble.
    ``body``         — single-block Region of ``ConstituentFunctionOp`` children.
    """

    name = "ccpp_utils.cam_host_constituent_api"

    public_names = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    body         = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, public_names_list: "list[str]", fn_ops: list):
        from xdsl.ir import Block, Region
        body = Region([Block(fn_ops)])
        super().__init__(
            properties={"public_names": ArrayAttr([StringAttr(n) for n in public_names_list])},
            regions=[body],
        )


@irdl_op_definition
class NonCamHostConstituentApiOp(IRDLOperation):
    """Container for the non-cam_host constituent registration API.

    ``public_names`` — names to export with ``public ::`` in the module preamble.
    ``body``         — single-block Region of ``ConstituentFunctionOp`` children,
                       optionally preceded by one DerivedTypeDefOp (the
                       multi-instance per-instance bundle type, when present --
                       the printer's module-preamble pre-scan looks for it here
                       rather than this op carrying a separate type_defs property).
    """

    name = "ccpp_utils.non_cam_host_constituent_api"

    public_names = prop_def(ArrayAttr)          # ArrayAttr[StringAttr]
    body         = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self,
        public_names_list: "list[str]",
        fn_ops: list,
    ):
        from xdsl.ir import Block, Region
        body = Region([Block(fn_ops)])
        props: dict = {
            "public_names": ArrayAttr([StringAttr(n) for n in public_names_list]),
        }
        super().__init__(properties=props, regions=[body])


@irdl_op_definition
class SuiteVariablesOp(IRDLOperation):
    """Carries the generated ccpp_physics_suite_variables subroutine as IR.

    The `body` region holds a single ConstituentFunctionOp representing the
    ccpp_physics_suite_variables subroutine; the printer delegates to it.
    """

    name = "ccpp_utils.suite_variables"

    body   = region_def("single_block")
    traits = traits_def(NoTerminator())

    def __init__(self, fn_op):
        from xdsl.ir import Block, Region
        super().__init__(regions=[Region([Block([fn_op])])])


@irdl_op_definition
class CppIncludeOp(IRDLOperation):
    """A C/C++ ``#include`` directive.

    Emits::

        #include <{header}>      (default: system/angle-bracket form)
        #include "{header}"      (``local=True``: quoted form)
    """

    name = "ccpp_utils.cpp_include"
    header = prop_def(StringAttr)
    local  = opt_prop_def(BoolAttr)

    def __init__(self, header: str, local: bool = False):
        props: dict = {"header": StringAttr(header)}
        if local:
            props["local"] = BoolAttr.from_bool(True)
        super().__init__(properties=props)


@irdl_op_definition
class ExternCGuardOp(IRDLOperation):
    """Wraps a region in the ``#ifdef __cplusplus`` / ``extern "C"`` guard
    block used by every generated C++-interop header.

    Emits::

        #ifdef __cplusplus
        extern "C" {
        #endif
        {body}
        #ifdef __cplusplus
        }
        #endif

    No properties -- the guard text is fixed. Replaces what were two
    independently hand-duplicated copies of this exact block in
    ``cpp_interop.py`` (``_build_chost_cpp_text``) and a third in
    ``print_cpp_header.py`` (``_emit_cap_header``).
    """

    name = "ccpp_utils.extern_c_guard"
    body = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, body_ops: list):
        from xdsl.ir import Block, Region
        super().__init__(regions=[Region([Block(body_ops)])])


@irdl_op_definition
class CFunctionSigOp(IRDLOperation):
    """A C function prototype, or an ``inline`` C++ function definition.

    Emits, when ``body`` is empty (a declaration)::

        {return_type} {fn_name}(
            {param_type}       {param_name},  {param_comment}
            ...
        );

    or, with no params::

        {return_type} {fn_name}(void);

    When ``body`` is non-empty (a definition -- Stage 3's own use, not yet
    exercised by Stage 2)::

        inline {return_type} {fn_name}(...) {
          {body}
        }

    ``param_names``/``param_types``/``param_comments`` are parallel
    ``ArrayAttr[StringAttr]`` (``param_comments`` entries may be empty
    strings), matching ``print_cpp_header.py``'s own pre-existing
    ``_fn_params`` tuple shape so retrofitting its callers is close to
    mechanical.

    ``is_const`` (Stage 3): a trailing ``const`` qualifier, for a member
    function nested inside a ``CppStructDefOp.methods`` region (e.g.
    ``bool ok() const { ... }``). Struct-method printing is a distinct
    code path from this op's own top-level printing (member functions
    never print ``inline`` even when ``is_inline`` is set, and empty
    params print ``()`` not ``(void)``) -- see ``CppStructDefOp``.
    """

    name = "ccpp_utils.c_function_sig"

    fn_name         = prop_def(StringAttr)
    return_type     = prop_def(StringAttr)
    is_inline       = opt_prop_def(BoolAttr)
    is_const        = opt_prop_def(BoolAttr)
    param_names     = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    param_types     = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    param_comments  = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    body            = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self, fn_name: str, param_names: "list[str]", param_types: "list[str]",
        param_comments: "list[str]", body_ops: list,
        return_type: str = "void", is_inline: bool = False, is_const: bool = False,
    ):
        from xdsl.ir import Block, Region
        props: dict = {
            "fn_name":        StringAttr(fn_name),
            "return_type":    StringAttr(return_type),
            "param_names":    ArrayAttr([StringAttr(n) for n in param_names]),
            "param_types":    ArrayAttr([StringAttr(t) for t in param_types]),
            "param_comments": ArrayAttr([StringAttr(c) for c in param_comments]),
        }
        if is_inline:
            props["is_inline"] = BoolAttr.from_bool(True)
        if is_const:
            props["is_const"] = BoolAttr.from_bool(True)
        super().__init__(properties=props, regions=[Region([Block(body_ops)])])


@irdl_op_definition
class CppFieldDeclOp(IRDLOperation):
    """One member-variable declaration inside a CppStructDefOp.

    Emits::

        {cpp_type:<{width}} {field_name}{array_suffix}{ = init_expr};

    where ``width = type_width`` if given, else ``8`` (the pad-plus-
    mandatory-space formula below is byte-identical to Stage 2's own
    original pad-to-9-no-space formula for every string <= 8 chars --
    Stage 2's only 3 actual type strings -- so this change is a pure
    extension, not a Stage-2 behavior change; it also fixes a latent
    bug in that original formula, which silently produced *zero*
    separating space for any type name >= 9 chars, never triggered
    before Stage 3 passes wider type strings).

    ``array_suffix`` (e.g. ``"[129]"``) is opaque text, same
    declaration-stays-text convention used everywhere else in this
    codebase for this kind of trailing shape annotation. ``init_expr``
    (e.g. ``"nullptr"``, ``"0"``, for a default member initializer) has
    the same lang-neutral-expr-ir Stage 3b structured alternative as
    the other ops in this round -- pass ``init_expr_op`` instead.
    """

    name = "ccpp_utils.cpp_field_decl"
    field_name   = prop_def(StringAttr)
    cpp_type     = prop_def(StringAttr)
    array_suffix = opt_prop_def(StringAttr)
    init_expr    = opt_prop_def(StringAttr)
    init_expr_region = opt_region_def("single_block")
    type_width   = opt_prop_def(IntegerAttr)

    traits = traits_def(NoTerminator())

    def __init__(
        self, field_name: str, cpp_type: str,
        array_suffix: "str | None" = None, init_expr: "str | None" = None,
        type_width: "int | None" = None, *, init_expr_op=None,
    ):
        if init_expr is not None and init_expr_op is not None:
            raise ValueError(
                "CppFieldDeclOp: pass at most one of init_expr or init_expr_op"
            )
        props: dict = {"field_name": StringAttr(field_name), "cpp_type": StringAttr(cpp_type)}
        if array_suffix is not None:
            props["array_suffix"] = StringAttr(array_suffix)
        init_region = None
        if init_expr is not None:
            props["init_expr"] = StringAttr(init_expr)
        elif init_expr_op is not None:
            init_region = _single_op_region([init_expr_op])
        if type_width is not None:
            props["type_width"] = IntegerAttr.from_int_and_width(type_width, 32)
        super().__init__(properties=props, regions=[init_region])


@irdl_op_definition
class CppStructDefOp(IRDLOperation):
    """A C/C++ struct definition.

    Emits::

        struct {struct_name} {
          {members}
          {methods, each printed via its own distinct member-function
           form -- never 'inline', '()' not '(void)' for empty params,
           single-line body when it's exactly one statement}

        private:
          {private_members}
        };

    ``is_pod`` (default True) now has real printer effect (Stage 2's own
    docstring noted it previously didn't): ``__init__`` raises if
    ``method_ops``/``private_member_ops`` is non-empty while
    ``is_pod=True``. Stage 2's own use (``CcppConstituentInfo``) stays
    POD (fields only); Stage 3's ``Status``/``State`` pass
    ``is_pod=False`` explicitly.
    """

    name = "ccpp_utils.cpp_struct_def"
    struct_name      = prop_def(StringAttr)
    is_pod           = opt_prop_def(BoolAttr)
    members          = region_def("single_block")
    methods          = region_def("single_block")
    private_members  = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self, struct_name: str, member_ops: list, is_pod: bool = True,
        method_ops: "list | None" = None, private_member_ops: "list | None" = None,
    ):
        from xdsl.ir import Block, Region
        method_ops = method_ops or []
        private_member_ops = private_member_ops or []
        if is_pod and (method_ops or private_member_ops):
            raise ValueError(
                f"CppStructDefOp({struct_name!r}): method_ops/private_member_ops "
                f"given but is_pod defaulted to True -- pass is_pod=False explicitly "
                f"for a struct with member functions or a private section."
            )
        props: dict = {"struct_name": StringAttr(struct_name)}
        if is_pod:
            props["is_pod"] = BoolAttr.from_bool(True)
        super().__init__(
            properties=props,
            regions=[
                Region([Block(member_ops)]),
                Region([Block(method_ops)]),
                Region([Block(private_member_ops)]),
            ],
        )


@irdl_op_definition
class CppNamespaceOp(IRDLOperation):
    """A C++ namespace block.

    Emits::

        namespace {ns_name} {
        {body}
        } // namespace {ns_name}

    Body children are printed with no added indent, matching the
    generated wrapper's own existing un-indented namespace-body style.
    """

    name = "ccpp_utils.cpp_namespace"
    ns_name = prop_def(StringAttr)
    body    = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, ns_name: str, body_ops: list):
        from xdsl.ir import Block, Region
        super().__init__(
            properties={"ns_name": StringAttr(ns_name)},
            regions=[Region([Block(body_ops)])],
        )


@irdl_op_definition
class CppCallStatementOp(IRDLOperation):
    """A column-wrapped ``callee(args...);`` C++ call statement.

    The C++-syntax sibling of ``CallStatementOp`` (Fortran's ``call
    {callee}(args)``): emits ``{callee}(args);``, column-wrapped via the
    shared ``wrap_paren_list`` helper (``print_ftn.py``, generalized with a
    ``cont_marker`` parameter so it no longer hardcodes Fortran's ``" &"``
    continuation) when the single-line form would be too long -- with no
    continuation marker needed in C++.
    """

    name = "ccpp_utils.cpp_call_statement"

    callee    = prop_def(StringAttr)
    call_args = opt_prop_def(ArrayAttr)   # legacy ArrayAttr[StringAttr]
    # lang-neutral-expr-ir Stage 3b: structured alternative to call_args,
    # pass call_arg_ops= instead.
    call_args_region = var_region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self, callee: str, call_args: "list[str] | None" = None,
        *, call_arg_ops: "list | None" = None,
    ):
        if call_args is not None and call_arg_ops is not None:
            raise ValueError(
                "CppCallStatementOp: pass at most one of call_args or call_arg_ops"
            )
        props: dict = {"callee": StringAttr(callee)}
        if call_arg_ops is not None:
            call_args_regions = [_single_op_region([a]) for a in call_arg_ops]
        else:
            props["call_args"] = ArrayAttr([StringAttr(a) for a in (call_args or [])])
            call_args_regions = []
        super().__init__(properties=props, regions=[call_args_regions])


@irdl_op_definition
class CppBraceInitCallOp(IRDLOperation):
    """A designated-initializer struct-literal call, always returned.

    Emits::

        return {callee}({
            .{field_names[0]}={field_values[0]},
            ...
        });

    Always multi-line, one field per line, unconditionally -- matches the
    generated wrapper's own existing unconditional one-per-line style for
    this idiom (the State-struct convenience overloads); no column-budget
    logic needed here, unlike ``CppCallStatementOp``.
    """

    name = "ccpp_utils.cpp_brace_init_call"

    callee        = prop_def(StringAttr)
    field_names   = prop_def(ArrayAttr)   # ArrayAttr[StringAttr] -- struct member names, not exprs
    field_values  = opt_prop_def(ArrayAttr)   # legacy ArrayAttr[StringAttr]
    # lang-neutral-expr-ir Stage 3b: structured alternative to
    # field_values, pass field_value_ops= instead.
    field_values_region = var_region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self, callee: str, field_names: "list[str]",
        field_values: "list[str] | None" = None, *, field_value_ops: "list | None" = None,
    ):
        if field_values is not None and field_value_ops is not None:
            raise ValueError(
                "CppBraceInitCallOp: pass at most one of field_values or field_value_ops"
            )
        props: dict = {
            "callee":      StringAttr(callee),
            "field_names": ArrayAttr([StringAttr(n) for n in field_names]),
        }
        if field_value_ops is not None:
            field_values_regions = [_single_op_region([v]) for v in field_value_ops]
        else:
            props["field_values"] = ArrayAttr([StringAttr(v) for v in (field_values or [])])
            field_values_regions = []
        super().__init__(properties=props, regions=[field_values_regions])


@irdl_op_definition
class CppConstructorOp(IRDLOperation):
    """A C++ constructor with a member-initializer list, nested inside a
    ``CppStructDefOp``'s ``methods`` region.

    Emits::

        {struct_name}({param_type} {param_name} = {param_default}, ...)
            : {init_member}({init_expr}), ... {}

    (or ``{ ...body... }`` if ``body`` is non-empty -- not exercised by
    today's conversion, harmless future-proofing matching
    ``CFunctionSigOp``'s own empty-vs-non-empty-body convention.)

    No ``struct_name`` property: only ever appears nested inside a
    ``CppStructDefOp.methods`` region, so the containing struct supplies
    the name at print time -- storing it redundantly on the child risks
    the two disagreeing.
    """

    name = "ccpp_utils.cpp_constructor"

    param_names    = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    param_types    = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    param_defaults = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    init_members   = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    init_exprs     = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    body           = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self, param_names: "list[str]", param_types: "list[str]",
        param_defaults: "list[str]", init_members: "list[str]",
        init_exprs: "list[str]", body_ops: list,
    ):
        from xdsl.ir import Block, Region
        super().__init__(
            properties={
                "param_names":    ArrayAttr([StringAttr(n) for n in param_names]),
                "param_types":    ArrayAttr([StringAttr(t) for t in param_types]),
                "param_defaults": ArrayAttr([StringAttr(d) for d in param_defaults]),
                "init_members":   ArrayAttr([StringAttr(m) for m in init_members]),
                "init_exprs":     ArrayAttr([StringAttr(e) for e in init_exprs]),
            },
            regions=[Region([Block(body_ops)])],
        )


@irdl_op_definition
class RawCppLinesOp(IRDLOperation):
    """Escape hatch for C++ content not yet converted to structured ops.

    The C++ sibling of ``RawFortranLinesOp``: holds raw C++ text (one or
    more lines, newline-separated), printed verbatim by
    ``print_cpp_header.py`` with no added indentation or punctuation.
    Permanent escape hatch (comments, section-header banners, local
    buffer declarations with varied initializer shapes, simple
    ``return``/one-off ``if (...) foo();`` lines) -- not just a staging
    device, same role ``RawFortranLinesOp`` already plays in ``ftn_body``.
    """

    name = "ccpp_utils.raw_cpp_lines"

    lines = prop_def(StringAttr)

    def __init__(self, text: str):
        super().__init__(properties={"lines": StringAttr(text)})


@irdl_op_definition
class CHostCapOp(IRDLOperation):
    """Carries the auto-generated BIND(C) cap for a C++ host model.

    ``ftn_body`` holds the complete Fortran module as structured IR,
    printed by ``print_ftn.py``. ``cpp_body`` holds the complete C header
    as structured IR, and ``wrapper_body`` holds the complete C++
    ergonomics wrapper (.hpp) as structured IR, both printed by
    ``print_cpp_header.py``.

    ``mod_name`` is the base name used for the module and header file, e.g.
    ``"Kessler_ccpp_chost_cap"``.
    """

    name = "ccpp_utils.chost_cap"

    ftn_body     = region_def("single_block")   # complete Fortran module, as ops
    cpp_body     = region_def("single_block")   # complete C++ header, as ops
    wrapper_body = region_def("single_block")   # complete C++ wrapper, as ops
    mod_name     = prop_def(StringAttr)   # base name, e.g. "Kessler_ccpp_chost_cap"

    traits = traits_def(NoTerminator())

    def __init__(self, ftn_body_ops: list, cpp_body_ops: list, mod_name: str,
                 wrapper_body_ops: list = ()):
        from xdsl.ir import Block, Region
        super().__init__(
            properties={
                "mod_name": StringAttr(mod_name),
            },
            regions=[
                Region([Block(ftn_body_ops)]),
                Region([Block(cpp_body_ops)]),
                Region([Block(list(wrapper_body_ops))]),
            ],
        )


@irdl_op_definition
class CapVarRefOp(IRDLOperation):
    """Reference to a module-level variable declared in the same cap module.

    Like HostVarRefOp but no USE statement is generated — the variable is
    in the current module.  The printer registers the variable name so that
    downstream ops emit it correctly.
    """

    name = "ccpp_utils.cap_var_ref"

    var_name = prop_def(StringAttr)
    res = result_def()

    def __init__(self, var_name: str, result_type):
        super().__init__(
            properties={"var_name": StringAttr(var_name)},
            result_types=[result_type],
        )


@irdl_op_definition
class KindCastOp(IRDLOperation):
    """Convert a real variable to a different Fortran KIND for a scheme call.

    Represents the statement pair::

        allocate(result, mold=source)            ! arrays only
        result = real(source, kind=target_kind)

    The *result* SSA value carries the target-kind type and is declared as a
    local allocatable in the enclosing suite-cap function.  For scalars the
    allocate is omitted.

    In the write direction (from scheme back to host) use ``KindWriteBackOp``.
    """

    name = "ccpp_utils.kind_cast"

    source      = operand_def()
    target_kind = prop_def(StringAttr)

    res = result_def()

    def __init__(
        self,
        source: "SSAValue | IRDLOperation",
        target_kind: "str | StringAttr",
        result_type,
    ):
        target_kind = _coerce_str_attr(target_kind)
        super().__init__(
            operands=[source],
            properties={"target_kind": target_kind},
            result_types=[result_type],
        )


### lang-neutral-expr-ir Stage 1b: new expression ops ########################
#
# None of these has an MLIR-standard analog (arith/math already cover
# arithmetic/logical/comparison/numeric+boolean literals directly -- see
# print_ftn.py's print_expr). Each composes through the same recursive
# print_expr/expr_to_cpp_str dispatch as arith ops and StrCmpOp/TrimOp do
# today; a region child is any op that dispatch already knows how to
# print, so no further "wrapper" op is needed anywhere below.


@irdl_op_definition
class StringLiteralExprOp(IRDLOperation):
    """A compile-time string literal used as a sub-expression.

    Emits ``'{text}'`` (Fortran) or ``"{text}"`` (C++) -- pure print-time
    text embedding, a different, simpler problem than the existing
    llvm.GlobalOp mechanism (which exists for when *generated code
    itself* needs a real runtime string constant with a real address --
    already solved, not what this is for).
    """

    name = "ccpp_utils.string_literal_expr"
    text = prop_def(StringAttr)

    def __init__(self, text: str):
        super().__init__(properties={"text": StringAttr(text)})


@irdl_op_definition
class StringConcatExprOp(IRDLOperation):
    """Fortran string concatenation: ``piece0 // piece1 // ...``
    (C++: an ``operator+`` chain).

    ``pieces`` holds two or more children, each any print_expr/
    expr_to_cpp_str-dispatchable string-valued expression op
    (StringLiteralExprOp, VarRefExprOp, CallExprOp, or a real compiled
    string value such as a CCPPTrimOp/CCPPStrCmpOp result) -- composes
    directly through the existing recursion. No dedicated "piece" wrapper
    op is needed: a region already holds real ops, not bare SSA values,
    so an op with a real result (like CCPPTrimOp) is simply one of the
    children directly.
    """

    name = "ccpp_utils.string_concat_expr"
    # One region per piece (not one shared region holding N sibling
    # ops): a piece can itself be a freshly-built arith/math sub-tree
    # (e.g. a CallExprOp wrapping comparison ops), whose own floating
    # operand dependencies must be flattened into ITS OWN region via
    # _single_op_region -- sharing one region/block across all pieces
    # would make the printer unable to tell a flattened dependency op
    # apart from a genuine sibling piece.
    pieces = var_region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, piece_ops: "list"):
        piece_ops = list(piece_ops)
        if len(piece_ops) < 2:
            raise ValueError("StringConcatExprOp needs at least 2 pieces")
        super().__init__(regions=[[_single_op_region([p]) for p in piece_ops]])


@irdl_op_definition
class VarRefExprOp(IRDLOperation):
    """Reference to a cap-gen-synthesized local/variable name that was
    never a real SSA value.

    Emits the bare name verbatim. Covers e.g. constituent_cap.py's
    locals -- "every reference is a plain text name," per
    TextBoundedDoLoopOp's own docstring -- as a structured expression
    leaf instead of raw text.

    ``result_type`` is optional (``res``, like ``CapVarRefOp``/
    ``HostVarRefOp``, carries "type set at construction to match callee
    expectation"): pass it when this reference needs to compose as a
    real operand of an ``arith``/``math`` op (e.g. ``state%errflg`` on
    one side of an ``arith.CmpiOp``) -- omit it when this op is only
    ever a region child printed by recursion, never an operand.
    """

    name = "ccpp_utils.var_ref_expr"
    var_name = prop_def(StringAttr)
    res = opt_result_def()

    def __init__(self, var_name: str, result_type=None):
        super().__init__(
            properties={"var_name": StringAttr(var_name)},
            result_types=[result_type] if result_type is not None else [None],
        )


@irdl_op_definition
class MemberAccessExprOp(IRDLOperation):
    """Derived-type/struct member access.

    Emits ``{base}%{member}`` (Fortran, always) or ``{base}.{member}`` /
    ``{base}->{member}`` (C++, selected by ``via``).

    ``base`` holds exactly one child expression op -- needs to support
    nesting, since real call sites chain, e.g.
    ``lc_instances(instance)%cam_constituents_obj``.

    ``result_type`` is optional, same "type set at construction to match
    callee expectation" convention as ``VarRefExprOp``'s own -- see its
    docstring; pass it when this access needs to compose as a real
    operand of an ``arith``/``math`` op.
    """

    name = "ccpp_utils.member_access_expr"
    base = region_def("single_block")
    member = prop_def(StringAttr)
    via = opt_prop_def(StringAttr)  # "value"|"pointer"; default "value"
    res = opt_result_def()

    traits = traits_def(NoTerminator())

    def __init__(
        self, base_op, member: str, via: "str | None" = None, result_type=None
    ):
        props: dict = {"member": StringAttr(member)}
        if via is not None:
            if via not in ("value", "pointer"):
                raise ValueError(
                    f"MemberAccessExprOp: via must be 'value' or 'pointer', got {via!r}"
                )
            props["via"] = StringAttr(via)
        super().__init__(
            properties=props,
            regions=[_single_op_region([base_op])],
            result_types=[result_type] if result_type is not None else [None],
        )


@irdl_op_definition
class IndexExprOp(IRDLOperation):
    """Array indexing.

    Emits ``{base}(i0, i1, ...)`` (Fortran) or ``{base}[i0][i1]...``
    (C++). ``base`` holds exactly one child expr; ``indices`` holds one
    child per subscript -- each either a plain expression op or a
    SliceExprOp (Fortran range syntax only; C++ slicing is unsupported,
    see SliceExprOp).

    ``result_type`` is optional, same "type set at construction to match
    callee expectation" convention as ``VarRefExprOp``'s own -- see its
    docstring; pass it when an indexed element needs to compose as a
    real operand of an ``arith``/``math`` op (e.g. ``arr(i) + 1``).
    """

    name = "ccpp_utils.index_expr"
    base = region_def("single_block")
    # One region per subscript (see StringConcatExprOp.pieces's own
    # comment for why: a subscript can itself be a freshly-built
    # arith/math sub-tree whose floating dependencies need their own
    # region, not a shared block mixed in with sibling subscripts).
    indices = var_region_def("single_block")
    res = opt_result_def()

    traits = traits_def(NoTerminator())

    def __init__(self, base_op, index_ops: "list", result_type=None):
        index_ops = list(index_ops)
        if not index_ops:
            raise ValueError("IndexExprOp needs at least one index")
        super().__init__(
            regions=[
                _single_op_region([base_op]),
                [_single_op_region([i]) for i in index_ops],
            ],
            result_types=[result_type] if result_type is not None else [None],
        )


@irdl_op_definition
class SliceExprOp(IRDLOperation):
    """Fortran array-section range: ``{lower}:{upper}[:{stride}]`` (any of
    the three may be omitted, e.g. a bare ``:`` when all are absent).

    Appears only as a child of IndexExprOp.indices. Unsupported for a
    C++-targeted print -- no equivalent syntax, so the printer raises.
    """

    name = "ccpp_utils.slice_expr"
    lower = opt_region_def("single_block")
    upper = opt_region_def("single_block")
    stride = opt_region_def("single_block")

    irdl_options = [AttrSizedRegionSegments()]
    traits = traits_def(NoTerminator())

    def __init__(self, lower_op=None, upper_op=None, stride_op=None):
        super().__init__(
            regions=[
                _single_op_region([lower_op]) if lower_op is not None else None,
                _single_op_region([upper_op]) if upper_op is not None else None,
                _single_op_region([stride_op]) if stride_op is not None else None,
            ]
        )


@irdl_op_definition
class KeywordArgExprOp(IRDLOperation):
    """One keyword argument of a CallExprOp: ``{arg_name}={value}``.

    Fortran only -- C++ has no named-argument syntax for free functions;
    CallExprOp raises at print time if any KeywordArgExprOp children are
    present on a C++-targeted print.
    """

    name = "ccpp_utils.keyword_arg_expr"
    arg_name = prop_def(StringAttr)
    value = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, arg_name: str, value_op):
        super().__init__(
            properties={"arg_name": StringAttr(arg_name)},
            regions=[_single_op_region([value_op])],
        )


@irdl_op_definition
class CallExprOp(IRDLOperation):
    """Expression-level call with positional and/or keyword arguments.

    Emits ``{callee}(args, kwargs)`` (Fortran) or ``{callee}(args)``
    (C++ -- raises if ``kwargs`` is non-empty, since C++ free functions
    have no named-argument syntax).

    Distinct from the *statement*-level DdtMethodCallOp/CallStatementOp:
    this is a sub-expression (e.g. a function-call RHS, ``trim(x)`` as
    one piece of a StringConcatExprOp), not a call statement in its own
    right.

    ``result_type`` is optional, same "type set at construction to match
    callee expectation" convention as ``VarRefExprOp``'s own -- see its
    docstring; pass it when a numeric call's result needs to compose as
    a real operand of an ``arith``/``math`` op (e.g. ``len(x) + 1``).
    """

    name = "ccpp_utils.call_expr"
    callee = prop_def(StringAttr)
    # One region per positional/keyword arg (see StringConcatExprOp.pieces's
    # own comment for why): an arg can itself be a freshly-built
    # arith/math sub-tree (e.g. CallExprOp("any", [a_cmpi_tree])), whose
    # floating operand dependencies need their own region, not a shared
    # block mixed in with sibling args.
    args = var_region_def("single_block")  # positional argument expr ops
    kwargs = var_region_def("single_block")  # KeywordArgExprOp children
    res = opt_result_def()

    irdl_options = [AttrSizedRegionSegments()]
    traits = traits_def(NoTerminator())

    def __init__(
        self, callee: str, arg_ops: "list | None" = None, kwarg_ops: "list | None" = None,
        result_type=None,
    ):
        super().__init__(
            properties={"callee": StringAttr(callee)},
            result_types=[result_type] if result_type is not None else [None],
            regions=[
                [_single_op_region([a]) for a in (arg_ops or [])],
                [_single_op_region([k]) for k in (kwarg_ops or [])],
            ],
        )


@irdl_op_definition
class ArrayConstructorExprOp(IRDLOperation):
    """Fortran array-constructor literal: ``[ {elem_type} :: e0, e1, ... ]``
    (``elem_type`` omitted when not given). C++: ``{ e0, e1, ... }``
    brace-init-list -- imperfect but reasonable; no real C++ call site
    needs this yet.
    """

    name = "ccpp_utils.array_constructor_expr"
    elem_type = opt_prop_def(StringAttr)
    # One region per element (see StringConcatExprOp.pieces's own
    # comment for why).
    elements = var_region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, element_ops: "list", elem_type: "str | None" = None):
        props: dict = {}
        if elem_type is not None:
            props["elem_type"] = StringAttr(elem_type)
        super().__init__(
            properties=props,
            regions=[[_single_op_region([e]) for e in element_ops]],
        )


### end lang-neutral-expr-ir Stage 1b new expression ops #####################


@irdl_op_definition
class UnitConvertOp(IRDLOperation):
    """Allocate a local temp and optionally apply a host→scheme unit conversion.

    For ``intent(in)`` / ``intent(inout)``::

        allocate(result(size(source,1), ...))   ! arrays only
        result = source <to_scheme_expr>         ! e.g. "* 0.01_kind_phys"

    For ``intent(out)`` (scheme does not read the value), pass an empty
    ``to_scheme_expr`` and only the allocation is emitted::

        allocate(result(size(source,1), ...))   ! arrays only

    The host's source array is never modified.  The result SSA value is
    declared as a local (allocatable for arrays, plain for scalars) in the
    enclosing function.  Use ``UnitWriteBackOp`` to write back after the
    scheme call for ``intent(inout)`` / ``intent(out)`` arguments.

    lang-neutral-expr-ir Stage 1b adds a structured alternative to the
    opaque ``to_scheme_expr`` text fragment: pass ``conversion_op`` (a
    real ``arith.AddfOp``/``SubfOp`` whose ``lhs`` operand is this op's
    own ``source`` operand -- ordinary MLIR semantics, since nested
    regions in this dialect are not isolated-from-above, same as
    e.g. IfThenOp's body) instead of ``to_scheme_expr``. Exactly one of
    the two must be given. The structured form has no real call site yet
    (retrofitting one is Stage 3c); the opaque-text form remains fully
    supported so every existing caller is unaffected.
    """

    name = "ccpp_utils.unit_convert"

    source         = operand_def()
    to_scheme_expr = opt_prop_def(StringAttr)  # e.g. "+ 273.15" or "" for out-only
    conversion     = opt_region_def("single_block")  # structured alternative

    res = result_def()

    traits = traits_def(NoTerminator())

    def __init__(
        self,
        source: "SSAValue | IRDLOperation",
        to_scheme_expr: "str | StringAttr | None" = None,
        result_type=None,
        *,
        conversion_op=None,
    ):
        if (to_scheme_expr is None) == (conversion_op is None):
            raise ValueError(
                "UnitConvertOp: pass exactly one of to_scheme_expr or conversion_op"
            )
        props: dict = {}
        region = None
        if to_scheme_expr is not None:
            props["to_scheme_expr"] = _coerce_str_attr(to_scheme_expr)
        else:
            if not isinstance(conversion_op.rhs.owner, ArithConstantOp):
                raise ValueError(
                    "UnitConvertOp: conversion_op.rhs must be a plain "
                    "arith.ConstantOp -- a compound rhs would lose its own "
                    "grouping when flattened into the printed suffix "
                    "fragment (e.g. 'source - a + b' instead of "
                    "'source - (a + b)'), and _suffix_kind_in_expr's kind "
                    "suffix is only meaningful on a literal"
                )
            region = _single_op_region([conversion_op])
        super().__init__(
            operands=[source],
            properties=props,
            regions=[region],
            result_types=[result_type],
        )


@irdl_op_definition
class UnitWriteBackOp(IRDLOperation):
    """Write a unit-converted value back to the original host variable.

    Represents::

        original_dest = conv_result <to_host_expr>   ! e.g. "conv_result - 273.15"
        deallocate(conv_result)                       ! arrays only

    Emitted after the scheme call for ``intent(inout)`` / ``intent(out)``
    arguments that required a unit conversion.

    lang-neutral-expr-ir Stage 1b sibling of ``UnitConvertOp``'s own
    structured alternative: pass ``conversion_op`` (a real
    ``arith.AddfOp``/``SubfOp`` whose ``lhs`` operand is this op's own
    ``conv_result`` operand) instead of ``to_host_expr``. Exactly one of
    the two must be given; the opaque-text form remains fully supported.
    """

    name = "ccpp_utils.unit_write_back"

    conv_result   = operand_def()
    original_dest = operand_def()

    to_host_expr = opt_prop_def(StringAttr)   # e.g. "- 273.15"
    conversion   = opt_region_def("single_block")  # structured alternative

    traits = traits_def(NoTerminator())

    def __init__(
        self,
        conv_result:   "SSAValue | IRDLOperation",
        original_dest: "SSAValue | IRDLOperation",
        to_host_expr:  "str | StringAttr | None" = None,
        *,
        conversion_op=None,
    ):
        if (to_host_expr is None) == (conversion_op is None):
            raise ValueError(
                "UnitWriteBackOp: pass exactly one of to_host_expr or conversion_op"
            )
        props: dict = {}
        region = None
        if to_host_expr is not None:
            props["to_host_expr"] = _coerce_str_attr(to_host_expr)
        else:
            if not isinstance(conversion_op.rhs.owner, ArithConstantOp):
                raise ValueError(
                    "UnitWriteBackOp: conversion_op.rhs must be a plain "
                    "arith.ConstantOp -- see UnitConvertOp's own identical "
                    "check for why a compound rhs is rejected"
                )
            region = _single_op_region([conversion_op])
        super().__init__(
            operands=[conv_result, original_dest],
            regions=[region],
            properties=props,
        )


@irdl_op_definition
class KindWriteBackOp(IRDLOperation):
    """Write a kind-converted value back to the original host variable.

    Represents::

        original_dest = real(conv_result, kind=original_kind)
        deallocate(conv_result)                  ! arrays only

    Emitted after the scheme call for ``intent(inout)`` / ``intent(out)``
    arguments that required a kind conversion.
    """

    name = "ccpp_utils.kind_write_back"

    conv_result   = operand_def()   # temp in scheme kind
    original_dest = operand_def()   # block arg in host kind

    original_kind = prop_def(StringAttr)   # host kind name

    def __init__(
        self,
        conv_result:   "SSAValue | IRDLOperation",
        original_dest: "SSAValue | IRDLOperation",
        original_kind: "str | StringAttr",
    ):
        original_kind = _coerce_str_attr(original_kind)
        super().__init__(
            operands=[conv_result, original_dest],
            properties={"original_kind": original_kind},
        )


@irdl_op_definition
class VerticalFlipOp(IRDLOperation):
    """Allocate a local temp and reverse an array section along the vertical
    (layer) dimension, for a scheme call whose own top_at_one convention
    differs from the shared value's current convention.

    Represents::

        allocate(result(size(source,1), ...))
        result = source(:, ..., size(source, vertical_dim):1:-1, ..., :)

    ``vertical_dim`` is the 1-based Fortran dimension index (matching the
    argument's own dimensions/dim_names) to reverse; every other dimension
    copies through unchanged (``:``). The host's source array is never
    modified. Use ``VerticalFlipWriteBackOp`` to flip back after the scheme
    call for ``intent(inout)`` / ``intent(out)`` arguments.
    """

    name = "ccpp_utils.vertical_flip"

    source       = operand_def()
    vertical_dim = prop_def(IntegerAttr)   # 1-based Fortran dimension index

    res = result_def()

    def __init__(
        self,
        source: "SSAValue | IRDLOperation",
        vertical_dim: "int | IntegerAttr",
        result_type,
    ):
        vertical_dim = _coerce_int_attr(vertical_dim)
        super().__init__(
            operands=[source],
            properties={"vertical_dim": vertical_dim},
            result_types=[result_type],
        )


@irdl_op_definition
class VerticalFlipWriteBackOp(IRDLOperation):
    """Write a vertically-flipped value back to the original host variable.

    Represents::

        original_dest = conv_result(:, ..., size(conv_result, vertical_dim):1:-1, ..., :)
        deallocate(conv_result)

    Reversing a reversed section restores the original order, so the
    write-back applies the identical reversed-section expression to the
    *source* side of the assignment (``conv_result``) and assigns into the
    plain, unreversed destination.

    Emitted after the scheme call for ``intent(inout)`` / ``intent(out)``
    arguments that required a vertical flip.
    """

    name = "ccpp_utils.vertical_flip_write_back"

    conv_result   = operand_def()   # temp with the scheme's own vertical convention
    original_dest = operand_def()   # block arg with the host's convention

    vertical_dim = prop_def(IntegerAttr)   # same index as the matching VerticalFlipOp

    def __init__(
        self,
        conv_result:   "SSAValue | IRDLOperation",
        original_dest: "SSAValue | IRDLOperation",
        vertical_dim:  "int | IntegerAttr",
    ):
        vertical_dim = _coerce_int_attr(vertical_dim)
        super().__init__(
            operands=[conv_result, original_dest],
            properties={"vertical_dim": vertical_dim},
        )


@irdl_op_definition
class RowMajorConvertOp(IRDLOperation):
    """Transpose a row-major host array to column-major order for Fortran scheme consumption.

    Emits::

        allocate(result(dim0, dim1, ...))
        result = reshape(source, [dim0, dim1, ...], order=[rank, ..., 1])

    ``dim_exprs`` holds the target (column-major) dimension sizes as Fortran
    expressions matching the scheme's dimension order.  Use
    ``RowMajorWriteBackOp`` to transpose back after the scheme call for
    ``intent(inout)`` / ``intent(out)`` arguments.
    """

    name = "ccpp_utils.row_major_convert"

    source    = operand_def()
    dim_exprs = prop_def(ArrayAttr)   # Fortran expressions, e.g. ["ncol", "nz"]

    res = result_def()

    def __init__(
        self,
        source: "SSAValue | IRDLOperation",
        dim_exprs: "list[str] | ArrayAttr",
        result_type,
    ):
        dim_exprs = _coerce_str_list_attr(dim_exprs)
        super().__init__(
            operands=[source],
            properties={"dim_exprs": dim_exprs},
            result_types=[result_type],
        )


@irdl_op_definition
class RowMajorWriteBackOp(IRDLOperation):
    """Write a column-major local array back to the row-major host variable.

    Emits::

        host_var = reshape(local_val, [dim_{rank-1}, ..., dim0], order=[rank, ..., 1])
        deallocate(local_val)

    ``dim_exprs`` must match the ``dim_exprs`` from the corresponding
    ``RowMajorConvertOp`` (column-major dimension order).  The write-back
    reverses the dimension list and applies the same ORDER so the result
    matches the host's row-major layout.
    """

    name = "ccpp_utils.row_major_write_back"

    local_val = operand_def()
    host_var  = operand_def()
    dim_exprs = prop_def(ArrayAttr)   # same order as RowMajorConvertOp (column-major)

    def __init__(
        self,
        local_val: "SSAValue | IRDLOperation",
        host_var:  "SSAValue | IRDLOperation",
        dim_exprs: "list[str] | ArrayAttr",
    ):
        dim_exprs = _coerce_str_list_attr(dim_exprs)
        super().__init__(
            operands=[local_val, host_var],
            properties={"dim_exprs": dim_exprs},
        )


@irdl_op_definition
class ConstituentSyncOp(IRDLOperation):
    """Sync one advected constituent between its module-level array and the
    3D constituent array passed to the suite cap run subroutine.

    direction="extract":   var_name(1:ncol_name, :) = q_name(1:ncol_name, :, lc_const_indices(idx))
    direction="writeback": q_name(1:ncol_name, :, lc_const_indices(idx)) = var_name(1:ncol_name, :)

    constituent_idx is the 1-based position of the constituent in the suite's
    cam_model_const_stdnames list.  lc_const_indices (a module-level array in
    the suite cap, populated at init time via ccpp_constituent_indices) maps
    that position to the actual runtime index in the 3D constituent array q,
    which may differ from the position when host constituents are registered
    before scheme constituents (cam_host=True path).

    Injected by SuiteCAP around the scheme calls in a _run subroutine when
    the suite owns module-level allocatables for advected constituents.
    """

    name = "ccpp_utils.constituent_sync"

    var_name       = prop_def(StringAttr)   # module-level var, e.g. "qv"
    q_name         = prop_def(StringAttr)   # constituent array, e.g. "q"
    ncol_name      = prop_def(StringAttr)   # column count variable, e.g. "ncol"
    constituent_idx = prop_def(IntegerAttr) # 1-based index in q's 3rd dimension
    direction      = prop_def(StringAttr)   # "extract" or "writeback"

    def __init__(self, var_name: str, q_name: str, ncol_name: str,
                 constituent_idx: int, direction: str):
        super().__init__(properties={
            "var_name":        StringAttr(var_name),
            "q_name":          StringAttr(q_name),
            "ncol_name":       StringAttr(ncol_name),
            "constituent_idx": IntegerAttr.from_int_and_width(constituent_idx, 32),
            "direction":       StringAttr(direction),
        })


@irdl_op_definition
class ConstituentIndexLookupOp(IRDLOperation):
    """Call ccpp_constituent_indices at suite init time to populate lc_const_indices.

    Emitted at the top of each group-phase _init_ FuncOp when the suite owns
    fixed advected constituents.  Prints as::

        call ccpp_constituent_indices( &
            [character(len=N) :: "std_name_1", "std_name_2", ...], &
            lc_const_indices, errflg, errmsg)
        if (errflg /= 0) return

    where N is the length of the longest standard name and the array order
    matches the 1-based constituent_idx values in ConstituentSyncOp.
    lc_const_indices is then populated with the runtime indices so that
    ConstituentSyncOp's q(:,:,lc_const_indices(k)) references are correct
    regardless of constituent registration order.
    """

    name = "ccpp_utils.constituent_index_lookup"
    std_names = prop_def(ArrayAttr)          # ArrayAttr of StringAttr, in constituent_idx order
    err_var_name = opt_prop_def(StringAttr)  # name of the integer error-code arg (e.g. "errflg" or "errcode")

    def __init__(self, std_names: "ArrayAttr | list[str]", err_var_name: "str | None" = None):
        if isinstance(std_names, list):
            std_names = ArrayAttr([StringAttr(s) for s in std_names])
        props: dict = {"std_names": std_names}
        if err_var_name is not None:
            props["err_var_name"] = StringAttr(err_var_name)
        super().__init__(properties=props)


@irdl_op_definition
class CamDirectCallOp(IRDLOperation):
    """Emit a direct Fortran subroutine call with positional string arguments.

    Prints as::

        call {callee}(arg0, arg1, ...)

    Unlike ``func.CallOp``, arguments are stored as Fortran expression strings
    rather than SSA values — suitable for calls where the arguments are
    module-scope variables accessed by name (e.g. ``errmsg``, ``errcode``).
    """

    name = "ccpp_utils.cam_direct_call"

    callee    = prop_def(StringAttr)
    call_args = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]

    def __init__(self, callee: str, call_args: "list[str]"):
        super().__init__(properties={
            "callee":    StringAttr(callee),
            "call_args": ArrayAttr([StringAttr(a) for a in call_args]),
        })


@irdl_op_definition
class CallStatementOp(IRDLOperation):
    """A column-wrapped ``call {callee}(args...)`` statement.

    Emits::

        call {callee}(a, b, c)

    or, when the single-line form would exceed the printer's column
    budget, Fortran-continuation-wraps the argument list the same way
    BindCSubroutineOp's own header does (shared ``wrap_paren_list``
    helper in print_ftn.py) -- replaces cpp_interop.py's own
    independently hand-rolled ``_emit_call`` wrap loop.

    Distinct from CamDirectCallOp (no wrapping at all -- retrofitting it
    risked destabilizing its own already-proven single-line output format
    across its existing callers, same reasoning BindCSubroutineOp was kept
    separate from ConstituentFunctionOp).
    """

    name = "ccpp_utils.call_statement"

    callee    = prop_def(StringAttr)
    call_args = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]

    def __init__(self, callee: str, call_args: "list[str]"):
        super().__init__(properties={
            "callee":    StringAttr(callee),
            "call_args": ArrayAttr([StringAttr(a) for a in call_args]),
        })


@irdl_op_definition
class CamClearErrStateOp(IRDLOperation):
    """Emit the no-dispatch error-state reset for timestep lifecycle wrappers.

    Prints as::

        {errcode_var} = 0
        {errmsg_var} = ''

    Used when a timestep-init or timestep-final wrapper has no per-group
    dispatcher (no scheme registered a timestep-init/final hook), so the
    wrapper must still zero out the error state before returning.
    """

    name = "ccpp_utils.cam_clear_err_state"

    errcode_var = prop_def(StringAttr)
    errmsg_var  = prop_def(StringAttr)

    def __init__(self, errcode_var: str, errmsg_var: str):
        super().__init__(properties={
            "errcode_var": StringAttr(errcode_var),
            "errmsg_var":  StringAttr(errmsg_var),
        })


@irdl_op_definition
class CamQminPreambleOp(IRDLOperation):
    """Emit the constituent-minimum (lc_qmin) preamble in cam_ccpp_physics_run.

    Emitted when the run dispatcher takes ``ccpp_constituent_minimum_values``
    as a block argument (i.e. at least one run-phase scheme reads qmin).
    Prints as::

        integer :: lc_n, lc_i
        real(kind=kind_phys), allocatable :: lc_qmin(:)
        if (allocated(lc_const_props)) then
          lc_n = size(lc_const_props)
        else
          lc_n = 0
        end if
        allocate(lc_qmin(lc_n))
        do lc_i = 1, lc_n
          call lc_const_props(lc_i)%minimum(lc_qmin(lc_i), {errcode_var}, {errmsg_var})
          if ({errcode_var} /= 0) then
            deallocate(lc_qmin)
            return
          end if
        end do

    The declarations (``integer :: lc_n``, etc.) appear inline in the
    subroutine body — valid in Fortran 2003+ and accepted by gfortran/nvhpc.
    ``kind_phys`` is imported from ``ccpp_kinds`` at module scope and is
    therefore available without a redundant subroutine-scope USE.
    """

    name = "ccpp_utils.cam_qmin_preamble"

    errcode_var = prop_def(StringAttr)
    errmsg_var  = prop_def(StringAttr)

    def __init__(self, errcode_var: str, errmsg_var: str):
        super().__init__(properties={
            "errcode_var": StringAttr(errcode_var),
            "errmsg_var":  StringAttr(errmsg_var),
        })


@irdl_op_definition
class CamQminPostambleOp(IRDLOperation):
    """Emit ``deallocate(lc_qmin)`` after the run dispatcher call.

    Paired with ``CamQminPreambleOp`` to clean up the constituent-minimum
    temporary array after ``ccpp_physics_run`` has used it.
    """

    name = "ccpp_utils.cam_qmin_postamble"

    def __init__(self):
        super().__init__()


@irdl_op_definition
class ErrorPropagateOp(IRDLOperation):
    """Emit an early-return guard on an integer error-code variable.

    Prints as::

        if ({errcode_var} /= 0) return
    """

    name = "ccpp_utils.error_propagate"
    errcode_var = prop_def(StringAttr)

    def __init__(self, errcode_var: str):
        super().__init__(properties={"errcode_var": StringAttr(errcode_var)})


@irdl_op_definition
class CamSuiteDispatchOp(IRDLOperation):
    """Emit the if/else suite-group dispatch chain in a CAM lifecycle wrapper.

    Represents the per-group dispatch pattern::

        if (trim(suite_name) == 'suite1') then
          call {dispatcher_fn}(arg1, 'group1', arg3, ...)
          if ({errcode_var} /= 0) return
          call {dispatcher_fn}(arg1, 'group2', arg3, ...)
          if ({errcode_var} /= 0) return
        else if (trim(suite_name) == 'suite2') then
          ...
        else
          write({errmsg_var}, '(3a)') '{wrapper_fn}: no suite named ', &
              trim(suite_name), ' found'
          {errcode_var} = 1
        end if

    Properties
    ----------
    dispatcher_fn : StringAttr
        Name of the internal dispatcher function (e.g. ``ccpp_physics_init``).
    wrapper_fn : StringAttr
        Name of the outer wrapper subroutine; used in the else-branch error message.
    errcode_var : StringAttr
        Fortran variable name for the integer error code (e.g. ``lc_errcode``).
    errmsg_var : StringAttr
        Fortran variable name for the error message string (e.g. ``lc_errmsg``).
    suite_groups : ArrayAttr[ArrayAttr[StringAttr]]
        Outer array has one inner ArrayAttr per suite.  In each inner array,
        element [0] is the suite name and elements [1:] are the group names
        that have a generated dispatcher for this lifecycle phase.
    call_args_template : ArrayAttr[StringAttr]
        Fortran expressions for the dispatcher call arguments, in order.
        The element whose value is the sentinel ``"__suite_part__"`` is
        replaced by the quoted group name literal for each call in the chain.
    """

    name = "ccpp_utils.cam_suite_dispatch"

    dispatcher_fn      = prop_def(StringAttr)
    wrapper_fn         = prop_def(StringAttr)
    errcode_var        = prop_def(StringAttr)
    errmsg_var         = prop_def(StringAttr)
    suite_groups       = prop_def(ArrayAttr)   # ArrayAttr[ArrayAttr[StringAttr]]
    call_args_template = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]

    def __init__(
        self,
        dispatcher_fn: str,
        wrapper_fn: str,
        errcode_var: str,
        errmsg_var: str,
        suite_groups: "list[tuple[str, list[str]]]",
        call_args_template: "list[str]",
    ):
        """
        Parameters
        ----------
        suite_groups
            List of (suite_name, [group1, group2, ...]) tuples.
        call_args_template
            Fortran arg expressions; use ``"__suite_part__"`` where the quoted
            group name should be substituted.
        """
        groups_attr = ArrayAttr([
            ArrayAttr([StringAttr(sn)] + [StringAttr(g) for g in groups])
            for sn, groups in suite_groups
        ])
        super().__init__(properties={
            "dispatcher_fn":      StringAttr(dispatcher_fn),
            "wrapper_fn":         StringAttr(wrapper_fn),
            "errcode_var":        StringAttr(errcode_var),
            "errmsg_var":         StringAttr(errmsg_var),
            "suite_groups":       groups_attr,
            "call_args_template": ArrayAttr([StringAttr(a) for a in call_args_template]),
        })


@irdl_op_definition
class CamSuiteSchemeListOp(IRDLOperation):
    """Emit the suite-keyed scheme-list assignment block in ccpp_physics_suite_schemes.

    Represents the body of the ``ccpp_physics_suite_schemes`` subroutine::

        if (trim(suite_name) == 'suite1') then
          allocate(scheme_list(N))
          scheme_list(1) = 'scheme_a'
          scheme_list(2) = 'scheme_b'
          ...
        else if (trim(suite_name) == 'suite2') then
          ...
        else
          write({errmsg_var}, '(3a)') 'No suite named ', trim(suite_name), ' found'
          {errflg_var} = 1
        end if

    Properties
    ----------
    suite_schemes : ArrayAttr[ArrayAttr[StringAttr]]
        Outer array has one inner ArrayAttr per suite.  In each inner array,
        element [0] is the suite name and elements [1:] are the scheme names
        in first-occurrence order (duplicates already removed by the caller).
    errmsg_var : StringAttr
        Name of the character variable to write the error message into.
    errflg_var : StringAttr
        Name of the integer variable to set to 1 on error.
    """

    name = "ccpp_utils.cam_suite_scheme_list"

    suite_schemes = prop_def(ArrayAttr)   # ArrayAttr[ArrayAttr[StringAttr]]
    errmsg_var    = prop_def(StringAttr)
    errflg_var    = prop_def(StringAttr)

    def __init__(self, suite_schemes: "list[tuple[str, list[str]]]",
                 errmsg_var: str = "errmsg", errflg_var: str = "errflg"):
        """
        Parameters
        ----------
        suite_schemes
            List of (suite_name, [scheme1, scheme2, ...]) tuples.
        errmsg_var
            Fortran variable name for the error message output.
        errflg_var
            Fortran variable name for the error flag output.
        """
        attr = ArrayAttr([
            ArrayAttr([StringAttr(sn)] + [StringAttr(s) for s in schemes])
            for sn, schemes in suite_schemes
        ])
        super().__init__(properties={
            "suite_schemes": attr,
            "errmsg_var":    StringAttr(errmsg_var),
            "errflg_var":    StringAttr(errflg_var),
        })


CCPPUtils = Dialect(
    "ccpp_utils",
    [
        StrCmpOp,
        TrimOp,
        HostVarRefOp,
        ClearStringOp,
        WriteErrMsgOp,
        WriteStmtOp,
        ArraySectionOp,
        KindDefOp,
        SetStringOp,
        KeywordCallOp,
        AccDataBeginOp,
        AccDataEndOp,
        AccUpdateSelfOp,
        AccUpdateDeviceOp,
        AccEnterDataOp,
        AccExitDataOp,
        GPUDebugPrintOp,
        OmpTargetDataBeginOp,
        OmpTargetDataEndOp,
        OmpTargetUpdateFromOp,
        OmpTargetUpdateToOp,
        OmpTargetEnterDataOp,
        OmpTargetExitDataOp,
        ModuleVarOp,
        LazyAllocOp,
        SafeDeallocOp,
        RankReducingSliceOp,
        PromotionLoopOp,
        SubcycleLoopOp,
        PresentCheckOp,
        ActiveCheckOp,
        NullifyPointerOp,
        AllocateOp,
        ZeroFillOp,
        PointerSliceAssignOp,
        PointerAssignOp,
        AssignOp,
        DdtMethodCallOp,
        ErrorGuardOp,
        IfThenOp,
        TextBoundedDoLoopOp,
        ScopedBlockOp,
        RawFortranLinesOp,
        ConstituentFunctionOp,
        BindCSubroutineOp,
        CToFortranStringCopyOp,
        FortranToCStringCopyOp,
        CamHostConstituentApiOp,
        NonCamHostConstituentApiOp,
        DdtComponentDeclOp,
        DerivedTypeDefOp,
        SuiteVariablesOp,
        CppIncludeOp,
        ExternCGuardOp,
        CFunctionSigOp,
        CppFieldDeclOp,
        CppStructDefOp,
        CppNamespaceOp,
        CppCallStatementOp,
        CppBraceInitCallOp,
        CppConstructorOp,
        RawCppLinesOp,
        CHostCapOp,
        CapVarRefOp,
        KindCastOp,
        KindWriteBackOp,
        StringLiteralExprOp,
        StringConcatExprOp,
        VarRefExprOp,
        MemberAccessExprOp,
        IndexExprOp,
        SliceExprOp,
        KeywordArgExprOp,
        CallExprOp,
        ArrayConstructorExprOp,
        UnitConvertOp,
        UnitWriteBackOp,
        RowMajorConvertOp,
        RowMajorWriteBackOp,
        VerticalFlipOp,
        VerticalFlipWriteBackOp,
        ConstituentSyncOp,
        ConstituentIndexLookupOp,
        CamDirectCallOp,
        CallStatementOp,
        CamClearErrStateOp,
        CamQminPreambleOp,
        CamQminPostambleOp,
        ErrorPropagateOp,
        CamSuiteDispatchOp,
        CamSuiteSchemeListOp,
    ],
    [RealKindType, DerivedType],
)
