from xdsl.dialects.builtin import (
    ArrayAttr,
    DYNAMIC_INDEX,
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
    ParametrizedAttribute,
    SSAValue,
    TypeAttribute,
    VerifyException,
)
from xdsl.irdl import (
    AttrSizedOperandSegments,
    IRDLOperation,
    irdl_attr_definition,
    irdl_op_definition,
    operand_def,
    opt_operand_def,
    opt_prop_def,
    param_def,
    prop_def,
    region_def,
    result_def,
    traits_def,
    var_operand_def,
    var_result_def,
)
from xdsl.traits import NoTerminator


@irdl_attr_definition
class RealKindType(ParametrizedAttribute, TypeAttribute):
    """MLIR type representing a Fortran real with a named kind qualifier.

    Used for Fortran code generation only — carries the kind name through
    the IR so the printer can emit 'real(kind=kind_name)' declarations.
    """

    name = "ccpp_utils.real_kind"
    kind_name: StringAttr = param_def()

    def __init__(self, kind_name: str | StringAttr):
        if isinstance(kind_name, str):
            kind_name = StringAttr(kind_name)
        super().__init__(kind_name)


@irdl_attr_definition
class DerivedType(ParametrizedAttribute, TypeAttribute):
    """MLIR type representing a Fortran derived data type (DDT).

    Used for Fortran code generation only — carries the DDT name through
    the IR so the printer can emit 'type(type_name)' declarations.
    """

    name = "ccpp_utils.derived_type"
    type_name: StringAttr = param_def()

    def __init__(self, type_name: str | StringAttr):
        if isinstance(type_name, str):
            type_name = StringAttr(type_name)
        super().__init__(type_name)


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
        if isinstance(literal, str):
            literal = StringAttr(literal)
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

    A corresponding llvm.GlobalOp stub (with a 'module' attribute) is placed
    at the enclosing module level to drive 'use module, only: var' generation.
    """

    name = "ccpp_utils.host_var_ref"

    var_name = prop_def(StringAttr)
    module_name = prop_def(StringAttr)
    # member_name is stored in the attributes dict (not a formal property) when
    # this op references a DDT member: reference emitted as var_name%member_name.
    res = result_def()  # type set at construction to match callee expectation

    def __init__(
        self, var_name: str | StringAttr, module_name: str | StringAttr,
        result_type, member_name: str | None = None,
    ):
        if isinstance(var_name, str):
            var_name = StringAttr(var_name)
        if isinstance(module_name, str):
            module_name = StringAttr(module_name)
        super().__init__(
            properties={"var_name": var_name, "module_name": module_name},
            result_types=[result_type],
        )
        if member_name is not None:
            self.attributes["member_name"] = StringAttr(member_name)


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
        if isinstance(prefix, str):
            prefix = StringAttr(prefix)
        if isinstance(suffix, str):
            suffix = StringAttr(suffix)
        super().__init__(
            operands=[dest, var],
            properties={"prefix": prefix, "suffix": suffix},
        )


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
    generated ``ccpp_kinds`` Fortran module.  Both properties are strings:
    ``kind_name`` is the Fortran identifier (e.g. ``kind_phys``) and
    ``kind_value`` is its definition (e.g. ``REAL64`` from iso_fortran_env).
    """

    name = "ccpp_utils.kind_def"

    kind_name = prop_def(StringAttr)
    kind_value = prop_def(StringAttr)

    def __init__(self, kind_name: str | StringAttr, kind_value: str | StringAttr):
        if isinstance(kind_name, str):
            kind_name = StringAttr(kind_name)
        if isinstance(kind_value, str):
            kind_value = StringAttr(kind_value)
        super().__init__(properties={"kind_name": kind_name, "kind_value": kind_value})


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
        if isinstance(callee, str):
            callee = StringAttr(callee)
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
    """Emit !$acc data copyin(...) copyout(...) present(...) directive."""
    name = "ccpp_utils.acc_data_begin"
    copyin_arrays  = var_operand_def()   # arrays to copy host → device
    copyout_arrays = var_operand_def()   # arrays to copy device → host
    present_arrays = var_operand_def()   # arrays asserted already on device

    irdl_options = [AttrSizedOperandSegments()]
  
    def __init__(self, copyin=None, copyout=None, present=None):
        super().__init__(operands=[
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
class ModuleVarOp(IRDLOperation):
    """Unified module-level variable declaration.

    Replaces the former ``AllocatableModVarOp`` (real vars) and
    ``ModuleTypeVarOp`` (DDT vars) with a single consistent representation.

    Printer emits in the module spec section before CONTAINS:
        rank=0: ``{fortran_type} :: {var_name}``
        rank>0: ``{fortran_type}, allocatable :: {var_name}(:, :, ...)``

    Examples::

        ModuleVarOp("temp_layer", "real(kind=kind_phys)", rank=2)
        → real(kind=kind_phys), allocatable :: temp_layer(:, :)

        ModuleVarOp("vmr_cap_ddt_suite", "type(vmr_type)", rank=0)
        → type(vmr_type) :: vmr_cap_ddt_suite
    """

    name = "ccpp_utils.module_var"
    var_name     = prop_def(StringAttr)
    fortran_type = prop_def(StringAttr)   # e.g. "real(kind=kind_phys)", "type(vmr_type)"
    rank         = prop_def(IntegerAttr)  # 0 = scalar, >0 = allocatable array

    def __init__(self, var_name: str, fortran_type: str, rank: int = 0):
        super().__init__(properties={
            "var_name":     StringAttr(var_name),
            "fortran_type": StringAttr(fortran_type),
            "rank":         IntegerAttr.from_int_and_width(rank, 64),
        })


# Legacy aliases — kept temporarily so external callers see a clear deprecation path.
# Use ModuleVarOp directly for new code.
def AllocatableModVarOp(var_name: str, kind_name: str, rank: int) -> "ModuleVarOp":  # type: ignore[misc]
    """Deprecated: use ModuleVarOp('real(kind={kind_name})', rank=rank) instead."""
    return ModuleVarOp(var_name, f"real(kind={kind_name})", rank)


@irdl_op_definition
class LazyAllocOp(IRDLOperation):
    """Allocate a module-level array on its first use and initialize it.

    Emitted inside _suite_physics before the first scheme call:
        if (.not. allocated(var_name)) then
          allocate(var_name(d1, d2, ...))
          var_name = init_value
        end if

    dim_vars are SSA values whose variable names supply the dimension extents.
    """

    name = "ccpp_utils.lazy_alloc"
    var_name   = prop_def(StringAttr)
    kind_name  = prop_def(StringAttr)
    init_value = opt_prop_def(StringAttr)  # Fortran literal, e.g. "0.0_kind_phys"
    dim_vars   = var_operand_def()          # SSA values giving dimension sizes

    def __init__(self, var_name: str, kind_name: str, dim_var_refs: list,
                 init_value: str | None = None):
        props: dict = {
            "var_name":  StringAttr(var_name),
            "kind_name": StringAttr(kind_name),
        }
        if init_value is not None:
            props["init_value"] = StringAttr(init_value)
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
class SuiteVariablesOp(IRDLOperation):
    """Carries the generated ccpp_physics_suite_variables Fortran text.

    The `body` attribute holds the complete pre-built Fortran subroutine as a
    string; the printer emits it verbatim inside the module's CONTAINS section.
    """

    name = "ccpp_utils.suite_variables"

    body = prop_def(StringAttr, prop_name="body")

    def __init__(self, body: str):
        super().__init__(properties={"body": StringAttr(body)})


def ModuleTypeVarOp(var_name: str, fortran_type: str) -> "ModuleVarOp":  # type: ignore[misc]
    """Deprecated: use ModuleVarOp(var_name, fortran_type) instead."""
    return ModuleVarOp(var_name, fortran_type, rank=0)


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


CCPPUtils = Dialect(
    "ccpp_utils",
    [
        StrCmpOp,
        TrimOp,
        HostVarRefOp,
        WriteErrMsgOp,
        ArraySectionOp,
        KindDefOp,
        SetStringOp,
        KeywordCallOp,
        AccDataBeginOp,
        AccDataEndOp,
        AccUpdateSelfOp,
        AccUpdateDeviceOp,
        OmpTargetDataBeginOp,
        OmpTargetDataEndOp,
        OmpTargetUpdateFromOp,
        OmpTargetUpdateToOp,
        ModuleVarOp,
        LazyAllocOp,
        SafeDeallocOp,
        RankReducingSliceOp,
        PromotionLoopOp,
        SuiteVariablesOp,
        CapVarRefOp,
    ],
    [RealKindType, DerivedType],
)
