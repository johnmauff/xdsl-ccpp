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
        needs_device_residency: bool = False,
    ):
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
        if init_value is not None:
            props["init_value"] = StringAttr(init_value)
        if needs_device_residency:
            props["needs_device_residency"] = BoolAttr.from_bool(True)
        super().__init__(properties=props)


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
    """

    name = "ccpp_utils.active_check"

    condition_expr = prop_def(StringAttr)

    with_body    = region_def("single_block")
    without_body = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, condition_expr: str, with_body_ops: list, without_body_ops: list):
        super().__init__(
            properties={"condition_expr": StringAttr(condition_expr)},
            regions=[with_body_ops, without_body_ops],
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
    """Allocate a Fortran allocatable or pointer variable to a given shape.

    Emits::

        allocate({var_name}({dims[0]}, {dims[1]}, ...))

    ``dims`` is an ArrayAttr of StringAttr Fortran expressions (e.g.
    ``"ncols"``, ``"size(lc_const_props)"``).
    """

    name = "ccpp_utils.allocate"
    var_name = prop_def(StringAttr)
    dims     = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]

    def __init__(self, var_name: str, dims: "list[str]"):
        super().__init__(properties={
            "var_name": StringAttr(var_name),
            "dims":     ArrayAttr([StringAttr(d) for d in dims]),
        })


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
    """

    name = "ccpp_utils.pointer_assign"
    ptr_name = prop_def(StringAttr)
    rhs_expr = prop_def(StringAttr)

    def __init__(self, ptr_name: str, rhs_expr: str):
        super().__init__(properties={
            "ptr_name": StringAttr(ptr_name),
            "rhs_expr": StringAttr(rhs_expr),
        })


@irdl_op_definition
class AssignOp(IRDLOperation):
    """A plain (non-pointer) scalar or array-element assignment statement.

    Emits::

        {lhs_expr} = {rhs_expr}

    Both sides are printed verbatim -- this deliberately does not attempt
    to structurally model the assigned expression (see TDB-004 in
    BACKLOG.md: a real language-neutral expression IR is a separate,
    much larger effort). Covers plain-value assignment; use
    PointerAssignOp/PointerSliceAssignOp instead for `=>` pointer
    association.

    Added as part of TDB-003 (cpp_interop.py's own raw-string conversion,
    which needs this regardless), deliberately pulled forward from
    TDB-004's own Stage-1 proposal for constituent_cap.py's remaining
    leaves -- landing one AssignOp design now means TDB-004 reconciles a
    single existing design instead of two independently-invented ones.
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
    """

    name = "ccpp_utils.ddt_method_call"
    obj_expr = prop_def(StringAttr)
    method   = prop_def(StringAttr)
    args     = prop_def(ArrayAttr)   # ArrayAttr[StringAttr], positional
    kwargs   = prop_def(ArrayAttr)   # ArrayAttr[StringAttr], "name=expr"

    def __init__(self, obj_expr: str, method: str,
                 args: "list[str] | None" = None, kwargs: "list[str] | None" = None):
        super().__init__(properties={
            "obj_expr": StringAttr(obj_expr),
            "method":   StringAttr(method),
            "args":     ArrayAttr([StringAttr(a) for a in (args or [])]),
            "kwargs":   ArrayAttr([StringAttr(k) for k in (kwargs or [])]),
        })


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
    """

    name = "ccpp_utils.error_guard"
    condition   = prop_def(StringAttr)
    errmsg_text = prop_def(StringAttr)
    errflg_var  = opt_prop_def(StringAttr)  # default "errflg" if unset
    errmsg_var  = opt_prop_def(StringAttr)  # default "errmsg" if unset

    def __init__(self, condition: str, errmsg_text: str,
                 errflg_var: str = "errflg", errmsg_var: str = "errmsg"):
        props: dict = {
            "condition":   StringAttr(condition),
            "errmsg_text": StringAttr(errmsg_text),
        }
        if errflg_var != "errflg":
            props["errflg_var"] = StringAttr(errflg_var)
        if errmsg_var != "errmsg":
            props["errmsg_var"] = StringAttr(errmsg_var)
        super().__init__(properties=props)


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
    """

    name = "ccpp_utils.if_then"
    condition_expr = prop_def(StringAttr)
    body = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, condition_expr: str, body_ops: list):
        from xdsl.ir import Block, Region
        super().__init__(
            properties={"condition_expr": StringAttr(condition_expr)},
            regions=[Region([Block(body_ops)])],
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
                       budget -- see the shared ``_wrap_paren_list``
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
    re: TDB-004). The shape is fixed -- always blank-init then scan-until-
    NUL -- so a dedicated op is clearer here than composing it from
    smaller loop primitives; it never varies across its call sites.

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
    re: TDB-004). Mirror image of CToFortranStringCopyOp; kept as a
    separate op rather than a direction flag since the two shapes share no
    printable text and a flag would just push the branching into the
    printer.

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
class CHostCapOp(IRDLOperation):
    """Carries the auto-generated BIND(C) cap for a C++ host model.

    ``ftn_body`` holds the complete Fortran module as structured IR (a
    single-block Region of statement ops, printed by ``print_ftn.py``
    exactly like any other module body). ``cpp_text``/``wrapper_text``
    remain pre-built C++ header/wrapper text (TDB-003 Stages 2/3 give
    these the same region-based treatment; until then ``print_cpp_header.py``
    has no op-dispatch printer of its own to consume regions for C++ output
    -- unlike ``print_ftn.py``, which already had one, so ``ftn_body`` alone
    could adopt the region shape in Stage 1 without inventing that
    infrastructure speculatively). Generated by the ``generate-ccpp-cap``
    pass when the host declares ``language = "c++"``.

    ``mod_name`` is the base name used for the module and header file, e.g.
    ``"Kessler_ccpp_chost_cap"``.
    """

    name = "ccpp_utils.chost_cap"

    ftn_body     = region_def("single_block")   # complete Fortran module, as ops
    cpp_text     = prop_def(StringAttr)   # complete C++ header text
    wrapper_text = prop_def(StringAttr)   # C++ ergonomics wrapper (.hpp)
    mod_name     = prop_def(StringAttr)   # base name, e.g. "Kessler_ccpp_chost_cap"

    traits = traits_def(NoTerminator())

    def __init__(self, ftn_body_ops: list, cpp_text: str, mod_name: str,
                 wrapper_text: str = ""):
        from xdsl.ir import Block, Region
        super().__init__(
            properties={
                "cpp_text":     StringAttr(cpp_text),
                "wrapper_text": StringAttr(wrapper_text),
                "mod_name":     StringAttr(mod_name),
            },
            regions=[Region([Block(ftn_body_ops)])],
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
    """

    name = "ccpp_utils.unit_convert"

    source         = operand_def()
    to_scheme_expr = prop_def(StringAttr)  # e.g. "+ 273.15" or "" for out-only

    res = result_def()

    def __init__(
        self,
        source: "SSAValue | IRDLOperation",
        to_scheme_expr: "str | StringAttr",
        result_type,
    ):
        to_scheme_expr = _coerce_str_attr(to_scheme_expr)
        super().__init__(
            operands=[source],
            properties={"to_scheme_expr": to_scheme_expr},
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
    """

    name = "ccpp_utils.unit_write_back"

    conv_result   = operand_def()
    original_dest = operand_def()

    to_host_expr = prop_def(StringAttr)   # e.g. "- 273.15"

    def __init__(
        self,
        conv_result:   "SSAValue | IRDLOperation",
        original_dest: "SSAValue | IRDLOperation",
        to_host_expr:  "str | StringAttr",
    ):
        to_host_expr = _coerce_str_attr(to_host_expr)
        super().__init__(
            operands=[conv_result, original_dest],
            properties={"to_host_expr": to_host_expr},
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
    BindCSubroutineOp's own header does (shared ``_wrap_paren_list``
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
        CHostCapOp,
        CapVarRefOp,
        KindCastOp,
        KindWriteBackOp,
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
